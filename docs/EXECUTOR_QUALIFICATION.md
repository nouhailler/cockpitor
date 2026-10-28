# Préparation L5 — protocole et qualification

État au 24 octobre 2026 : politique et transport de vérification testés,
**aucune exécution activée**. La politique, le transport et le nouveau client
`backend/app/executor_client.py` sont reliés au moteur L4 dans les tests de banc.
Le lanceur habituel n'instancie aucun client Unix et ne propose aucune activation.
Ces modules ne contiennent ni sous-processus, ni connexion à un moteur, ni auxiliaire privilégié.
Un banc séparé compile maintenant les opérations et vérifie leurs postconditions
avec des pilotes de fixtures : [adaptateurs de laboratoire](ADAPTER_TRIALS.md).
Il n'est raccordé ni au protocole v2 ni au moteur de simulation.

## Contrat proposé

Une future frontière de confiance devra séparer l'application de l'exécuteur.
Le transport de laboratoire lit l'UID fourni par le noyau Linux via SO_PEERCRED
sur une socket Unix privée. Il n'accepte jamais cet UID dans le JSON. Les tests
ouvrent de vraies sockets et vérifient le refus lorsque cet UID ne correspond pas
à celui configuré dans la politique.
Une socket ne distinguant pas deux applications du même UID, l'isolation du compte
et les permissions du répertoire/socket feront partie de la revue de déploiement.

La politique est vide par défaut lors de sa construction explicite avec zéro droit.
Chaque droit autorise un triplet exact action/cible/moteur. Les unités critiques
restent interdites même si elles sont ajoutées aux droits. Aucun joker, argument,
chemin de programme, utilisateur cible ou commande libre n'est accepté.

Le transport implémente une longueur de quatre octets non signés en ordre réseau,
puis au maximum 2048 octets de JSON UTF-8. Il traite une requête par connexion,
limite les connexions traitées à quatre et sérialise politique et sondes. Le délai
de deux secondes inclut réception, attente du verrou, traitement et réponse ; la
sonde asynchrone dispose au plus d'une seconde. Ces délais supposent une sonde
coopérative à l'annulation, comme toute limite asyncio. Une réponse de refus et la
fermeture disposent chacune d'au plus 100 ms de nettoyage supplémentaires. Les
connexions surnuméraires sont fermées immédiatement ; un client refusé avant
lecture peut observer une fermeture/réinitialisation plutôt qu'une réponse JSON.
Le JSON réseau v2 refuse champs supplémentaires, doublons, constantes non finies, types
implicites et versions inconnues. Aucun instantané n'est accepté depuis le client.

Le protocole se déroule ainsi :

1. L'application valide session, approbation L4 et audit de début avant tout appel
   au client Unix. La liaison est implémentée par injection explicite d'un vérificateur
   de simulation et testée sur le banc ; elle n'est pas configurée dans le lanceur.
   Un ticket seul ne prouve aucun consentement.
2. L'exécuteur relit lui-même la cible, vérifie un droit positif puis réserve un
   identifiant d'opération et émet un ticket aléatoire de 256 bits valable 30 s.
   Dès la première lecture, son empreinte doit égaler celle du plan approuvé ; une
   simple stabilité entre les deux lectures ne suffirait pas.
   Seule son empreinte est conservée. La sonde est une dépendance de confiance du
   serveur, appelée après vérification des droits. Les tests fournissent une sonde
   contrôlée ; les adaptateurs de lecture réels restent à raccorder et qualifier.
3. Après une nouvelle lecture fiable, le ticket est consommé avant vérification
   de sa valeur, expiration et empreinte de cible/configuration. Un échec impose
   un nouvel identifiant. Un client étranger ne peut pas brûler le ticket.
4. Le résultat est une intention immuable. **Ce résultat n'exécute rien**. Les futurs
   adaptateurs devront appliquer une commande fixe et vérifier sa postcondition.

Les 256 identifiants réservés ne sont jamais évincés, même après consommation ou
expiration. À saturation, le prototype refuse toute émission ; remplacer l'instance
invalide tous les tickets. Une nouvelle instance ne peut accepter un ancien ticket.
Le transport sérialise les appels et consomme le ticket avant la seconde sonde.
Un échec, une expiration pendant la sonde ou un timeout ne permettent donc pas de
réessayer le même ticket. Si la réponse d'émission est perdue, l'identifiant reste
réservé ; aucun rejeu automatique. La fermeture annule les tâches, invalide les
tickets, interdit les nouvelles émissions et exige une nouvelle instance pour
redémarrer. Aucune API ne permet de restaurer les tickets après crash.

## Transport de laboratoire livré

Le serveur exige un chemin absolu, un répertoire réel sans alias symbolique,
appartenant à son UID effectif et de mode exactement 0700. La socket créée est de
mode 0600. Tout chemin existant, y compris une socket ou un lien pendant, est
refusé sans suppression. Le nettoyage ne supprime que la socket créée, reconnue
par son type, périphérique et inode ; un remplacement est conservé.
Le démarrage sous root ou sans SO_PEERCRED est refusé. Il n'existe ni commande
de lancement installée, ni variable d'activation, ni configuration Unix dans FastAPI, ni liaison à l'IA.

Trois messages sont reconnus :

- `issue` : version 2, identifiant d'opération, requête d'action typée et
  `expected_fingerprint` du plan approuvé ; réponse `ticket_issued` avec ticket,
  durée 30 s, version, identifiant et empreinte concordants.
- `verify` : version 2, identifiant et ticket ; réponse `verified_only` après nouvelle
  sonde et comparaison, avec la même version, le même identifiant et l'empreinte.
  La réponse ne renvoie ni cible ni instantané.

- `revoke` : version 2, identifiant et ticket exact ; réponse `revoked` si la
  capacité en attente/en lecture est invalidée, idempotente si déjà révoquée.
  Cette mise à jour n'attend pas le verrou des sondes, mais partage l'admission
  limitée aux connexions du banc. Une révocation après vérification terminée est refusée.

La version réseau 1 est refusée, sans repli automatique : elle ne liait pas
l'émission à l'empreinte approuvée. L'enveloppe interne de la politique reste v1 ;
elle n'est pas acceptée telle quelle par le transport v2.

Toutes les réponses portent `system_execution_enabled: false`. Les erreurs sont
réduites à `rejected`, sans exception, secret, ticket ni donnée de sonde. Les appels
n'exécutent jamais l'intention vérifiée. Les mêmes UID restent une frontière de
confiance commune ; cette politique n'isole pas des programmes malveillants du même
compte. L'audit propre d'un futur exécuteur, les privilèges minimaux et les opérations
réelles restent à implémenter avant activation. Le serveur ne vérifie pas lui-même
une approbation humaine : cette responsabilité reste dans le moteur applicatif.
Avant d'en faire un exécuteur privilégié, la frontière de confiance de cette
approbation doit être revue indépendamment.

Validation : 35 tests de transport sur sockets Unix locales et 25 tests de politique,
dont fermeture, saturation, rejeu concurrent, trames lentes/tronquées, changements de
configuration, sonde en panne, refus root et absence de SO_PEERCRED. Aucun service
ni conteneur n'est modifié. Ces preuves ne qualifient pas un exécuteur privilégié.

## Liaison au moteur et audit — banc de simulation

Le moteur L4 conserve ses contrôles d'origine : session propriétaire, approbation
ponctuelle, relecture de cible et validation transactionnelle de `actions.simulating`
avant tout échange Unix. Sans vérificateur injecté, son comportement habituel reste
local. Avec le client de banc, la simulation :

1. Contrôle la session et l'échéance avant connexion, avant envoi et après réponse
   de chaque échange. Le client vérifie le dossier/socket privés et l'UID noyau du
   serveur, puis impose des réponses strictes et concordantes avec le plan.
2. Reçoit une vérification sans effet système, puis enregistre
   `actions.transport_verified`, corrélé au même identifiant d'opération. L'écriture
   SQL exige l'état `simulating` et prend le verrou d'écriture avant l'audit.
3. Revérifie session/échéance et ne termine en `simulated` qu'après audit final.
   Une panne d'audit ne produit aucun succès. Les opérations non terminales sont
   reclassées `interrupted` à la reprise, comme en L4.

Le résultat ajoute `transport_verified` (false dans le lanceur habituel).
`commands_executed`, `system_changed` et `system_execution_enabled` restent false.
L'audit conserve uniquement le type d'événement, la date et l'identifiant corrélé ;
ni cible, session, ticket Unix, jeton d'approbation ni instantané. Schéma SQLite v3
inchangé. L'erreur client est expurgée et disponible en français/anglais.

Le client n'accepte pas de serveur root, ne réessaie pas et ne dégrade pas le
protocole. Ses échanges ont chacun une limite de 2,5 s, plus 100 ms de fermeture.
L'annulation ferme le client ; après réception d'un ticket valide, le client tente
une révocation ponctuelle avec nettoyage borné. Une sonde distante déjà démarrée
peut continuer jusqu'à son délai, sans effet système, mais un ticket révoqué ne
peut plus être validé. Un ticket émis dont la réponse n'est plus
utilisée reste inutilisable après son expiration et occupe sa réservation bornée.
Le serveur de session décrit plus bas ajoute une invalidation autonome par session
sur le banc. Son autorité reste dans le même processus ; le canal authentifié
vers un futur exécuteur séparé reste bloquant avant toute possibilité d'exécution.

Les empreintes du moteur et de la sonde distante doivent être comparables. Les
sondes contrôlées du banc le garantissent ; une future séparation en processus
réels devra concevoir la gestion des clés HMAC et des instantanés sans transmettre
les secrets au client. Aucun adaptateur réel n'est déclaré qualifié par ces tests.

40 tests dans `test_executor_bridge.py` couvrent le parcours complet sur socket,
l'absence de transport avant approbation/audit, les réponses falsifiées, révocations,
échéances, annulation, panne d'audit et reprise. Avec les autres suites : 279 tests
backend et 26 frontend passants.

## Matrice avant activation — à réaliser en VM jetable

| Essai | Attendu et preuve à conserver |
| --- | --- |
| Client UID étranger, socket ou répertoire trop ouvert | Connexion refusée ou démarrage refusé ; aucun effet |
| Session révoquée, audit indisponible, approbation absente | Aucun appel à l'adaptateur de mutation |
| Unité fixture dédiée : start/stop/restart | Seule l'unité explicitement autorisée change ; état final relu |
| Docker puis Podman : start/restart d'un conteneur fixture | Identifiant intégral, moteur exact et configuration vérifiés |
| Changement entre lectures et mutation | Refus avant mutation lorsque détectable ; course résiduelle documentée |
| Timeout ou crash après envoi de la mutation | Résultat inconnu explicite, aucune répétition automatique |
| Erreur d'audit final après mutation | Aucun faux succès ni faux retour arrière ; rapprochement à la reprise |
| Annulation après début d'une mutation | Aucun engagement d'annulation de l'effet système |
| Redémarrage de l'exécuteur et rejeu | Ancien ticket refusé, opération non rejouée automatiquement |
| Sorties volumineuses, connexions lentes et simultanées | Bornes de mémoire, temps et concurrence respectées |

Pour chaque essai : version du noyau/systemd/moteur, image VM, révision Git,
configuration positive des droits, résultat attendu/observé et audit corrélé.
N'utiliser que des unités et conteneurs fixtures sans volumes hôte ni secrets.
Les résultats des tests unitaires ne doivent pas remplir cette matrice à la place
des essais réels. Cet environnement ne fournit ni VM ni Docker/Podman ; aucun de
ces essais réels n'a été déclaré réussi.

La revue du transport, des privilèges minimaux, des adaptateurs et de cette matrice
reste obligatoire avant de raccorder une route d'exécution. L'IA reste sans outil.

## Avancement des adaptateurs sur fixtures

La logique de commandes/requêtes fixes, les postconditions et le journal durable
des effets potentiellement inconnus sont testés sur des ressources temporaires.
70 tests nouveaux, 349 backend et 26 frontend au total. Le pilote de service exécute
un programme Python de fixture à la place de systemctl ; le pilote conteneur utilise
un serveur HTTP Unix de test. Les vrais pilotes d'entrée/sortie restent absents.
La matrice VM ci-dessus n'est pas remplie par ces résultats, et aucune activation
système ne découle du succès du banc. Voir ADAPTER_TRIALS.md pour les limites.

## Réconciliation sur fixtures — 26 octobre 2026

Le banc dispose maintenant d'un blocage durable par cible et d'une réconciliation
sans envoi, liée à l'observation d'origine. Un résultat inconnu bloque les verbes
sur cette cible jusqu'à deux lectures concordantes et un audit de résolution.
Le journal autonome v2 migre v1 après sauvegarde ; la base applicative reste v3.
30 tests supplémentaires, 379 backend et 26 frontend au total. Les ressources et
pilotes réels ne sont pas qualifiés par ce résultat : la matrice VM reste ouverte.
Voir [FIXTURE_RECONCILIATION.md](FIXTURE_RECONCILIATION.md).

## Révocation ponctuelle — 27 octobre 2026

La révocation de tickets reçus est disponible et testée, sans attendre une sonde
lente et sans prétendre annuler une vérification déjà terminée. Elle ne remplace
pas la révocation globale par session indépendante du client, notamment lorsqu'un
ticket n'a pas été reçu. 20 tests nouveaux, 399 backend et 26 frontend au total.
Voir [TICKET_REVOCATION.md](TICKET_REVOCATION.md) pour les délais et limites.

## Autorité de session de laboratoire — 27 octobre 2026

SessionVerificationServer complète le banc avec une référence Sessions de confiance
et une surveillance autonome, sans ticket reçu ou message client nécessaire à la
révocation. Scope exigé, registre borné, contrôles autour des lectures et liaison au
propriétaire applicatif sont testés ; 21 nouveaux tests, 420 backend et 26 frontend.
Ce n'est pas encore un canal entre processus réels ou une preuve d'approbation
privilégiée. La matrice VM et les pilotes restent ouverts. Voir
[SESSION_TICKET_REVOCATION.md](SESSION_TICKET_REVOCATION.md).

## Canal vers une autorité séparée — 28 octobre 2026

Le canal Unix de contrôle des sessions est implémenté et testé avec une autorité
dans un autre processus Python non privilégié : UID, nonce, schémas stricts, bornes,
absence de cache positif, révocation et panne de processus. 20 tests nouveaux,
440 backend et 26 frontend au total. Le mode local historique reste distinct.
Ce canal ne qualifie pas une approbation privilégiée indépendante ni les pilotes
système. Séparation de privilèges et matrice VM toujours ouvertes. Référence :
[REMOTE_SESSION_AUTHORITY.md](REMOTE_SESSION_AUTHORITY.md).
