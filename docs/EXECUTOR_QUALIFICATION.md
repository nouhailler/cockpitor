# Préparation L5 — protocole et qualification

État au 24 octobre 2026 : politique et transport de vérification testés,
**aucune exécution activée**. `backend/app/executor_protocol.py` et
`backend/app/executor_transport.py` ne sont raccordés à aucun routeur ni lanceur.
Ils ne contiennent ni sous-processus, ni connexion à un moteur, ni auxiliaire privilégié.

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
Le JSON v1 refuse champs supplémentaires, doublons, constantes non finies, types
implicites et versions inconnues. Aucun instantané n'est accepté depuis le client.

Le protocole se déroule ainsi :

1. L'application valide session, approbation L4 et audit de début. Cette liaison
   n'est pas encore implémentée et un ticket de protocole ne prouve aucun consentement.
2. L'exécuteur relit lui-même la cible, vérifie un droit positif puis réserve un
   identifiant d'opération et émet un ticket aléatoire de 256 bits valable 30 s.
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
de lancement installée, ni variable d'activation, ni liaison à FastAPI ou à l'IA.

Deux messages sont reconnus :

- `issue` : version 1, identifiant d'opération et requête d'action typée ; réponse
  `ticket_issued` avec ticket et durée 30 s.
- `verify` : version 1, identifiant et ticket ; réponse `verified_only` après nouvelle
  sonde et comparaison. La réponse ne renvoie ni cible ni instantané.

Toutes les réponses portent `system_execution_enabled: false`. Les erreurs sont
réduites à `rejected`, sans exception, secret, ticket ni donnée de sonde. Les appels
n'exécutent jamais l'intention vérifiée. Les mêmes UID restent une frontière de
confiance commune ; cette politique n'isole pas des programmes malveillants du même
compte. La liaison à l'approbation L4, l'audit de l'exécuteur, les privilèges minimaux
et les opérations réelles restent à implémenter avant activation.

Validation : 32 tests de transport sur sockets Unix locales et 25 tests de politique,
dont fermeture, saturation, rejeu concurrent, trames lentes/tronquées, changements de
configuration, sonde en panne, refus root et absence de SO_PEERCRED. Aucun service
ni conteneur n'est modifié. Ces preuves ne qualifient pas un exécuteur privilégié.

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
