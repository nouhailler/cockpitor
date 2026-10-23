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
| Conteneurs | Inventaire, filtres, détails, CPU/RAM et journaux bornés via socket explicitement configuré |
| Services et journaux | Inventaire des services chargés, détails, journaux bornés/paginés et permissions explicites |
| Mutations | Aucune action système ; PUT /api/v1/settings protège les seuls réglages applicatifs |
| Persistance | SQLite v1 privé : préférences, événements d’alerte et audit borné des réglages |
| Distribution | Diagnostic et paquet Debian absents |

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
- `frontend/src/main.tsx` : vues et rafraîchissement.
- `frontend/src/api.ts` : client HTTP authentifié avec délai maximal.
- `backend/app/services.py` et `frontend/src/services.tsx` : services et journaux en lecture seule.
- `frontend/src/style.css` : thèmes et mise en page responsive.
- `scripts/serve.py` : lancement utilisateur et génération du jeton.
- `requirements.lock` et `frontend/package-lock.json` : dépendances résolues.
- `.github/workflows/ci.yml` : lint, types, tests, build et audit npm.

## Validation connue

- 97 tests backend et 13 tests frontend réussis localement.
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
- Qualifier le module Conteneurs sur Docker et Podman réels ; ajouter une vue de journaux applicatifs.
- Étendre éventuellement l’inventaire aux fichiers de services installés mais non chargés.
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

## Étape du 23 octobre 2026

Le module Services consulte `systemctl list-units` et une liste limitée de
propriétés de `systemctl show`. `journalctl` lit au plus 202 entrées brutes par
requête, avec une période limitée à une heure ou 24 heures. La recherche de texte
est littérale et locale à la page ; la pagination utilise les curseurs journald.
Les commandes sont sans shell, exécutées avec des chemins absolus, un environnement
fixe, deux lectures concurrentes maximum, un délai de cinq secondes et une limite
de sortie de 2 Mio. Le processus est arrêté et récupéré après dépassement ou annulation.

Sur le poste réel : 132 services détectés, détails de dbus.service consultés,
journal refusé faute de permissions. Aucun changement de droits n’a été effectué.
Les journaux lisibles et leur pagination sont validés par tests simulés ; un compte
réel ayant accès au journal reste à tester. Le masquage couvre les secrets courants,
sans garantir de détecter tous les secrets propres aux applications.

## Complément Conteneurs — 23 octobre 2026

`backend/app/containers.py` et `frontend/src/containers.tsx` relient les détails,
statistiques et journaux à l’inventaire. Les identifiants acceptés sont exactement
64 caractères hexadécimaux minuscules ; aucun nom, préfixe, chemin ou commande libre.
L’API est négociée depuis `/version`, bornée aux versions de compatibilité 1.24–1.47.
Les routes de détail incluent le moteur pour éviter une ambiguïté Docker/Podman.

Inspect est filtré : pas d’environnement, commande, label ou montage. Le CPU est
calculé seulement avec deux compteurs valides, et peut dépasser 100 % sur plusieurs
cœurs. La mémoire est la valeur brute déclarée, cache inclus. Les statistiques
manquantes restent null. Les flux de logs TTY et multiplexés sont traités séparément,
avec reconstitution des trames par flux et masquage commun dans redaction.py.
Les lectures détaillées ont un budget de six secondes et deux opérations simultanées.

Le navigateur vérifie l’absence de moteurs sur ce poste. Les scénarios disponibles,
arrêtés, refusés et incompatibles sont couverts par tests, dont un vrai serveur Unix
HTTP contrôlé (ce n’est pas un moteur réel). Aucun accès moteur ni privilège activé.
Prochaine étape : préférences persistantes et alertes locales, toujours sans actions sensibles.

## Préférences et alertes — 23 octobre 2026

- `preferences.py` définit des schémas stricts : thème, rafraîchissement, rétention,
  maximum 20 règles nommées de façon unique et cibles exactes.
- `storage.py` utilise SQLite v1, transactions, paramètres SQL, délai de verrouillage
  court, permissions 0700/0600 et refus des liens symboliques pour la base/dossier.
  Une base non vide de version 0 est sauvegardée avant initialisation ; les versions
  futures sont refusées sans modification. Les lectures ne recréent pas une base disparue.
- `alerts.py` évalue toutes les deux secondes, avec fraîcheur des sources, durée,
  nouveaux échantillons, déduplication, résolution et reprise des événements actifs.
- Les événements résolus expirent après la rétention choisie, à partir de leur
  résolution, avec plafond de 1000 résolus. Les actifs restent conservés ; l’audit
  des enregistrements est limité à 1000 événements sans corps ni jeton.
- Seul PUT settings est autorisé en écriture : Bearer, origine exacte obligatoire,
  jeton CSRF obtenu via GET authentifié, application/json, corps borné à 16 Kio.
- `frontend/src/preferences.tsx` fournit Paramètres et Alertes ; le thème et la
  fréquence d’affichage système sont appliqués après chargement/enregistrement.
- Le collecteur système a son propre thread unique afin que les lectures SQLite
  n’altèrent pas les références de mesure CPU par thread de psutil.

Le répertoire privé par défaut est `.localcockpit/` à la racine ; il est ignoré par
Git et ne doit pas être commité. Le nom peut être remplacé au lancement par
LOCALCOCKPIT_DATA_DIR. Une panne de base est signalée et réessayée en arrière-plan,
sans bloquer les autres modules. Le diagnostic expurgé reste la prochaine étape.
