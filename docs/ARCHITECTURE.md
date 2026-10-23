# Architecture 0.1

Navigateur → même origine `127.0.0.1:8765` → FastAPI non root → collecteur psutil
et adaptateurs HTTP locaux. FastAPI sert le build React, sans CDN ni service worker.
Le lanceur refuse root et fixe l'adresse loopback. Lancer uvicorn manuellement
avec une autre adresse contournerait ce choix : ce mode n'est pas supporté.

Le collecteur tourne toutes les deux secondes. Les requêtes de métriques consultent son
dernier instantané ; elles ne déclenchent aucune collecte. CPU et réseau exigent
une référence précédente. Le CPU par processus peut dépasser 100 % et est
indisponible pour les nouveaux processus jusqu'à la collecte suivante.
L'historique contient au plus 450 points (environ 15 minutes) en mémoire.
Un échec garde l'horodatage précédent, permettant de signaler les valeurs anciennes.

Les vérifications IA et conteneurs tournent en parallèle, puis attendent dix secondes.
Les lectures HTTP sont limitées en durée et volume ; les réponses sont filtrées
et validées. Seules les informations utiles sont transmises à React. Aucun accès
à l'environnement d'un conteneur ou à une base OpenWebUI.

Cette première version n'a ni stockage SQLite, ni système de plugins chargeables,
ni agent privilégié. Les interfaces de modules versionnées restent à formaliser.
Les données de la machine de développement ne prouvent pas la compatibilité
avec une installation Debian propre.

## Services système — 23 octobre 2026

Un adaptateur indépendant inventorie toutes les dix secondes les unités système
chargées de type service. Détails et journaux sont demandés à la sélection, avec
contrôle des unités et limites de ressources. Aucune commande de mutation n’est
accessible. L’inventaire reste accessible si la lecture du journal échoue ; le
collecteur système et les intégrations IA/conteneurs sont indépendants de ce lot.

La sortie `systemctl show` est filtrée par propriétés ; journald utilise JSON et
les curseurs pour remonter dans le temps. La recherche de texte s’effectue sur une
page bornée sans passer d’expression régulière utilisateur au système.
Références : [systemctl](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)
et [journalctl](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html).
