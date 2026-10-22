# Guide utilisateur

La vue d'ensemble présente les dernières valeurs réellement collectées. Une
valeur « Indisponible » n'est pas un zéro. CPU et réseau nécessitent deux collectes
après démarrage. Les débits sont agrégés sur les interfaces réseau et exprimés en
octets par seconde ; les tailles sont exprimées en unités binaires (Mio/Gio).
Le stockage suit les pourcentages système, qui peuvent tenir compte d'espace réservé.

Le graphique CPU garde environ 15 minutes au maximum, perdues au redémarrage.
La page Système complète les métriques avec les capteurs accessibles. Le GPU
n'est pas encore collecté. Les processus sont recherchables, paginés et triés
par utilisation mémoire ; leur CPU peut dépasser 100 % sur plusieurs cœurs.

Un bandeau signale les échecs et les données système âgées de plus de 15 secondes.
Une intégration indisponible n'empêche pas la surveillance système. Ollama fournit
ses propres modèles ; aucune estimation de VRAM n'est déduite de leur taille.
OpenWebUI désactivé signifie qu'aucune URL n'a été configurée. Les moteurs de
conteneurs nécessitent un accès existant, explicitement configuré par l'utilisateur.
Aucun bouton ne permet de modifier un service ou un conteneur.
