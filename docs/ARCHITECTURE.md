# Architecture 0.1

Navigateur → même origine `127.0.0.1:8765` → FastAPI non root → collecteur psutil
et adaptateurs HTTP locaux. FastAPI sert le build React, sans CDN ni service worker.
Le lanceur refuse root et fixe l'adresse loopback. Lancer uvicorn manuellement
avec une autre adresse contournerait ce choix : ce mode n'est pas supporté.

Le collecteur tourne toutes les deux secondes. Les requêtes de métriques consultent son
dernier instantané ; elles ne déclenchent aucune collecte. CPU et réseau exigent
une référence précédente. Le CPU par processus peut dépasser 100 % et est
indisponible pour les nouveaux processus jusqu'à la collecte suivante.
L'historique contient au plus 450 points (environ 15 minutes) en mémoire.
Un échec garde l'horodatage précédent, permettant de signaler les valeurs anciennes.

Les vérifications IA et conteneurs tournent en parallèle, puis attendent dix secondes.
Les lectures HTTP sont limitées en durée et volume ; les réponses sont filtrées
et validées. Seules les informations utiles sont transmises à React. Aucun accès
à l'environnement d'un conteneur ou à une base OpenWebUI.

Cette version utilise SQLite pour les préférences et événements ; elle n’a ni
système de plugins chargeables ni agent privilégié. Les capacités sont annoncées par un manifeste ; aucun plugin chargeable.
Les données de la machine de développement ne prouvent pas la compatibilité
avec une installation Debian propre.

## Services système — 23 octobre 2026

Un adaptateur indépendant inventorie toutes les dix secondes les unités système
chargées de type service. Détails et journaux sont demandés à la sélection, avec
contrôle des unités et limites de ressources. Aucune commande de mutation n’est
accessible. L’inventaire reste accessible si la lecture du journal échoue ; le
collecteur système et les intégrations IA/conteneurs sont indépendants de ce lot.

La sortie `systemctl show` est filtrée par propriétés ; journald utilise JSON et
les curseurs pour remonter dans le temps. La recherche de texte s’effectue sur une
page bornée sans passer d’expression régulière utilisateur au système.
Références : [systemctl](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)
et [journalctl](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html).

## Conteneurs — détails et journaux

L’inventaire reste une collecte périodique partagée. L’inspecteur sélectionné lit
les détails à la demande, les statistiques toutes les cinq secondes après réponse,
et les journaux sur sélection/actualisation/changement de filtre. Un échec des
statistiques n’efface pas les journaux ou le détail. L’accès au socket reste explicite.

Le backend négocie la version de compatibilité, valide l’identité d’inspection et
ne transmet qu’une liste de champs utiles. Les journaux Docker non TTY utilisent
un en-tête de huit octets par trame ; les fragments sont assemblés par flux avant
masquage. Le format brut TTY est traité sans démultiplexage. Aucun flux continu n’est ouvert.
Les fonctions de masquage sont partagées dans redaction.py.

Références vérifiées : [spécification Moby API 1.47](https://github.com/moby/moby/blob/v27.5.1/docs/api/v1.47.yaml),
[formats des journaux Moby](https://github.com/moby/moby/blob/master/client/container_logs.go),
[versionnement Docker](https://docs.docker.com/reference/api/engine/),
[API Podman et compatibilité](https://docs.podman.io/en/latest/_static/api.html).
La qualification des moteurs réels et de leurs différences de versions reste à réaliser.

## Persistance et moteur d’alertes

Le stockage est indépendant des collecteurs. Une connexion SQLite courte est ouverte
par opération, sans fichier temporaire disque ; les transactions protègent réglages,
résolutions associées et audit. Un verrou applicatif sérialise l’évaluation des
règles et les enregistrements. La base garde les préférences JSON, événements et
un audit minimal, aucune métrique haute fréquence ni secret de session. Les tendances minute et conversations facultatives sont décrites ci-dessous.

L’évaluation toutes les deux secondes utilise les instantanés déjà partagés. Les
métriques système ont une fraîcheur maximale de 15 s, les modules optionnels de 40 s.
Une temporisation n’aboutit qu’avec un nouvel échantillon ; un résultat sain résout
un événement actif, une source inconnue le conserve. Les temporisations ne sont pas
persistées et repartent au démarrage ; les événements actifs sont relus pour éviter
les doublons. Modifier/supprimer une règle clôt son événement actif.

Références : [sqlite3 Python](https://docs.python.org/3/library/sqlite3.html),
[validation Pydantic](https://docs.pydantic.dev/latest/concepts/validators/) et
[protection CSRF OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## Architecture modulaire et sessions

main.py conserve le cycle de vie et l’assemblage, routes/ sépare système, intégrations,
réglages, diagnostic, sessions et assistant. security.py centralise les contrôles
HTTP et errors.py l’enveloppe localisée. modules.py expose les capacités explicites,
toutes sans actions système. Les erreurs d’une intégration ne stoppent pas les autres.
Le frontend sépare connexion, types, graphiques, navigation, supervision et assistant.

L’échange du secret d’amorçage ouvre une session opaque hachée en mémoire. L’activité
utilisateur est signalée séparément du polling. Les conversations enregistrées ne
représentent pas des comptes : cette version reste mono-utilisateur local.

## Supervision et persistance v2

monitoring.py inspecte en arrière-plan outils fixes et interfaces psutil/sysfs,
avec limites de temps et sortie. Les requêtes API ne lancent aucune sonde.
SQLite v2 ajoute metric_history, ai_threads et ai_messages, après sauvegarde de la
base antérieure. Rétention CPU/RAM : une mesure/minute, sept jours, 10080 points.
Conversations : vingt fils de quarante messages maximum, uniquement sur choix explicite.
Les graphiques CPU/RAM respectent les dates et interrompent les courbes dans les trous.

## Assistant sans exécution

assistant.py limite Ollama à une génération et à un modèle déjà annoncé. Le contexte
est un instantané minimal, prévisualisé et lié à la session ; les messages du modèle
ne deviennent jamais des opérations. Une vérification locale POST /api/show exclut les modèles distants avant l’envoi
du prompt ; POST /api/chat est ensuite effectué seulement après action utilisateur. Une interruption de session ferme
l’attente de génération ; le modèle peut rester chargé dans Ollama.
Référence : [API Chat Ollama](https://docs.ollama.com/api/chat).

## Socle d’actions en simulation — L4

actions.py orchestre des plans en mémoire liés au hash de session et un cycle
préparation → approbation → simulation → résultat, avec état/audit SQLite atomiques.
La base v3 ajoute seulement action_operations ; les plans/cibles/jetons restent volatils.
L’empreinte HMAC de configuration est produite par les adaptateurs de lecture.
Il n’existe pas de fonction d’exécution système à injecter ou à activer. Les futures
opérations réelles exigeront une architecture de privilèges et une qualification distinctes.
Voir [le modèle et les preuves](ACTIONS_SECURITY.md).

## Préparation L5 : transport de vérification isolé

executor_protocol.py et executor_transport.py sont un banc séparé, sans import dans
les routeurs/lanceur. La politique positive et les tickets sont séparés de la
réception Unix et de l'identité noyau. Le serveur appelle une sonde de confiance,
jamais un snapshot client ; il sérialise sonde et politique. Aucune méthode ne
modifie les ressources. Il n'existe pas de chemin de l'assistant vers ce banc.
Voir [contrat, bornes et qualification restante](EXECUTOR_QUALIFICATION.md).

## Liaison de vérification au moteur L4

ActionEngine expose SimulationVerifier pour le banc, sans injection dans le lanceur.
executor_client.py relie le cycle approuvé/audité au transport v2 ; l'empreinte du
plan est exigée dès issue et retrouvée dans les deux réponses. L'événement
transactionnel actions.transport_verified exige l'état simulating avant le résultat
simulated. Session et échéance sont contrôlées autour des échanges. Le client ne
possède aucune méthode d'exécution. Le serveur n'authentifie pas indépendamment
une approbation humaine ; une future frontière privilégiée exige une revue séparée.
