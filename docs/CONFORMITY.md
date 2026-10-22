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
| 9. Conteneurs en lecture seule | PARTIEL | inventaire avec opt-in ; tests simulés Docker, socket Podman ; moteurs réels NON TESTÉS |
| 10. Journaux bornés et rendus sûrs | ABSENT | aucun endpoint ou écran de logs |
| 11. Pas de shell arbitraire | IMPLÉMENTÉ | aucun subprocess ni endpoint de commande ; routes en lecture seule |
| 12. Mutations désactivées | IMPLÉMENTÉ | middleware refuse POST/PUT/PATCH/DELETE ; test_api.py |
| 13. Secrets et diagnostic | PARTIEL | champs conteneur en liste blanche, erreurs expurgées ; export ABSENT, revue exhaustive NON TESTÉE |
| 14. Hors ligne après installation | PARTIEL | assets locaux et IP loopback seules ; essai avec réseau coupé NON TESTÉ |
| 15. Tests et build CI | PARTIEL | contrôles locaux passants ; workflow fourni, exécution distante NON TESTÉE |

## Validations exécutées

- `ruff check backend scripts` : réussi.
- `ruff format --check backend scripts` : réussi.
- `mypy backend/app` : réussi.
- `pytest -q` : 19 tests réussis, un avertissement de dépréciation TestClient/httpx.
- `npm run lint --prefix frontend` : réussi, TypeScript strict.
- `npm run format:check --prefix frontend` : réussi.
- `npm test --prefix frontend` : 4 tests réussis.
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
