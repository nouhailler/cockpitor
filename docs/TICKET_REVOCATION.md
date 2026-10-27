# L5 — révocation ponctuelle des tickets Unix

État au 27 octobre 2026 : disponible dans le banc de vérification isolé. Aucun
serveur Unix n'est lancé par l'application ; aucune action système n'est activée.

## Contrat

Le protocole réseau v2 reconnaît désormais `revoke`, avec version, identifiant
exact et ticket de 256 bits. L'UID est toujours obtenu du noyau, jamais du JSON.
La révocation exige le bon secret ; un mauvais ticket ou un UID étranger ne retire
pas une capacité valide. Aucun nom de cible ou instantané n'est accepté dans ce message.

Le serveur retire le ticket en attente ou déjà consommé pour une lecture en cours,
puis conserve une marque de révocation en mémoire. Une seconde révocation authentique
retourne le même résultat. L'identifiant reste réservé et aucun nouveau ticket
ne peut être émis sous cet identifiant. La réponse `revoked` porte version, identifiant,
empreinte concordante et system_execution_enabled=false.

La mise à jour de politique est synchrone et ne passe pas par le verrou des sondes.
Une sonde lente ne retarde donc pas l'invalidation d'un ticket connu. La lecture
peut continuer jusqu'à son délai, mais sa validation finale exige encore une
capacité active. Après accusé de révocation, cette lecture ne peut plus produire
verified_only. La vérification d'une capacité consommée ne peut réussir qu'une fois.

La limite d'admission reste de quatre connexions traitées. Une saturation, un
transport indisponible ou un délai dépassé peut empêcher la confirmation : le client
ne doit pas annoncer une révocation réussie dans ce cas. Une vérification déjà
terminée n'est pas annulable : une révocation tardive est refusée, sans faux accusé.
Aucun effet système n'existe dans ce protocole et aucune annulation d'effet n'est promise.

## Client et interruption de session

VerificationClient.revoke vérifie les permissions de socket, l'UID serveur et la
réponse stricte. Cette opération de réduction de capacité reste autorisée après
expiration locale de la session ; elle ne demande aucune nouvelle approbation.

Lorsqu'il a reçu et validé un ticket, le client tente sa révocation si un contrôle
de session/échéance échoue, si la vérification échoue ou si sa tâche est annulée.
Il conserve l'erreur initiale, sans reprise de vérification ni tâche de nettoyage
laissée en arrière-plan. Le nettoyage dispose de 300 ms, plus au plus 100 ms pour
fermer sa connexion. Son échec n'est pas transformé en succès.

Cette garantie reste **ponctuelle** : si la connexion est interrompue avant réception
et validation du ticket, le client ne connaît pas le secret à révoquer. Le ticket
reste alors soumis à son expiration de 30 s et à l'invalidation au redémarrage.
Le serveur de laboratoire lié à Sessions peut désormais invalider tous les tickets
sans dépendre du client : voir [SESSION_TICKET_REVOCATION.md](SESSION_TICKET_REVOCATION.md).
Il utilise une référence d'autorité dans le même processus, pas encore un canal
indépendant authentifié entre services réels.
Un ticket déjà vérifié ou consommé par un échec est inutilisable, mais ne peut pas
nécessairement produire un accusé de révocation. Le client n'assimile pas ce refus
à une preuve de retour arrière.

## Bornes et confidentialité

Les ensembles en attente, en lecture et révoqués partagent les identifiants réservés,
limités à 256. Les secrets restent hachés ; aucun ticket brut n'est persisté ou journalisé.
La fermeture efface ces ensembles et interdit leur réutilisation dans l'instance.
Il n'y a ni nouveau schéma SQLite, ni route web, ni variable d'activation, ni liaison
à l'assistant IA. La révocation volatile du banc n'est pas un audit d'exécuteur privilégié.

## Validation

20 nouveaux tests dans `test_executor_revocation.py` couvrent mauvais UID/secret,
idempotence, rejeu, invalidation d'une lecture consommée, validation unique,
révocation concurrente sur socket réelle, annulation du client et nettoyage échoué
ou expiré sans masquer l'erreur initiale. Une révocation tardive est refusée.

Total : 399 tests backend et 26 frontend passants, lint/types/format/build passants.

```sh
.venv/bin/pytest -q backend/tests/test_executor_revocation.py
```

Restent le canal d'autorité authentifié entre processus réels, la preuve
d'approbation à une frontière privilégiée, les vrais pilotes bornés et les essais
systemd/Docker/Podman en VM jetable. Aucun de ces points n'est déclaré qualifié
par les tests ponctuels ci-dessus.

## Complément : autorité de session

Le nouveau serveur de session complète la révocation ponctuelle par une surveillance
autonome des sessions du banc, sans nouveau message client ni besoin du ticket reçu.
Ce mode est explicite et reste hors lanceur. Total actuel : 420 tests backend et
26 frontend. La qualification d'une autorité séparée/privilégiée reste ouverte.
