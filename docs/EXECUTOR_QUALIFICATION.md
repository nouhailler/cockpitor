# Préparation L5 — protocole et qualification

État au 24 octobre 2026 : prototype de politique testé, **aucune exécution activée**.
`backend/app/executor_protocol.py` n'est importé par aucun routeur ni lanceur.
Il ne contient ni sous-processus, ni connexion à un moteur, ni auxiliaire privilégié.

## Contrat proposé

Une future frontière de confiance devra séparer l'application de l'exécuteur.
L'identité UID proviendra de SO_PEERCRED sur une socket Unix privée ; elle ne sera
jamais acceptée dans le JSON. Le prototype reçoit cet UID en argument pour tester
la politique ; il ne réalise donc pas encore l'authentification d'un processus.
Une socket ne distinguant pas deux applications du même UID, l'isolation du compte
et les permissions du répertoire/socket feront partie de la revue de déploiement.

La politique est vide par défaut lors de sa construction explicite avec zéro droit.
Chaque droit autorise un triplet exact action/cible/moteur. Les unités critiques
restent interdites même si elles sont ajoutées aux droits. Aucun joker, argument,
chemin de programme, utilisateur cible ou commande libre n'est accepté.

Un futur transport utilisera une longueur annoncée bornée à 2048 octets, un délai
de lecture et une limite de connexions. Ces protections du transport restent à
implémenter : le prototype valide uniquement une trame déjà reçue. Le JSON v1
refuse les champs supplémentaires, doublons, types implicites et versions inconnues.

Le protocole se déroule ainsi :

1. L'application valide session, approbation L4 et audit de début. Cette liaison
   n'est pas encore implémentée et un ticket de protocole ne prouve aucun consentement.
2. L'exécuteur relit lui-même la cible, vérifie un droit positif puis réserve un
   identifiant d'opération et émet un ticket aléatoire de 256 bits valable 30 s.
   Seule son empreinte est conservée. Le prototype reçoit un instantané fourni par
   le test ; une future implémentation doit utiliser sa propre sonde fiable.
3. Après une nouvelle lecture fiable, le ticket est consommé avant vérification
   de sa valeur, expiration et empreinte de cible/configuration. Un échec impose
   un nouvel identifiant. Un client étranger ne peut pas brûler le ticket.
4. Le résultat est une intention immuable. **Ce résultat n'exécute rien**. Les futurs
   adaptateurs devront appliquer une commande fixe et vérifier sa postcondition.

Les 256 identifiants réservés ne sont jamais évincés, même après consommation ou
expiration. À saturation, le prototype refuse toute émission ; remplacer l'instance
invalide tous les tickets. Une nouvelle instance ne peut accepter un ancien ticket.
L'utilisation est séquentielle : un futur transport devra sérialiser les appels.
Aucune API ne permet de restaurer les tickets après crash.

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
