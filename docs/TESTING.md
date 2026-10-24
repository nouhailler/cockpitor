# Vérification

```sh
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
.venv/bin/mypy backend/app
.venv/bin/pytest -q
npm run lint --prefix frontend
npm run format:check --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
npm audit --prefix frontend
```

Les tests API utilisent TestClient et les tests d'intégration HTTP utilisent
MockTransport : aucun service cloud, clé ou moteur réel requis. La collecte psutil
est aussi vérifiée sur l'hôte Linux. Les tests frontend utilisent jsdom.
Un environnement qui bloque les réveils inter-threads peut empêcher TestClient
de démarrer ; dans ce cas exécuter les tests dans un environnement local normal.

Vérifications manuelles : jeton requis, tableau système alimenté, navigation,
états optionnels, affichage mobile, recherche de processus, absence de boutons
sensibles. Le navigateur a confirmé le tableau réel et les modèles du service
Ollama local ; aucun accès moteur réel n'a été configuré pour les tests.

Restent à tester : Debian propre, systemd, moteurs réels Docker/Podman, OpenWebUI
configuré, accessibilité exhaustive, charge et installation/désinstallation Debian.
La CI est fournie mais son exécution distante n'est pas attestée par les tests locaux.

## Lot Services — 23 octobre 2026

41 tests backend et 6 tests frontend réussis. Tests supplémentaires : validation
anti-injection des unités/curseurs, sélection des propriétés, pagination, recherche
littérale, secrets connus, refus de permissions, timeout, limites de sortie,
concurrence et nettoyage des processus annulés. Les limites de sous-processus sont
exercées avec de vrais processus Python substitués aux commandes système de test.
Les tests de l’API utilisent un inventaire simulé et n’interrogent pas l’hôte.

Dans le navigateur réel : 132 services détectés, détail de dbus.service affiché,
refus du journal explicitement visible. Un journal réel lisible n’a pas été testé
avec les permissions actuelles. Capture : docs/images/services.jpg.

## Complément Conteneurs — 23 octobre 2026

75 tests backend et 9 tests frontend. Cas ajoutés : identité et liste blanche
d’inspection, moteurs Docker/Podman, versions négociées/incompatibles, unités CPU/RAM,
absence de référence CPU, formats de logs TTY et multiplexés avec fragments, limites
et erreurs 403/404/409/501, réponses invalides/volumineuses/lentes, absence de socket,
saturation et libération des opérations, validation des routes et refus des mutations.
Un vrai serveur HTTP sur socket Unix de test valide le transport de bout en bout.
Les tests jsdom vérifient sélection, filtres, ressources, rendu sûr des logs et
indépendance d’une panne des statistiques.

Vérification navigateur : états Docker/Podman absents et filtres accessibles,
sans invention de conteneur ni activation de socket. Capture docs/images/containers.jpg.
Les moteurs réels, pilotes de logs, contextes rootless et versions distribuées restent
NON TESTÉS sur cette machine. Les doubles de test sont confinés aux tests.

## SQLite et alertes — 23 octobre 2026

97 tests backend et 13 tests frontend. Tests ajoutés : réouverture persistante,
permissions privées, liens symboliques, sauvegarde pré-migration, refus de version
future, verrouillage SQLite, conservation du réglage précédent après échec,
validation stricte, seuils temporisés, déduplication/reprise, source périmée,
observabilité, résolution après modification et rétention qui conserve les actifs.
Les tests API isolent la base dans un dossier temporaire et vérifient Bearer,
origine, CSRF, JSON, taille de corps, champs refusés et disponibilité des métriques.
Les tests jsdom couvrent sauvegarde réelle du formulaire via PUT, erreurs,
relance de lecture, filtres/pagination des alertes et rendu textuel sûr.

Vérification navigateur : lecture et enregistrement des réglages réels confirmés,
page Alertes sans événement inventé, observabilité des quatre règles initiales sur
les mesures du poste. Captures docs/images/settings.jpg et docs/images/alerts.jpg.
Les scénarios d’activation/résolution forcés sont limités aux tests contrôlés.

## Diagnostic et multilingue

Validation actuelle : 109 tests backend et 18 frontend. La suite couvre liste
blanche et exclusion des marqueurs sensibles, sources absentes, panne SQLite,
confirmation stricte, CSRF/origine/jeton, limites et cadence, paramètres fr/en,
compatibilité des anciennes préférences, parité des catalogues et unités locales.
Dans le navigateur : anglais restauré après rechargement, export téléchargé après
confirmation et audit affiché. Les moteurs réels restent à qualifier séparément.

## Tranche L0–L3

138 tests backend et 22 frontend. Nouveaux scénarios : échange du jeton et refus du
bootstrap pour les données, expiration sans prolongation par polling, durée absolue,
révocation/rejeu, limites de connexions, CSRF/origine, audit paginé, migration v1/v2
sauvegardée, rétention bornée, classification IPv4/IPv6/multicast, sondes absentes,
réponses simulées SMART/NVIDIA/APT, isolement des collecteurs, contexte lié à la
session et expirant, consentement et conservation IA, annulation/concurrence,
refus des redirections/sorties trop grandes/réponses incomplètes et HTML échappé.

Navigateur réel : connexion, supervision et réponse qwen2.5:3b depuis Ollama local,
sans conservation de la conversation de validation. Les scénarios de succès
SMART/GPU/NUT restent simulés ; matériel réel compatible non disponible sur ce poste.
Un avertissement Starlette/TestClient reste préexistant, non bloquant.

Validation complémentaire réelle : après redémarrage, l’ancienne session retourne à
la connexion ; déconnexion confirmée ; assistant FR/EN ; affichage à 390 px sans
débordement du document, après correction de la grille mobile. Le contrôle /api/show
précède désormais chaque prompt ; le refus des modèles cloud avant transmission
du texte est couvert par un test dédié.

## L4 — simulations contrôlées

179 tests backend et 26 frontend passants. test_actions.py couvre types/injections,
unités critiques, confirmations non booléennes, sessions étrangères/révoquées,
empreintes/cibles/configurations modifiées, échéance pendant préflight, rejeu,
concurrence, annulation, timeout, quotas, audit absent et rollback SQL, reprise et
migration v2 sauvegardée. Les adaptateurs vérifient le masquage HMAC et les seuls GET moteur.
Les tests frontend imposent examen/confirmation, absence de token dans DOM/storage,
invalidation sur erreur, annulation et anglais. Parcours navigateur réel cron.service
préparé/approuvé/simulé, sans redémarrage. Aucune VM d’exécution privilégiée qualifiée.
Voir ACTIONS_SECURITY.md pour la portée exacte des preuves.

## Préparation L5 — 24 octobre 2026

`backend/tests/test_executor_protocol.py` ajoute 24 tests : droits positifs, UID,
trames strictes/bornées, expiration, consommation sur échec, état/configuration,
rejeu, redémarrage et saturation sans éviction. Total : 203 backend et 26 frontend.
Ces tests ne lancent aucune opération système et ne qualifient pas le transport
Unix ou les futurs adaptateurs. Voir [la matrice restante](EXECUTOR_QUALIFICATION.md).

## Transport de vérification L5 — 24 octobre 2026

Total actuel : **236 tests backend et 26 frontend**, Ruff/format/mypy passants.
`test_executor_transport.py` ajoute 32 tests sur sockets Unix locales : UID lu du
noyau, refus avant sonde, droits/champs non autorisés, trames invalides ou lentes,
taille annoncée avant réception du corps, rejeu concurrent, délais/erreurs des
sondes, configuration modifiée, saturation et fermeture avec annulation.
Les chemins existants ou symboliques sont conservés ; root, permissions trop
ouvertes et absence de SO_PEERCRED sont refusés. Un test de politique supplémentaire
couvre l'invalidation après consommation et avant comparaison de l'instantané.
Ces tests nécessitent un environnement Linux non root autorisant AF_UNIX ; ne pas
confondre une interdiction du bac à sable avec un défaut du protocole. Aucune
mutation de service/conteneur n'est réalisée. La matrice VM demeure à compléter.
