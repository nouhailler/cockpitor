# L5 — kit de préparation à la qualification VM

État au 28 octobre 2026 : précontrôle exécutable en lecture seule, testé. Il ne
crée aucune VM, aucun service, aucun conteneur et n'installe aucun paquet ou droit.
Il ne lance jamais les opérations sensibles de la matrice de qualification.

## Exécuter le précontrôle

Depuis le checkout, avec les dépendances du projet déjà installées :

```sh
.venv/bin/python scripts/qualification_preflight.py --profile all --language fr
```

Le JSON est écrit sur la sortie standard. Pour conserver un rapport privé :

```sh
mkdir -m 700 qualification-reports
.venv/bin/python scripts/qualification_preflight.py --profile systemd --language en --output "$PWD/qualification-reports/preflight.json"
```

Le dossier doit déjà exister, appartenir au compte et avoir le mode 0700. Le rapport
est un nouveau fichier 0600 ; un fichier existant ou un lien n'est jamais écrasé.
Un chemin absolu est exigé. qualification-reports/ est ignoré par Git : les rapports
locaux de machine ne sont pas publiés automatiquement.

Profils : systemd, docker, podman ou all (par défaut). Les profils moteurs exigent
respectivement --docker-socket et --podman-socket, avec chemins absolus de sockets
Unix existantes, fournis explicitement. Les variables d'intégration de l'application
et les emplacements habituels ne sont pas réutilisés implicitement. Le profil
systemd ne contacte aucun moteur.

Codes de sortie :

| Code | Sens |
| --- | --- |
| 0 | Prérequis du profil observés, pas qualification des opérations |
| 2 | Prérequis absents/inconnus, ou arguments invalides |
| 3 | Impossible d'enregistrer un nouveau rapport privé |

Même avec le code 0, qualified=false et system_execution_enabled=false restent
obligatoires. Aucun endpoint, drapeau ou variable ne permet de convertir le rapport
en droit d'exécution. Un rapport n'est pas une attestation signée ou une approbation.

## Contrôles réalisés

- Compte non root, distribution ID=debian et Python au moins 3.11.
- Détection --vm positive et --container négative, outils accessibles et résultats
  reconnus. Une détection absente/ambiguë bloque au lieu de supposer une VM.
- systemd en PID 1, état exactement running et version numérique lisible.
- Révision Git identifiable et checkout sans modification locale, y compris fichiers
  non ignorés ; aucun verrou optionnel Git ou rafraîchissement d'index demandé.
- Pour les profils choisis : GET /version sur chaque socket explicite, négociation
  de l'API compatible déjà utilisée par le projet et version numérique expurgée.

Les moteurs ne sont pas contactés si un contrôle de base échoue. Aucun inventaire,
log ou inspect de conteneur n'est demandé. Une API compatible ne prouve pas à elle
seule la famille réelle Docker/Podman ni la disponibilité de chaque opération.
Aucune permission de socket n'est élargie, aucun groupe n'est ajouté. L'opérateur
reste responsable d'indiquer un moteur de confiance dans la VM de test.

Les commandes sont une liste fixe de lectures sous /usr/bin, sans shell ni verbe
libre : systemd-detect-virt, systemctl is-system-running/--version et Git rev-parse/status.
Chaque commande est limitée à deux secondes, stdout/stderr à 4 Kio chacun. Les
processus de lecture démarrent dans un groupe isolé ; un délai ou dépassement
nettoie ce groupe, y compris un descendant gardant un flux ouvert après sortie du
parent. Les moteurs disposent de deux secondes et les réponses de la lecture
partagée restent bornées à 2 Mio, sans redirection ou proxy d'environnement.

Le rapport de schéma v1 n'exporte que profil, date UTC, commit, versions numériques,
contrôles et codes stables. Pas de nom de machine, utilisateur, chemin de socket,
adresse, liste de ressources, sortie brute, secret ou jeton. Les libellés sont FR/EN.
L'enregistrement refuse un rapport de plus de 16 Kio.

## Ce qu'il faut préparer pour les essais réels

1. Une VM Debian **jetable** choisie par l'opérateur, avec instantané et procédure de
   destruction/restauration, sans données personnelles ou volumes hôte partagés.
   La détection de virtualisation ne prouve pas qu'une VM est jetable ou sans valeur.
2. systemd et, selon le profil, Docker/Podman installés et configurés par l'opérateur.
   Ce kit ne fournit pas d'installateur ni d'élévation. Les versions relevées doivent
   être jointes au dossier de qualification ; aucune version Debian n'est déclarée
   qualifiée par le seul ID détecté.
3. Un checkout propre à la révision examinée, les dépendances déjà présentes, et les
   sockets de test explicitement autorisées en lecture avec leurs permissions existantes.
4. Revue distincte des vrais pilotes bornés, de la preuve d'approbation et des comptes
   de moindre privilège avant d'autoriser un quelconque start/stop/restart réel.

La [matrice bloquante](EXECUTOR_QUALIFICATION.md) reste à remplir avec systemd et
moteurs réels, résultats attendus/observés, audit corrélé et traces d'échecs partiels.
Les pilotes de fixtures ne doivent pas être remplacés silencieusement par un pilote
hôte pour accélérer cette étape. Un précontrôle vert ne valide ni cette matrice,
ni les permissions privilégiées, ni la santé métier d'une application.

## Validation du kit

25 tests supplémentaires : refus des faits absents/ambigus, profils et sockets
explicites, commandes en liste blanche, absence de contact moteur si environnement
bloqué, rapport FR/EN et expurgé, sauvegarde privée sans écrasement, limites des
processus et GET réel sur socket Unix de fixture. Le nettoyage des descendants
est exercé avec des processus Python contrôlés, sans commande système de mutation.

```sh
.venv/bin/pytest -q backend/tests/test_qualification_preflight.py
```

Total : 465 tests backend et 26 frontend passants, lint/types/format/build passants.
Les succès de tests utilisent des faits de VM et moteurs contrôlés. Ils ne sont
pas enregistrés comme qualification réelle de ce poste ou d'une VM disponible.
