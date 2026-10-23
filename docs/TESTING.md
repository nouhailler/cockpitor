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
