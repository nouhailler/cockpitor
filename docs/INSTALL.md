# Installation depuis les sources

Voir les commandes du README ; ne pas utiliser sudo pour lancer l'application.
Le fichier requirements.lock fige l'environnement Python testé (développement
compris) et frontend/package-lock.json fige le frontend. Les téléchargements
initiaux nécessitent Internet. L'exécution compilée utilise uniquement des
ressources locales ; les adaptateurs contactent seulement les endpoints configurés.

Le frontend est servi depuis frontend/dist. Recompiler après toute modification.
Arrêt : Ctrl+C dans le terminal du lanceur. Redémarrage : relancer la même commande.
Le jeton est affiché dans ce terminal privé ; il ne doit pas être copié dans un
journal partagé. Un jeton fourni via LOCALCOCKPIT_TOKEN doit rester secret.

Si le démarrage échoue : vérifier que le port 8765 est libre, que le build existe
et que le processus est exécuté avec un utilisateur ordinaire. Si Ollama est absent,
l'interface système doit rester utilisable. OpenWebUI est désactivé sans URL.
Une erreur de socket conteneur ne doit pas conduire à élargir automatiquement les droits.

Aucun fichier système, utilisateur système ni service n'est installé actuellement.
La désinstallation depuis les sources consiste à supprimer le checkout et son
environnement virtuel après arrêt, après avoir sauvegardé les données privées souhaitées. Aucun modèle Ollama, moteur, conteneur ou volume externe n'est supprimé.
Le thème est une préférence locale du navigateur, effaçable via ses données de site.
Le paquet .deb et le retour arrière automatisé ne sont pas encore disponibles.
Le schéma SQLite courant est v2, décrit ci-dessous.

## Données persistantes

Par défaut, la base est créée dans `.localcockpit/cockpitor.sqlite3`, à la racine
du projet. Ce dossier doit être privé (0700), le fichier 0600, appartenant au compte
d’exécution. Un dossier existant trop permissif est refusé plutôt que modifié.
LOCALCOCKPIT_DATA_DIR peut désigner un autre dossier dédié, sans exposer ce choix dans l’API.
Un volume en lecture seule, plein ou verrouillé dégrade les préférences/alertes,
mais les métriques restent accessibles ; la récupération est réessayée.

Sauvegarde manuelle : arrêter l’application puis copier le dossier privé vers un
emplacement privé. Au redémarrage, conserver son propriétaire et ses permissions.
Une base antérieure (sans version ou v1) est sauvegardée avant la migration vers v2 ;
une base de version future est refusée. Les sauvegardes backup-*.sqlite3 restent
privées et doivent être conservées/supprimées explicitement par le propriétaire.
Ne pas supprimer le checkout sans préserver `.localcockpit/` si l’historique est utile.
Le diagnostic expurgé est disponible. Le paquet Debian reste à réaliser.

## Sessions et sondes facultatives

Après saisie du secret du lanceur, une session en mémoire remplace ce secret pour
les appels API. Elle expire après 15 minutes sans interaction ou huit heures au total.
Déconnexion et redémarrage la révoquent. Une reconnexion utilise le secret du terminal.
Le navigateur ne mémorise pas ces secrets. Dix connexions/minute maximum globalement.

Les sondes utilisent les outils déjà présents : lsblk, systemctl, apt, timedatectl,
smartctl, nvidia-smi et upsc. Rien n’est installé automatiquement. Les chemins sont
fixes sous /usr/bin et /usr/sbin. Les outils absents, permissions insuffisantes ou
matériels incompatibles sont signalés ; ne pas lancer l’application en root pour les contourner.
L’IA exige un modèle déjà installé dans Ollama ; l’application ne télécharge pas de modèle.
Conserver le dossier locales/ avec le backend pour les messages FR/EN.
