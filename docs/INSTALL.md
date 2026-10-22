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
La désinstallation consiste à supprimer ce checkout et son environnement virtuel
après arrêt. Aucun modèle Ollama, moteur, conteneur ou volume externe n'est supprimé.
Le thème est une préférence locale du navigateur, effaçable via ses données de site.
Le paquet .deb, les migrations et le retour arrière ne sont pas encore disponibles.
