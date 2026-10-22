# Architecture 0.1

Navigateur → même origine `127.0.0.1:8765` → FastAPI non root → collecteur psutil
et adaptateurs HTTP locaux. FastAPI sert le build React, sans CDN ni service worker.
Le lanceur refuse root et fixe l'adresse loopback. Lancer uvicorn manuellement
avec une autre adresse contournerait ce choix : ce mode n'est pas supporté.

Le collecteur tourne toutes les deux secondes. Les requêtes API consultent son
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
