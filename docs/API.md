# API v0.1 — préfixe /api/v1

Toutes les routes API exigent `Authorization: Bearer <jeton>`.
Les seules méthodes acceptées sont GET et HEAD (HEAD seulement sur les routes
qui le prennent en charge). Aucune méthode d'écriture n'est disponible.

| GET | Résultat |
| --- | --- |
| /health | version et indicateur read_only |
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
code, message et correlation_id. Les erreurs de validation des paramètres utilisent
encore le format 422 FastAPI : l'unification et les schémas de sortie typés sont
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
