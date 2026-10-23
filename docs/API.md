# API v0.1 — préfixe /api/v1

Toutes les routes API sauf auth/options et auth/sessions exigent
`Authorization: Bearer <session>`. Le jeton du lanceur ne donne aucun accès aux données.
Les routes de supervision acceptent GET et, lorsqu’il est pris en charge, HEAD.
Les écritures autorisées couvrent réglages, sessions, diagnostic et assistant IA.
Aucune mutation système n’est disponible. Tous les POST/PUT exigent JSON, origine
locale exacte et X-LocalCockpit-CSRF.

| GET | Résultat |
| --- | --- |
| /health | version, read_only (système), settings_writable et santé du stockage |
| /system/metrics | dernier instantané système hors processus |
| /system/history | au plus 450 échantillons CPU/RAM horodatés |
| /system/processes | items, total, collected_at ; q (100 caractères), offset >= 0, limit 1–200 |
| /ai/status | états Ollama/OpenWebUI, modèles installés et chargés si disponibles |
| /containers | états des moteurs et inventaires accessibles |
| /containers/{engine}/{id} | état et configuration en liste blanche |
| /containers/{engine}/{id}/stats | CPU, mémoire brute, limite mémoire, horodatages |
| /containers/{engine}/{id}/logs | tail 1–200 par flux, period hour/day ; lecture non continue |
| /services | inventaire chargé, recherche q, filtre state (all/active/inactive/failed), offset et limit 1–200 |
| /services/{unit} | propriétés d’état autorisées, démarrage et dépendances disponibles |
| /services/{unit}/logs | limit 1–200, period hour/day, priority 0–7, q littéral, cursor optionnel |

Unités : octets, octets/s, secondes, degrés Celsius et pourcentages.
Les horodatages de collecte sont UTC ISO 8601 ; le navigateur les présente localement.
Une valeur absente est null ou accompagnée d'un statut et d'un message.
Les états d'intégration sont available, unavailable et disabled.
Les états HTTP 503 indiquent la première collecte en cours.

Les erreurs de contrôle d'accès et d'exécution ont une enveloppe error contenant
code, message et correlation_id. Les erreurs de validation des paramètres utilisent la même enveloppe, avec
INVALID_REQUEST et sans valeurs d’entrée. Les schémas de sortie typés exhaustifs restent
à compléter. Les documentations interactives et l'OpenAPI public sont désactivés
pour cette version ; un contrat versionné reste à livrer.

## Services et journaux

Les unités doivent être des noms exacts `.service` (pas de motif, option, chemin
ou commande). Les résultats de l’inventaire sont partagés et actualisés toutes les
dix secondes ; les détails et journaux sont lus à la demande sans mutation.
Les services installés mais non chargés ne figurent pas dans cette première liste.

Les journaux sont triés du plus récent au plus ancien. `next_cursor` permet de lire
la page précédente dans le temps ; null indique la fin. Un curseur disparu retourne
409 CURSOR_EXPIRED. Le filtre q s’applique uniquement aux entrées de la page lue ;
une page sans résultat peut donc avoir une page suivante. `scanned` précise le
nombre d’entrées examinées avant le filtre textuel. Les messages sont du texte,
avec masquage de motifs de secrets connus ; les champs binaires/absents sont indiqués.

La période est limitée à une heure ou 24 heures, le volume à 2 Mio et chaque
commande à cinq secondes. Deux commandes maximum sont exécutées simultanément ;
une saturation retourne 429 BUSY. Les permissions insuffisantes retournent 403,
et les avertissements de visibilité du journal ne sont pas présentés comme une
lecture complète vide. Les données de détail sont une liste blanche de propriétés,
excluant commandes de démarrage et environnement.

## Détails conteneurs

`engine` est docker ou podman ; `id` est un identifiant complet de 64 chiffres
hexadécimaux minuscules. Le socket est configuré uniquement côté lancement.
Toutes les requêtes moteur sont GET sur des chemins fixes via Unix ; aucune URL,
commande ni chemin de socket n’est accepté dans la requête utilisateur.

Négociation : lecture de /version puis sélection de min(ApiVersion, 1.47), si cette
version respecte MinAPIVersion et le plancher 1.24. Une réponse non compatible est
refusée. L’inventaire utilise aussi le préfixe négocié.

Les détails contiennent id, engine, name, image, created, state, tty et collected_at.
Les champs Env/Cmd/Labels/Mounts ne sont pas retournés. Le CPU en % utilise les
deltas cpu_stats/precpu_stats et online_cpus (ou percpu_usage) ; il est null si la
référence manque ou si les compteurs sont invalides. memory_usage_bytes est brute,
cache inclus ; memory_limit_bytes vient du moteur et ne représente pas la RAM de
l’hôte. sample_at est l’horodatage moteur s’il est fourni, collected_at celui de lecture.

Les journaux sont décodés selon Config.Tty. Les trames stdout/stderr sont assemblées
par flux avant masquage et découpage. items contient stream/message ; au plus tail
lignes par flux, donc 2 × tail au maximum. ordering vaut grouped_by_stream : aucun
ordre inter-flux n’est garanti. Sans TTY, un format de trame incompatible est une
erreur ; avec TTY, le flux fusionné est affiché comme stdout. Pas de follow ni pagination.

Limites : deux opérations détaillées concurrentes, délai total de six secondes,
2 Mio par réponse et deux secondes d’inactivité HTTP. Saturation : 429 BUSY ;
accès désactivé : 409 ENGINE_DISABLED ; absence API/conteneur : 404 ; permissions :
403 ; statistiques incompatibles avec l’état : 409 ; fonction absente : 503.
Toutes les erreurs publiques sont expurgées ; aucune mutation n’est disponible.

## Préférences et alertes

GET /settings retourne settings, csrf_token et storage (status/schema_version).
PUT /settings remplace l’objet settings complet et retourne operation_id, status
completed et les réglages réellement enregistrés. Champs autorisés : theme
(dark/light/system), refresh_seconds (entier 3–60), retention_days (1–90), rules
(20 maximum, identifiants uniques). Champs inconnus et types non conformes sont refusés.

Les règles définissent id, metric, enabled, threshold (0–100), duration_seconds
(0–3600), severity (warning/critical), target et engine. metric est cpu_percent,
memory_percent, swap_percent, disk_free_percent, ollama_unavailable, service_failed
ou container_stopped. Une cible est requise pour disque/service/conteneur ; engine
est autorisé seulement pour un conteneur. Les conditions booléennes ignorent threshold.
Les comparaisons sont strictes : supérieur pour CPU/RAM/swap, inférieur pour libre disque.

PUT exige Bearer et Origin correspondant exactement à l’origine de la requête,
Content-Type application/json et X-LocalCockpit-CSRF égal au jeton du GET authentifié.
Le corps réellement lu est limité à 16384 octets (413 au-delà). CSRF/origine refusée :
403 ; contenu non JSON : 415 ; configuration invalide : 422 expurgé ; stockage : 503.
Un succès correspond au commit atomique des réglages et de l’audit, pas à une simple
acceptation en mémoire. Les tokens ne sont pas stockés dans SQLite.

GET /alerts : status=all/active/resolved, limit 1–200 (50 par défaut), offset >= 0.
Réponse items/total pour les événements, rules pour l’observabilité courante et
evaluated_at pour l’heure de dernière évaluation. rules.status : healthy, pending,
active, unavailable ou disabled. Le champ active permet de distinguer une source
indisponible avec événement actif conservé. Les événements contiennent identifiant,
règle, gravité, message, état, début et résolution. Pas d’acquittement ni notification externe.

La santé conserve read_only=true au sens des ressources système et annonce
settings_writable=true. Une base indisponible ne rend pas /health ou les métriques inaccessibles.

## Diagnostic et langue

GET /diagnostics/options retourne les informations de confidentialité et le jeton
CSRF, même si SQLite est indisponible. POST /diagnostics exige Bearer, origine
locale exacte, application/json, X-LocalCockpit-CSRF et exactement
`{"confirmed": true}`. Corps limité à 1024 octets ; délai global de cinq secondes
entre générations (429). Réponse JSON pièce jointe, 64 Kio maximum, sans logs ni
identités, construite à partir des instantanés existants. X-Diagnostic-Audit vaut
recorded ou unavailable. Le schéma du rapport reste stable et indépendant de la langue.

Preferences.language accepte fr/en (fr par défaut pour les anciennes données).
Accept-Language choisit les messages d’erreur structurés, avec repli fr ;
Content-Language et Vary sont renvoyés. Codes d’erreur et états restent stables.

## Sessions

1. GET /auth/options, public mais soumis aux contrôles Host/Origin : csrf_token et durées.
2. POST /auth/sessions avec `{"token":"jeton du lanceur"}` ; corps 1 Kio maximum.
   Retour : token de session aléatoire, csrf_token, idle_seconds=900, absolute_seconds=28800.
3. Utiliser ce token en Bearer pour les autres routes ; rien en cookie/URL/localStorage.
4. POST /auth/activity, session + CSRF : marque une interaction réelle. Les GET ne
   prolongent pas l’inactivité. POST /auth/logout révoque et annule la génération associée.

Dix tentatives de connexion globales/minute, succès inclus ; 429 à saturation.
Maximum 32 sessions ; les sessions expirées sont purgées avant nouvelle connexion.
Au redémarrage aucune session ne survit. La récupération locale consiste à utiliser
le jeton du terminal, ou à redémarrer le lanceur sous le même compte système.
Le frontend renvoie vers la connexion sur 401 et signale une session expirée.

## Modules, audit et supervision

- GET /modules : manifeste des capacités, system_actions=false pour chaque module.
- GET /audit : limit 1–200, offset >=0 ; items(id/action/timestamp), total. Historique de 1000 opérations.
- GET /system/inspection : dernière inspection partagée, collected_at et sections
  indépendantes. Collecte toutes les 60 s après la fin de la précédente ; anciennes
  données conservées avec leur date si échec. Outils : quatre secondes, 512 Kio stdout,
  8 Kio stderr, environnement fixe, aucun shell ou sudo. Aucun scan réseau actif.
- GET /system/trends?hours=24 : hours 1–168, items CPU/RAM horodatés, rétention sept jours,
  une mesure/minute et 10080 points maximum. 503 si stockage indisponible.

Les sections d’inspection précisent leurs limites : GPU NVIDIA seulement, routes
IPv4, écoute IPv4/IPv6 sans preuve d’exposition externe, cache APT non actualisé,
quatre disques SMART et quatre onduleurs d’un serveur NUT local existant maximum.
Un outil absent ou refusé ne déclenche aucune installation ni changement de droits.

## Assistant IA local

- POST /ai/context : capture numérique CPU/RAM/swap, source/horodatage/fraîcheur et
  context_id lié à la session, valable cinq minutes ; 32 aperçus maximum en mémoire.
- POST /ai/chat : JSON 64 Kio maximum ; model existant dans le dernier inventaire,
  prompt (1–4000 caractères), thread_id optionnel, context_id optionnel, retain bool
  (false par défaut), history optionnel (huit messages user/assistant, 4000 caractères chacun).
- Réponse : answer, thread_id (null sans conservation), context et system_actions_enabled=false.
- POST /ai/cancel : annule seulement la génération de cette session.
- GET /ai/threads : 20 conversations les plus récentes ; GET /ai/thread?id=... :
  40 messages maximum. Identifiant : 32 caractères hexadécimaux minuscules.

Une seule génération à la fois, délai minimal cinq secondes entre débuts ; 429 sinon.
Le backend vérifie d’abord POST /api/show (512 Kio maximum, sans prompt), refuse
les modèles distants ou sans métadonnées locales, puis appelle POST /api/chat sur
l’Ollama loopback configuré, sans
redirection/proxy d’environnement/outils, 75 s maximum, réponse HTTP 64 Kio maximum,
texte conservé 16000 caractères maximum et num_predict=1024/num_ctx=8192.
Au plus huit messages précédents, chacun tronqué à 4000 caractères, servent de contexte.
Les observations jointes sont conservées avec la réponse seulement si retain=true.
Le modèle peut se tromper ; aucune commande n’est exécutée. Annulation/déconnexion/
expiration interrompt l’attente, sans garantie de déchargement du modèle côté Ollama.
Les conversations sauvegardées sont communes au compte local, sans isolation multi-utilisateurs.
