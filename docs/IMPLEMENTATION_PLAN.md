# Plan et avancement

Ordre demandé : surveillance système et interface, puis IA, puis conteneurs.
Les protections et tests précèdent toute opération sensible. Aucun agent ni
endpoint de mutation système n'est livré dans cette itération.

| Lot | État | Preuves / suite |
| --- | --- | --- |
| Cadrage | PARTIEL | architecture et sécurité documentées ; Debian cible et installation VM à valider |
| Socle API et interface | IMPLÉMENTÉ | accès par jeton, même origine, thèmes, navigation, build et tests |
| Surveillance système | IMPLÉMENTÉ | collecte partagée, historique mémoire, processus paginés, interface connectée |
| IA locale | IMPLÉMENTÉ | Ollama modèles/chargement et état HTTP OpenWebUI ; tests erreurs/absence |
| Conteneurs | PARTIEL | inventaire, détails, statistiques et logs reliés et testés ; qualification Docker/Podman réels NON TESTÉE |
| Services et journaux | PARTIEL | services chargés, détails et journaux par unité reliés et testés ; vue des journaux applicatifs et inventaire des fichiers non chargés à compléter |
| SQLite et alertes | IMPLÉMENTÉ | préférences, règles et événements persistants, rétention, audit et protections settings testés |
| Diagnostic expurgé | IMPLÉMENTÉ | export confirmé, expurgé par liste blanche, borné et audité ; tests et téléchargement navigateur |
| Français / anglais | IMPLÉMENTÉ | catalogues partagés, choix immédiat, préférence persistante, formats et erreurs localisés |
| Moteur L4 en simulation | IMPLÉMENTÉ | plans, approbations, revalidation et audit reliés ; qualification avant exécution réelle restante |
| Transport de vérification L5 | PARTIEL | banc Unix avec identité noyau et tests locaux ; aucune intégration/exécution réelle |
| Adaptateurs et postconditions de fixtures | PARTIEL | logique et journal autonome testés ; vrais pilotes et VM non qualifiés |
| Actions sensibles | ABSENT | volontairement bloquées ; conception, autorisation, confirmation et tests requis |
| Packaging Debian/systemd | ABSENT | à tester en VM avec permissions réelles |
| Stabilisation globale P0 | PARTIEL | contrôles locaux passants ; MVP complet non déclaré |

À chaque lot : lint, types, tests et build ; mise à jour du rapport de conformité.
Pas de déclaration de fin du MVP avant validation de tous les P0 et du paquet.

23 octobre 2026 : lot Services en lecture seule livré, 41 tests backend et 6 tests frontend. Prochaine étape fonctionnelle : détails/statistiques/journaux des conteneurs avant la persistance.

23 octobre 2026 : complément Conteneurs en lecture seule livré, 75 tests backend et 9 tests frontend. Prochaine étape : préférences SQLite et alertes locales ; actions sensibles toujours absentes.

23 octobre 2026 : SQLite et alertes livrés, 97 tests backend et 13 frontend. La seule mutation autorisée porte sur les réglages applicatifs ; les actions système restent absentes. Prochaine étape : diagnostic local expurgé.

23 octobre 2026 : diagnostic et français/anglais livrés, 109 tests backend et 18 frontend. Sessions traitées dans la tranche suivante.

## Extension proposée à partir de Linux Made Sane

Voir [la feuille de route détaillée](ROADMAP_LINUX_MADE_SANE.md) : inventaire
fonctionnel, douze lots et socle préalable aux opérations sensibles. Ce plan est
proposé, sans modification de code ni activation des fonctions administratives.

## Tranche validée et réalisée — L0 à L3

- Architecture : routeurs API, erreurs, capacités et composants React séparés.
- Sessions : expiration, révocation, limites et récupération par redémarrage local.
- Supervision : historique persistant et sondes complémentaires, selon droits/outils disponibles.
- Assistant IA : chat Ollama local, aperçu/consentement, conservation facultative et aucune action.

138 tests backend et 22 frontend, contrôles/build passants. Réponse du modèle local
et supervision vérifiées en navigateur. GPU NVIDIA seulement ; routes IPv4 ;
qualification SMART/GPU/NUT sur matériels réels à poursuivre. L4 et toutes les actions
administratives restent À FAIRE, soumis à leur barrière de sécurité dédiée.

24 octobre 2026 : socle L4 livré exclusivement en simulation, 179 tests backend et
26 frontend. La revue du futur exécuteur et les essais en VM jetable ne sont pas
réalisés ; la barrière avant L5 n’est pas franchie. Voir ACTIONS_SECURITY.md.

24 octobre 2026 : transport de vérification L5 livré dans un banc isolé, avec
SO_PEERCRED et sockets privées, messages issue/verify, bornes et annulation.
236 tests backend et 26 frontend passent. Prochaine tranche : liaison approbation/audit,
adaptateurs et qualification VM avec effets partiels explicites, avant toute activation.
Voir [EXECUTOR_QUALIFICATION.md](EXECUTOR_QUALIFICATION.md).

24 octobre 2026 : liaison L4 approbation/audit au client Unix réalisée sur banc,
avec protocole v2 lié à l'empreinte approuvée. 279 tests backend et 26 frontend.
Le lanceur conserve la simulation locale. Les adaptateurs, postconditions, gestion
des effets partiels et qualification VM précèdent toujours toute activation.

24 octobre 2026 : banc autonome d'adaptateurs/postconditions et journal persistant
livré, 349 tests backend et 26 frontend. Pilotes injectés uniquement par les tests ;
aucun branchement au protocole de vérification ou à la simulation de l'application.
Prochaine tranche : vrais pilotes bornés dans un environnement jetable, réconciliation
après effets partiels, revue des privilèges/révocation et qualification VM avant activation.
