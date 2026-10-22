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
