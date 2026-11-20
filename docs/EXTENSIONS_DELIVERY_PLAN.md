# Extensions demandées — ordre de livraison

Demande confirmée le 20 novembre 2026 : racines explicitement choisies, aucun
répertoire automatique, aucune connexion distante sans clé d’hôte vérifiée.
La feuille de route détaillée reste ROADMAP_LINUX_MADE_SANE.md ; le tableau
ci-dessous sépare l’avancement livré des prochains chantiers. Il n’active aucune
connexion, tâche, installation, modification d’accès ou publication.

| Ordre | Lot | Avancement et prochain résultat vérifiable |
| --- | --- | --- |
| 0 | Explorateur, sauvegardes et restauration | Premier sous-lot livré : exploration locale en lecture seule et restauration des préférences, cf. FILES_BACKUPS.md. Écritures de fichiers et sauvegardes complètes restent à faire. |
| 1 | SSH/SFTP et multi-hôtes | À faire : inventaire explicite, permissions par hôte, vérification stricte des clés d’hôte, stockage séparé des secrets puis connexion et SFTP bornés. Tester changement de clé, révocation, cibles interdites et erreurs sur serveur isolé. Aucun hôte de test n’a encore été fourni. |
| 2 | Catalogue d’applications et recettes | À faire : catalogue versionné, ports/volumes/dépendances explicites, analyse des collisions puis plans contrôlés. Aucune recette distante/IA exécutée directement ; moteurs réels à qualifier avant installation. |
| 3 | Tâches et procédures guidées | À faire : procédures typées, historique et exécution manuelle revue ; planification avec fuseau, heure d’été, déduplication, reprise et révocation de politique. Aucun cron ni tâche autonome créé par le développement. |
| 4 | Réseau, pare-feu, comptes et partages | À faire au-delà des observations réseau existantes : inventaires dédiés, plans d’ACL/règles/comptes, récupération autonome contre perte d’accès puis qualification VM et essais réels isolés. |
| 5 | Accès distant et notifications | À faire : accès privé avec authentification renforcée et révocation, puis connecteurs de notification facultatifs par destination. Aucun port public, tunnel, compte ou message externe créé par défaut. |

Les actions sensibles restent bloquées jusqu’à revue des privilèges, protections
et tests en VM jetable. L’IA demeure un conseiller sans outil d’exécution.
Chaque livraison doit relier l’interface FR/EN, l’API, le résultat observable,
les tests d’abus, la documentation et la CI. Une page de configuration ou un banc
simulé ne suffisent pas à déclarer une intégration réelle implémentée.
