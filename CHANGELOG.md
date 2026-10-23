# Historique — Cockpitor

## Non publié

### Préférences et alertes — 23 octobre 2026

- SQLite v1 privé, initialisation/migration avec sauvegarde, préférences et audit borné.
- Pages Paramètres et Alertes, thèmes clair/sombre/système et fréquence d’affichage persistants.
- Règles temporisées CPU/RAM/swap/disque, Ollama indisponible, service en échec et conteneur arrêté.
- Déduplication, résolution, rétention des événements et sources indisponibles explicites.
- PUT settings limité aux réglages applicatifs, protégé par authentification, origine et CSRF.
- Collecteur CPU isolé dans un thread dédié ; panne SQLite sans arrêt de la supervision.
- 97 tests backend et 13 frontend, captures réelles et documentation mises à jour.
- Aucune action sur le système, les services ou les conteneurs ajoutée.

### Conteneurs — 23 octobre 2026

- Inventaire filtrable par nom/image et état, sélection d’un moteur et d’un conteneur.
- Détails filtrés excluant environnement, commandes, labels et montages.
- Statistiques CPU calculées sur les compteurs fournis et mémoire brute avec limites.
- Journaux TTY/multiplexés bornés, périodes et nombre de lignes configurables.
- Négociation d’API Docker/Podman et erreurs explicites de version, état et permissions.
- Masquage des secrets commun aux journaux services et conteneurs.
- 75 tests backend et 9 tests frontend, dont un test de transport sur socket Unix réel contrôlé.
- Aucune opération sensible ajoutée ; moteurs réels encore non qualifiés.

### Fonctionnalités — 23 octobre 2026

- Page Services : recherche, pagination et filtres des unités système chargées.
- Détails de service : état, démarrage et dépendances via propriétés autorisées.
- Journaux par unité : période, niveau, recherche littérale et pagination par curseur.
- Erreurs de permissions explicites et masquage de motifs de secrets connus.
- Sous-processus sans shell, limites de durée/volume/concurrence et nettoyage testé.
- 41 tests backend et 6 tests frontend, documentation et capture du module mises à jour.
- Aucune opération sensible ajoutée.

### Documentation

- README enrichi avec icônes, tableaux, diagramme, checklist et capture réelle du tableau de bord.
- Ajout de CONTEXT.md : priorités, architecture, état du projet et règles de reprise.
- Préparation du dépôt GitHub `nouhailler/cockpitor` et exclusions des fichiers locaux sensibles.

## 0.1.0 — 22 octobre 2026

- Socle FastAPI local en lecture seule et interface React responsive clair/sombre.
- Collecte système, processus paginés, capteurs et historique CPU en mémoire.
- Surveillance Ollama/OpenWebUI et inventaire optionnel Docker/Podman.
- Tests de protections API, de collecte, d'intégrations et d'interface.
- Aucune opération sensible ; limites et conformité documentées.
