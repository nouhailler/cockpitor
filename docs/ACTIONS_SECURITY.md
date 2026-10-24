# Actions contrôlées — lot L4, 24 octobre 2026

## Portée livrée

Le lot implémente un cycle de plan et d’approbation **uniquement en simulation**.
Il ne contient ni exécuteur système, ni sudo, ni auxiliaire privilégié. Les endpoints
réels start/stop/restart/execute restent refusés ; aucune variable d’environnement
ne permet de les activer. L’assistant IA ne dispose toujours d’aucun outil d’action.

Les cinq types examinables sont service.start, service.stop, service.restart,
container.start et container.restart. Ils décrivent ce qui serait demandé dans une
future version ; leur simulation ne lance aucune de ces commandes. Les seules
commandes système utilisées par le préflight sont des lectures systemctl show ;
les moteurs sont interrogés uniquement en GET sur leur socket explicitement configuré.
Le préflight ne prouve pas l’autorisation d’exécuter ultérieurement l’action réelle.

## Cycle et protections

1. Préparer : schéma strict (2 Kio), action en liste blanche, unité exacte ou moteur
   Docker/Podman + identifiant complet. Inventaire disponible et frais de 40 s maximum.
   Services critiques et unités inconnues exclus, aucun argument/chemin de commande libre.
2. Examiner : état observable et empreinte du plan, lié au hash de la session courante.
   Le plan expire après 120 s et n’est pas modifiable. Une configuration systemd
   nécessitant daemon-reload est refusée ; aucun reload n’est effectué.
3. Approuver : confirmed doit être exactement le booléen true, avec identifiant et
   empreinte du plan. Le serveur relit la cible et sa configuration. Le jeton aléatoire
   de 256 bits est remis une seule fois, conservé haché en mémoire et valable au plus
   60 s, sans dépasser la date limite du plan.
4. Simuler : session, état, expiration, jeton et cible sont revérifiés. L’approbation
   est consommée et l’audit de début validé avant la simulation. Une seule simulation
   simultanée ; deadline de huit secondes pour ses contrôles. L’état est encore relu
   pendant la simulation. Résultat explicite : aucune commande de modification et
   aucun changement système. Un résultat positif exige un audit final validé.
5. Annuler/expirer : invalidation de l’approbation ; annulation de la tâche en cours.
   Les sessions révoquées ou expirées sont contrôlées avant/après les lectures ; une
   tâche de nettoyage passe toutes les deux secondes. Aucune annulation n’est annoncée
   réussie si son audit échoue. Un crash/restart/rétablissement du stockage invalide
   les opérations non terminales, enregistrées comme interrupted.

Une panne d’audit avant approbation ou simulation bloque la transition. Si l’audit
final échoue, aucun succès n’est annoncé ; la reprise classe l’opération interrompue.
SQLite met à jour état et événement d’audit dans la même transaction. Les approbations
ne sont ni restaurables après redémarrage ni transférables à une autre session.

Les configurations systemd et Config/HostConfig/Mounts des conteneurs sont comparées
par HMAC SHA-256, avec une clé aléatoire propre au processus. Les commandes, environnements
et montages bruts ne quittent pas les adaptateurs. Le plan ajoute une empreinte de
l’action/cible et de l’instantané filtré. La base ne conserve que identifiant, type,
état et dates ; aucun jeton, cible ou instantané. Les identifiants d’événements d’audit
portent le préfixe de l’opération pour la corrélation.

Limites : 64 plans non terminés en mémoire, historique borné à 1000 opérations
récentes plus les opérations encore en attente, audit commun de 1000 événements.
Les plans terminés peuvent être oubliés en mémoire lors d’une nouvelle préparation.
Les durées de l’interface représentent la dernière réponse ; le serveur fait autorité.
Quitter la page perd l’approbation côté navigateur ; il faut préparer un nouveau plan.

## Vérifications réalisées

- Schémas : injections, noms/préfixes de conteneurs, moteur inconnu, mode execute,
  commande libre, unités critiques, confirmation 1/false/texte/null refusés.
- Autorisations : session étrangère, jeton falsifié, empreinte modifiée, expiration
  avant et pendant lecture, révocation et rejeu refusés.
- Cohérence : cible/configuration modifiée, concurrence, annulation, timeout,
  quota de plans, panne SQLite, audit final absent et reprise après interruption.
- Transactions : un trigger de refus d’audit vérifie le rollback de l’approbation.
- Adaptateurs : commandes secrètes masquées par HMAC, modification de configuration
  détectée et préflight conteneur n’émettant que des GET (tests contrôlés).
- Frontend : confirmation obligatoire, étapes séparées, erreur invalidant le parcours,
  annulation, absence du jeton dans le DOM/localStorage et affichage anglais explicite.
- Navigateur réel : plan cron.service préparé, approuvé puis simulé ; aucun redémarrage.
  Résultat et historique vérifiés en français et en anglais ; capture versionnée.

Référence : backend/tests/test_actions.py et frontend/tests/actions.test.tsx.

## Barrière avant L5 — non franchie

Les tests du simulateur ne qualifient pas un exécuteur privilégié. Avant toute
activation réelle, il reste à concevoir et relire son protocole typé et ses règles
minimales de privilège, vérifier l’identité de son client, qualifier les opérations
exactes et leurs échecs partiels, puis tester en VM jetable sur systemd/Docker/Podman
réels. Aucun de ces essais destructifs ou changements de permissions n’a été effectué.
La liste de services critiques reste une protection supplémentaire ; elle ne remplace
pas une autorisation positive propre à chaque future action et cible.

Une exécution réelle ne serait pas atomique avec l’audit SQLite ni avec l’état
observé à distance : courses de changement de cible, résultats inconnus après crash
et impossibilité éventuelle d’annuler une action devront être traités séparément.
Aucune déclaration de sécurité générale ou d’autorisation de production n’est déduite
du succès des tests de simulation.
