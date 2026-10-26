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

## Préparation L5 : prototype de protocole isolé

Le module executor_protocol.py ajoute une politique sans exécution ni transport :
UID attendu, droits exacts, enveloppe stricte de 2 Kio, tickets ponctuels 30 s,
empreinte revérifiée et identifiants non réutilisables (quota 256, refus à saturation).
Il n'est pas raccordé à l'application et ne remplace ni l'approbation L4, ni une
identité obtenue du noyau, ni une lecture de cible effectuée par l'exécuteur.
Voir [le contrat et la matrice de qualification](EXECUTOR_QUALIFICATION.md).
La barrière avant activation demeure non franchie.

## Transport de vérification L5

executor_transport.py ajoute un banc Linux AF_UNIX non raccordé à l'application,
avec identité noyau, permissions privées, limites, sondes sérialisées et invalidation
à la fermeture. Les messages issue/verify ne produisent que des tickets et un
résultat verified_only. Les 32 tests de transport utilisent des sockets réelles,
avec sondes contrôlées ; aucune commande de modification n'est exécutée. Le serveur
refuse root. Ce transport ne réalise pas encore la liaison à l'approbation/audit L4,
ni les adaptateurs réels. La barrière d'activation reste non franchie.

## Liaison approbation/audit au banc Unix

Le vérificateur de simulation est maintenant injectable dans ActionEngine pour le
banc. L'approbation et l'audit simulating précèdent tout échange ; session/échéance
sont contrôlées autour de chaque échange et après audit de vérification. Le protocole
réseau v2 lie les deux sondes à l'empreinte du plan approuvé, puis l'audit
transactionnel actions.transport_verified précède le succès final. Toute panne
ou révocation bloque ce succès. Le client refuse réponses incohérentes, exécution
annoncée, UID ou permissions de socket invalides. Il n'effectue aucun rejeu.
40 tests de liaison utilisent de vraies sockets avec sondes contrôlées. Aucun
client n'est instancié par le lanceur, aucun serveur ne réalise de mutation.
La révocation distante immédiate, la preuve d'approbation à une frontière privilégiée,
les clés d'empreinte inter-processus et les adaptateurs restent à qualifier.

## Adaptateurs de fixtures et résultats inconnus

Le nouveau banc autonome compose des opérations fixes, deux lectures avant envoi
et des postconditions de génération/configuration. Il impose un journal privé
persistant avant entrée dans le pilote ; après cette entrée, annulation/timeout
ou réponse ambiguë ne signifie jamais absence d'effet. Les IDs restent réservés
après redémarrage et aucune relance automatique n'existe. L'audit final doit réussir
pour retourner verified ; sinon, la reprise classe l'intention unknown.
Aucun pilote système par défaut n'est fourni. Ces classes ne sont pas des
SimulationVerifier et ne doivent pas être raccordées à la simulation applicative.
Les 70 tests de fixtures ne qualifient pas de mutation réelle. Voir ADAPTER_TRIALS.md.

## Réconciliation et interdiction des relances — 26 octobre 2026

Le banc ajoute une empreinte opaque de ressource et un blocage SQL persistant des
nouveaux essais sur les cibles prepared/dispatching/unknown, quel que soit le verbe.
La réconciliation ne dispose d'aucun chemin d'envoi : observation d'origine liée,
deux lectures concordantes, puis état/événement reconciled atomiques. Une panne ou
révocation laisse le blocage. L'ancien résultat unknown reste dans l'historique,
sans preuve de causalité ni reprise d'approbation. Les inconnus v1 sans liaison
restent bloquants globalement. Voir FIXTURE_RECONCILIATION.md ; activation réelle
et qualification VM toujours absentes.
