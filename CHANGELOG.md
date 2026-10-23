# Historique — Cockpitor

## Non publié

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
