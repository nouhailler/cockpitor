# Contexte du projet — Cockpitor

## Objectif

Construire un cockpit personnel pour un poste Debian, accessible depuis un
navigateur local, sans cloud ni télémétrie. Le nom du dépôt est **Cockpitor** ;
l’interface et les variables de configuration utilisent actuellement le nom de
travail **LocalCockpit**. Le cahier des charges de référence est
[docs/cahier_des_charges_localcockpit_debian.md](docs/cahier_des_charges_localcockpit_debian.md).

## Priorités validées

1. Développer la surveillance système et l’interface.
2. Ajouter les intégrations IA locale.
3. Ajouter les conteneurs.
4. N’autoriser les opérations sensibles qu’après validation des protections et des tests.

La version actuelle est un **prototype 0.1.0 en lecture seule**, pas le MVP Debian complet.

## État actuel

| Domaine | État |
| --- | --- |
| Interface | React, TypeScript strict, Vite ; responsive, thèmes clair/sombre |
| Backend | FastAPI, lanceur non root, port 8765 sur 127.0.0.1 |
| Système | CPU, RAM, swap, uptime, charge, réseau, stockage, processus et capteurs accessibles |
| Historique | Jusqu’à 450 points en mémoire, environ 15 minutes |
| IA | Modèles Ollama, modèles chargés si disponibles, état HTTP/lien OpenWebUI |
| Conteneurs | Inventaire Docker/Podman via socket explicitement configuré |
| Mutations | Absentes ; méthodes d’écriture refusées par le middleware |
| Persistance et packaging | SQLite, alertes, diagnostic et paquet Debian absents |

## Décisions à préserver

- Frontend et API sont servis sous une même origine, sans ressources tierces.
- L’accès API exige un jeton conservé uniquement en mémoire par le frontend.
- Le lanceur fixe l’écoute loopback et refuse root.
- Les appels API lisent des instantanés partagés ; ils ne relancent pas les collectes.
- Les URL d’intégration acceptent seulement des IP loopback numériques.
- Aucun shell arbitraire, aucun agent privilégié, aucun élargissement automatique des droits.
- L’accès Docker reste une frontière de confiance importante et exige une activation explicite.
- Aucune donnée absente ne doit être remplacée par une valeur fictive.
- Les erreurs d’intégration ne doivent pas empêcher la surveillance système.

## Carte du code

- `backend/app/main.py` : cycle de vie, routes, authentification, hôtes/origines et headers.
- `backend/app/system.py` : collecte système et référence des mesures différentielles.
- `backend/app/integrations.py` : lectures HTTP bornées et adaptateurs optionnels.
- `frontend/src/main.tsx` : vues, client API et rafraîchissement.
- `frontend/src/style.css` : thèmes et mise en page responsive.
- `scripts/serve.py` : lancement utilisateur et génération du jeton.
- `requirements.lock` et `frontend/package-lock.json` : dépendances résolues.
- `.github/workflows/ci.yml` : lint, types, tests, build et audit npm.

## Validation connue

- 19 tests backend et 4 tests frontend réussis localement.
- Ruff, mypy, TypeScript, Prettier et build frontend passants.
- Audit npm sans vulnérabilité signalée lors de la préparation initiale.
- Tableau système, recherche de processus et modèles Ollama vérifiés dans un navigateur.
- Capture réelle versionnée dans `docs/images/dashboard.jpg`.

Les tests API sont isolés des services réellement installés. Dans l’environnement
de développement initial, le bac à sable bloquait le portail inter-threads de
TestClient ; la suite passait dans un environnement local normal. Un avertissement
de dépréciation Starlette/TestClient concernant httpx reste présent.

## Limites et prochaines décisions

- Choisir et tester la version Debian cible dans une VM propre.
- Remplacer le jeton de développement par des sessions expirables, avec limitation des tentatives.
- Compléter les schémas de sortie API, l’enveloppe d’erreur et le contrat de modules.
- Ajouter détails/statistiques/logs conteneurs et services/journaux en lecture seule.
- Tester Docker, Podman et OpenWebUI sur des instances réelles configurées.
- Ajouter audit des dépendances Python, tests de charge et revue d’accessibilité.
- Concevoir packaging, service systemd, migrations et désinstallation.

**Avant toute action sensible :** conception, revue de sécurité, actions typées,
liste blanche, confirmation explicite, audit expurgé, validation des paramètres,
moindre privilège et tests d’abus. Une interface de confirmation seule ne suffit pas.

## Reprendre le développement

Lire d’abord le README, le cahier des charges, le plan et le rapport de conformité.
Travailler par lots vérifiables ; lancer les commandes du
[guide de tests](docs/TESTING.md) après chaque lot. Mettre à jour le plan, le rapport
et le CHANGELOG sans déclarer implémentée une fonction non reliée de bout en bout.

Dépôt : [nouhailler/cockpitor](https://github.com/nouhailler/cockpitor).
