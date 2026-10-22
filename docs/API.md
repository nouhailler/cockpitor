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
