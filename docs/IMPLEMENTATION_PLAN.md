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
| Actions sensibles | ABSENT | volontairement bloquées ; conception, autorisation, confirmation et tests requis |
| Packaging Debian/systemd | ABSENT | à tester en VM avec permissions réelles |
| Stabilisation globale P0 | PARTIEL | contrôles locaux passants ; MVP complet non déclaré |

À chaque lot : lint, types, tests et build ; mise à jour du rapport de conformité.
Pas de déclaration de fin du MVP avant validation de tous les P0 et du paquet.

23 octobre 2026 : lot Services en lecture seule livré, 41 tests backend et 6 tests frontend. Prochaine étape fonctionnelle : détails/statistiques/journaux des conteneurs avant la persistance.

23 octobre 2026 : complément Conteneurs en lecture seule livré, 75 tests backend et 9 tests frontend. Prochaine étape : préférences SQLite et alertes locales ; actions sensibles toujours absentes.

23 octobre 2026 : SQLite et alertes livrés, 97 tests backend et 13 frontend. La seule mutation autorisée porte sur les réglages applicatifs ; les actions système restent absentes. Prochaine étape : diagnostic local expurgé.

23 octobre 2026 : diagnostic et français/anglais livrés, 109 tests backend et 18 frontend. Prochaine étape : sessions expirables et limitation des tentatives.
