# L5 — révocation de session dans le banc Unix

État au 27 octobre 2026 : implémenté et testé sur le banc isolé. Aucune instance
n'est créée par le lanceur de Cockpitor ; aucune action système n'est activée.

## Autorité indépendante du client

SessionVerificationServer utilise un objet Sessions de confiance, injecté dans le
même processus. Le serveur connaît donc l'état réel des sessions du banc sans
attendre que le client possède un ticket ou envoie un message de révocation.
La déconnexion, l'expiration inactive (15 min) et la durée absolue (8 h) utilisent
les règles de Sessions existantes. Une autorité indisponible vaut refus.

Un moniteur passe nominalement toutes les 50 ms sur les opérations associées aux
sessions. Il invalide leurs tickets en attente ou consommés pour une lecture, sans
utiliser de connexion entrante et sans attendre le verrou des sondes. Une saturation
des quatre connexions ne bloque donc pas ce contrôle interne. Ce n'est pas une
borne temps réel : la planification et la boucle asyncio doivent progresser.
Les contrôles synchrones avant/après chaque lecture et avant la réponse vérifient
également la session. Une sonde déjà commencée peut continuer, sans pouvoir valider
son ticket si la révocation est constatée avant la fin de la vérification.

Le moniteur est annulé et attendu à la fermeture ; associations et capacités sont
effacées. La révocation d'une session ne retire pas les tickets des autres sessions.
Elle n'annule pas une vérification déjà terminée et ne promet aucun retour arrière.

## Liaison obligatoire dans ce mode

Le message issue v2 du serveur de session exige session_scope : un identifiant
opaque de 64 caractères hexadécimaux, ici le hash du jeton Sessions. Aucun jeton
brut n'est transmis. Le serveur refuse une session absente, inconnue ou expirée
avant la sonde ; une session invalidée pendant l'émission ne reçoit aucun ticket.

L'identifiant d'opération est lié à sa session avant la lecture. Une nouvelle
émission ne peut pas remplacer ce lien. Les messages verify ne peuvent pas choisir
une autre session : leur lien vient du registre serveur, tandis que leur ticket
reste nécessaire. Le client configuré pour une session refuse un propriétaire
ActionEngine différent avant tout échange. Le moteur fournit désormais ce propriétaire
au vérificateur ; les clients de banc non configurés restent compatibles.

Le serveur de vérification historique refuse les champs de session. Un client
configuré ne peut donc pas se rabattre silencieusement sur un serveur sans autorité.
Aucun message réseau ne permet de désactiver le moniteur ou d'invalider arbitrairement
une session. La révocation ponctuelle par ticket reste disponible après expiration,
puisqu'elle ne fait que réduire une capacité.

## Mémoire et confidentialité

Le registre ne conserve que l'identifiant d'opération et l'identifiant opaque de
session en mémoire. Il est borné par les 256 opérations réservées. Une émission
échouée avant réservation retire son association ; les IDs réservés restent non
réutilisables jusqu'au remplacement du serveur. Ni jeton brut ni identifiant de
session n'est ajouté aux audits SQLite ou renvoyé dans les réponses Unix.
Aucun nouveau schéma, endpoint web, droit système ou configuration du lanceur.

## Limites de la preuve

Cette autorité est une **référence dans le même processus de laboratoire**. Ce n'est
pas encore un canal authentifié entre deux services réels. L'identifiant de session
et l'UID ne prouvent pas une approbation humaine au serveur ; le cycle applicatif
approuvé/audité reste distinct. Un programme malveillant du même compte n'est pas
isolé par cette architecture de test. Un futur auxiliaire privilégié exigera une
frontière d'approbation, une autorité inter-processus et ses pannes qualifiées.
Les vrais pilotes, les clés entre processus et les essais en VM restent requis.

## Validation

21 nouveaux tests dans test_session_verification.py : révocation de plusieurs
tickets d'une session seulement, réponse perdue, expirations inactive/absolue,
lecture et émission interrompues, autorité indisponible, absence de scope valide,
nettoyage, réassociation refusée, saturation des connexions, propriétaire incohérent,
absence de repli et parcours réel Sessions/ActionEngine/audit/socket de test.

```sh
.venv/bin/pytest -q backend/tests/test_session_verification.py
```

Total : 420 tests backend et 26 frontend passants, lint/types/format/build passants.
Les sondes sont contrôlées ; aucun service ni conteneur réel n'est modifié.

## Complément du 28 octobre : processus séparé

Le nouveau RemoteSessionVerificationServer consulte une autorité par RPC Unix
privé, au lieu d'une référence Sessions locale. UID, nonce, types, délais et panne
sont testés, y compris avec une autorité dans un processus enfant. Ce mode ne se
replie pas vers l'autorité locale et ne conserve pas d'autorisation positive en cache.
Les paragraphes ci-dessus décrivent le mode local historique. Voir
[REMOTE_SESSION_AUTHORITY.md](REMOTE_SESSION_AUTHORITY.md) pour le mode distant
non privilégié et les limites de la preuve. Total actuel : 440 backend et 26 frontend.
