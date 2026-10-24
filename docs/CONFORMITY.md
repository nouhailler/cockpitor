# Rapport de conformité — prototype 0.1.0

Ce rapport couvre les lots demandés : surveillance système et interface, puis IA,
puis inventaire conteneurs. Il ne déclare pas l'achèvement de la version 1.0.

| Critère P0 | État | Preuves et limites |
| --- | --- | --- |
| 1. Paquet Debian | ABSENT | installation depuis les sources uniquement |
| 2. systemd et redémarrage machine | ABSENT | lanceur utilisateur, pas d'unité livrée |
| 3. Écoute loopback | IMPLÉMENTÉ | scripts/serve.py fixe 127.0.0.1 ; démarrage local observé |
| 4. CPU/RAM/disque/uptime/réseau | IMPLÉMENTÉ | backend/app/system.py, frontend/src/main.tsx ; test_system.py et navigateur réel |
| 5. Données indisponibles explicites | IMPLÉMENTÉ | première mesure null, capteurs absents et statuts d'intégration ; tests système et frontend |
| 6. Isolation des erreurs de module | PARTIEL | modules optionnels tolèrent les erreurs HTTP attendues ; protocole de module général encore absent |
| 7. Ollama et modèles | IMPLÉMENTÉ | integrations.py, vue IA, tests d'intégration et service Ollama local observé |
| 8. OpenWebUI | PARTIEL | état HTTP et lien implémentés ; instance réelle configurée NON TESTÉE |
| 9. Conteneurs en lecture seule | PARTIEL | inventaire, détails, statistiques et logs avec opt-in ; tests simulés et transport Unix contrôlé ; moteurs réels NON TESTÉS |
| 10. Journaux bornés et rendus sûrs | PARTIEL | journaux systemd et conteneurs reliés de bout en bout, bornés et testés ; journal applicatif dédié absent, lecture réelle réussie NON TESTÉE faute de droits |
| 11. Pas de shell arbitraire | IMPLÉMENTÉ | sous-processus systemctl/journalctl avec arguments fixes et unités validées ; aucun endpoint de commande libre |
| 12. Mutations désactivées | IMPLÉMENTÉ | middleware refuse les mutations système ; réglages, sessions, diagnostic et IA protégés ; test_api.py |
| 13. Secrets et diagnostic | PARTIEL | champs conteneur en liste blanche, erreurs expurgées ; export confirmé par liste blanche implémenté et testé ; revue exhaustive NON TESTÉE |
| 14. Hors ligne après installation | PARTIEL | assets locaux et IP loopback seules ; essai avec réseau coupé NON TESTÉ |
| 15. Tests et build CI | PARTIEL | contrôles locaux passants ; CI précédente documentation réussie ; tranche L0–L3 à vérifier après publication |

## Validations exécutées

- `ruff check backend scripts` : réussi.
- `ruff format --check backend scripts` : réussi.
- `mypy backend/app` : réussi.
- `pytest -q` : 179 tests réussis, un avertissement de dépréciation TestClient/httpx.
- `npm run lint --prefix frontend` : réussi, TypeScript strict.
- `npm run format:check --prefix frontend` : réussi.
- `npm test --prefix frontend` : 26 tests réussis.
- `npm run build --prefix frontend` : réussi.
- `npm audit --prefix frontend` : zéro vulnérabilité après mise à jour de Vitest.

Les premiers tests API étaient bloqués par le bac à sable au démarrage du portail
inter-threads de TestClient ; ils passent hors de cette restriction. Un test
supplémentaire a révélé une course dans la fixture avec les collectes réelles :
la fixture utilise maintenant des adaptateurs simulés déterministes.

Vérification navigateur : tableau système alimenté, rendu responsive à environ
700 px, modèles Ollama locaux, états de sockets absents, processus et recherche.
Les tests HTTP n'utilisent pas les services réellement installés.

## Fichiers créés

- Racine : README.md, CHANGELOG.md, pyproject.toml, requirements.lock, .gitignore.
- Backend : backend/app/{__init__,main,system,integrations}.py.
- Tests backend : backend/tests/test_{api,system,integrations}.py.
- Frontend : frontend/package.json, package-lock.json, tsconfig.json, index.html,
  src/{bootstrap,main}.tsx, src/style.css, tests/app.test.tsx.
- Exécution et CI : scripts/serve.py, .github/workflows/ci.yml.
- Documentation : docs/{IMPLEMENTATION_PLAN,CONFORMITY,ARCHITECTURE,SECURITY,
  INSTALL,API,TESTING,USER_GUIDE}.md.

Le cahier des charges original est conservé sans modification. Les dépendances
installées et le build local sont générés et exclus du suivi par .gitignore.

## Revue de sécurité et suites

Aucun chemin d'arrêt, redémarrage ou élévation de privilèges. Aucun accès moteur
activé pendant la vérification réelle. Les contrôles hôte/origine/authentification,
la limitation des réponses, le refus des redirections, l'exclusion des variables
d'environnement et le rendu textuel sont couverts par les tests disponibles.

Avant distribution : sessions avec expiration, limitation des tentatives,
formalisation des modules et schémas API, validation Debian/systemd, tests réels
moteurs/OpenWebUI, journalisation contrôlée, audit Python et revue de charge.
Les actions sensibles restent interdites avant conception et validation dédiées.

## Lot Services — 23 octobre 2026

Fichiers ajoutés : backend/app/services.py, backend/tests/test_services.py,
frontend/src/api.ts, frontend/src/services.tsx, frontend/tests/services.test.tsx,
docs/images/services.jpg. Main backend/frontend, styles, tests API, README,
CONTEXT, CHANGELOG et guides mis à jour.

IMPLÉMENTÉ : inventaire des services système chargés, recherche/pagination/filtres,
détail et journaux par unité, limites de sous-processus, refus des permissions,
masquage courant, rendu textuel, refus des mutations. PARTIEL : couverture complète
des journaux et secrets arbitraires. ABSENT : journal applicatif dédié et inventaire
des fichiers de services non chargés. NON TESTÉ : journal réel accessible à ce compte.

Validation réelle : 132 unités trouvées, propriétés de dbus.service affichées,
refus de lecture journald expliqué dans l’interface sans modification des droits.
La CI du commit initial était réussie avant ce lot ; les résultats de ce lot
sont vérifiés localement puis soumis au workflow à la publication.

## Complément Conteneurs — 23 octobre 2026

Fichiers ajoutés : backend/app/containers.py, backend/app/redaction.py,
backend/tests/test_containers.py, frontend/src/containers.tsx, frontend/src/format.ts,
frontend/tests/containers.test.tsx et docs/images/containers.jpg. Adaptateur d’inventaire,
routes API, masquage services, vues principales, tests et documentation mis à jour.

IMPLÉMENTÉ : détails en liste blanche, calcul CPU/RAM documenté, logs TTY/multiplexés,
limites de volume/temps/concurrence, identifiants et version négociée, interface et
refus des mutations. PARTIEL : compatibilité des moteurs selon leurs versions et
pilotes de logs, masquage arbitraire. ABSENT : actions, terminal, pagination des logs
conteneurs (dernières lignes bornées uniquement). NON TESTÉ : Docker/Podman réels.

Les 75 tests backend et 9 frontend passent localement, avec lint, types, format et
build. L’avertissement TestClient/httpx préexistant reste présent. Le transport Unix
est vérifié contre un serveur contrôlé ; aucun droit système ou socket moteur réel
n’a été activé. Le navigateur affiche honnêtement « Socket non détecté » pour les
deux moteurs. La prochaine étape du plan concerne la persistance et les alertes.

## SQLite et alertes — 23 octobre 2026

Fichiers ajoutés : backend/app/{preferences,storage,alerts}.py,
backend/tests/test_storage_alerts.py, frontend/src/preferences.tsx,
frontend/tests/preferences.test.tsx et captures settings.jpg/alerts.jpg.
Main API/UI, client HTTP, styles, tests API, exclusions Git et guides mis à jour.

IMPLÉMENTÉ : préférences SQLite, migration initiale privée avec sauvegarde,
schémas stricts, règles locales temporisées, événements actifs/résolus et audit
bornés, récupération après erreur, formulaire connecté et protection d’écriture.
PARTIEL : modèle d’authentification encore fondé sur un jeton de développement,
audit minimal sans interface dédiée. ABSENT : actions
système. NON TESTÉ : migration depuis une ancienne version livrée (aucune version
SQLite précédente n’existe), disque physiquement plein et scénarios de coupure électrique.

Les 109 tests backend et 18 frontend passent, ainsi que lint, types, format et build.
Le navigateur a confirmé un enregistrement dans la base réelle et l’observabilité
sur les métriques du poste. Aucune alerte fictive n’a été créée dans cette base.
Les fichiers SQLite locaux restent privés et exclus du commit. Les durées en
attente repartent après redémarrage ; les événements persistés évitent les doublons.

## Diagnostic et langues

109 tests backend et 18 frontend : confirmation stricte, authentification/origine/
CSRF, tailles, cadence, liste blanche avec marqueurs sensibles, panne SQLite,
rétrocompatibilité des préférences, parité des catalogues et formats régionaux.
Téléchargement réel et restauration de la langue anglaise vérifiés dans le navigateur.
Les noms et journaux externes restent dans leur langue source.

## Tranche L0–L3 livrée

Architecture par domaine, erreurs HTTP unifiées, sessions révocables/expirables et
limites de connexions, manifeste sans actions système et audit consultable.
Supervision complémentaire selon outils/droits, historique minute/sept jours et
assistant Ollama sans outils/exécution, contexte consenti et conservation facultative.
138 tests backend et 22 frontend passants ; échange et réponse IA réels observés.
SMART/NVIDIA/NUT non qualifiés sur matériel réel ; routes IPv4, écoutes IPv4/IPv6.
Le diagnostic conserve sa liste blanche et exclut conversations et informations réseau.
MFA, multi-utilisateurs, accès distant, exécution d’actions et packaging restent absents.

## L4 — 24 octobre 2026

Socle de plans/approbations livré en simulation et relié à l’UI FR/EN, 179 tests
backend et 26 frontend. Cycle réel sur cron.service sans mutation. Les tests du
moteur et de l’audit ne constituent pas une qualification d’exécuteur privilégié :
revue et essais en VM avant L5 toujours requis. Aucun endpoint d’exécution réelle.
Les secrets de configuration sont représentés par HMAC ; aucun token/cible/instantané
persisté dans le nouvel historique minimal. Détails : ACTIONS_SECURITY.md.
