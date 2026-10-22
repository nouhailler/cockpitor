# Sécurité et frontières de confiance

Prototype local en lecture seule, pas une version validée pour exposition réseau.

## Protections implémentées

- Lanceur non root, écoute fixe sur 127.0.0.1, sans proxy de confiance.
- Jeton aléatoire par démarrage, en-tête Authorization, comparaison en temps constant.
- Hôtes loopback autorisés uniquement ; origine étrangère refusée ; aucun CORS global.
- Aucun cookie d'authentification ; une page étrangère ne peut pas attacher le jeton
  détenu uniquement en mémoire par l'interface. Aucun jeton dans les URL.
- Toutes les méthodes autres que GET/HEAD refusées, aucun endpoint d'action.
- CSP, anti-frame, nosniff, no-referrer, no-store ; aucun asset externe.
- IP loopback numériques seulement pour les intégrations, sans redirection, proxy
  d'environnement ou identifiant intégré à l'URL. HTTPS conserve sa validation TLS.
- Lectures HTTP bornées en taille et temps ; inventaire filtré par liste de champs.
- React échappe le texte ; aucun rendu HTML de données externes.
- Aucun appel shell, aucune élévation de droits, aucun changement de groupe.

## Limites connues

Le jeton est un mécanisme provisoire pour le développement mono-utilisateur.
Il reste valide jusqu'au redémarrage ; la déconnexion efface seulement la copie
mémoire de l'onglet. Pas encore de sessions expirables ni de limitation des
échecs d'authentification. Ne pas réutiliser un jeton faible ou permanent.
Une autre application locale compromise ou le propriétaire du compte constitue
une menace distincte ; le jeton ne protège pas d'un compte système compromis.
Les limites globales de connexions et le durcissement systemd restent à implémenter.
Les informations système et noms de processus sont privées et nécessitent le jeton.
L'état OpenWebUI signifie uniquement qu'une réponse HTTP réussie est reçue :
ce n'est ni une authentification du produit ni une preuve de son fonctionnement interne.

Le socket Docker reste équivalent à root, même pour un client qui ne fait que lire.
Son activation nécessite une configuration explicite existante ; aucune permission
n'est accordée par le programme. Pas de garantie de confidentialité des noms de
modèles/conteneurs saisis par l'utilisateur : ces champs sont affichés tels quels,
comme texte. Les variables d'environnement et configurations secrètes sont exclues.

## Conditions préalables à des actions sensibles

Conception et revue de sécurité, actions typées, liste blanche des cibles,
permissions minimales, confirmation, audit expurgé, revalidation côté agent,
limites de concurrence et tests d'abus. Tant que ces conditions ne sont pas
validées, aucune mutation système ne doit être ajoutée ou activée.
