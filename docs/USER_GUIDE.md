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

## Services et journaux

La page Services liste les services système actuellement chargés, actifs ou non.
Rechercher un nom/une description, filtrer l’état, puis sélectionner une unité.
Le détail affiche l’état, la configuration au démarrage et les dépendances quand
disponibles ; il ne permet pas de modifier le service.

Les journaux montrent 50 entrées par page, par défaut sur la dernière heure.
Le niveau maximum inclut tous les niveaux plus graves. La recherche textuelle
est limitée à chaque page : utiliser « Entrées plus anciennes » même si la page
courante n’a aucun résultat. « Entrées récentes » reprend depuis les données
actuelles. Le contenu est du texte et certains secrets connus sont masqués.

Un refus de permission est une erreur de lecture, pas l’absence d’événements.
L’application n’élargit aucun droit. Un accès partiel signalé par journalctl est
également refusé comme lecture complète. Si le curseur n’existe plus après une
rotation, actualiser les journaux. Une collecte réussie vide signifie uniquement
qu’aucune entrée visible ne correspond à cette unité et à cette période.

## Détails d’un conteneur

Dans Conteneurs, filtrer le nom/image et l’état puis sélectionner un conteneur.
La sélection distingue Docker et Podman. Les dates et l’état proviennent du moteur,
avec horodatage de lecture ; actualiser pour relire l’état et les journaux.

Le CPU est un instantané calculé à partir des compteurs du moteur ; 200 % correspond
à deux cœurs occupés. Une référence manquante donne « Indisponible ». La mémoire
brute inclut le cache : elle ne reproduit donc pas nécessairement le chiffre de la
CLI Docker. La limite déclarée n’est pas une mesure de la RAM libre de l’hôte.
Un conteneur arrêté peut avoir des journaux lisibles et des statistiques indisponibles.

Les journaux sont limités aux dernières 50/100/200 lignes par flux sur une heure
ou 24 heures. stdout et stderr sont regroupés séparément, sans ordre global garanti.
En mode TTY, les deux flux sont déjà fusionnés. Un moteur/driver ne permettant pas
la lecture des logs affiche une erreur explicite. Le masquage vise les secrets
courants ; ne pas publier les journaux sans vérification humaine.

## Paramètres et alertes

Paramètres enregistre le thème, la fréquence d’affichage des métriques (la collecte
reste indépendante), les règles et la rétention. Le choix « Suivre le système »
suit les changements de thème du poste. La confirmation d’enregistrement contient
un identifiant d’opération ; une erreur de stockage signifie qu’aucun succès n’est confirmé.

Les règles CPU/RAM/swap déclenchent au-dessus du seuil ; disque libre déclenche
au-dessous. Les règles d’état (Ollama, service et conteneur) n’utilisent pas de seuil
numérique. Choisir une cible exacte pour service/conteneur/disque ; les sources
absentes ou non observables sont signalées, pas présumées saines. Une règle en
attente nécessite de nouvelles observations pendant la durée choisie.

Alertes sépare les événements actifs/résolus de l’état actuel des sources. Une
source devenue indisponible conserve un événement actif. Un état redevenu sain le
résout. Modifier, désactiver ou supprimer une règle résout ses événements actifs ;
changer uniquement le thème ne les résout pas. Les durées en attente repartent au
redémarrage, les événements persistent sans doublon. Les résolus sont conservés
pendant 1–90 jours à compter de leur résolution, avec un maximum de 1000 résolus.
Aucun envoi externe ou action automatique. Le diagnostic exportable reste absent.
