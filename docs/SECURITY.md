# Sécurité et frontières de confiance

Prototype local en lecture seule, pas une version validée pour exposition réseau.

## Protections implémentées

- Lanceur non root, écoute fixe sur 127.0.0.1, sans proxy de confiance.
- Jeton aléatoire par démarrage, en-tête Authorization, comparaison en temps constant.
- Hôtes loopback autorisés uniquement ; origine étrangère refusée ; aucun CORS global.
- Aucun cookie d'authentification ; une page étrangère ne peut pas attacher le jeton
  détenu uniquement en mémoire par l'interface. Aucun jeton dans les URL.
- Méthodes d’écriture refusées sauf PUT exact sur /api/v1/settings et POST exact sur /api/v1/diagnostics ; aucun endpoint d’action système.
- Réglages : authentification, origine locale obligatoire, jeton CSRF en mémoire,
  JSON borné et schéma strict sans adresse réseau, chemin de socket ni commande.
- SQLite : dossier dédié 0700/base 0600 possédés par le compte, refus des liens
  symboliques, requêtes paramétrées, audit sans corps ni jeton, rétention bornée.
- Les fichiers de données privés sont exclus de Git ; aucune clé d’intégration
  ou token d’authentification/CSRF n’est enregistré dans la base.
- CSP, anti-frame, nosniff, no-referrer, no-store ; aucun asset externe.
- IP loopback numériques seulement pour les intégrations, sans redirection, proxy
  d'environnement ou identifiant intégré à l'URL. HTTPS conserve sa validation TLS.
- Lectures HTTP bornées en taille et temps ; inventaire filtré par liste de champs.
- Détails conteneurs : moteurs en liste blanche, identifiants complets validés,
  identité d’inspection vérifiée, uniquement GET sur le socket explicitement configuré.
- Inspect filtré sans environnement, commandes, labels ou montages ; deux opérations
  détaillées simultanées, délai total six secondes, 2 Mio par réponse.
- Journaux conteneurs non continus, tail borné, validation des trames multiplexées,
  masquage des secrets connus et rendu textuel. Aucun terminal ni action de contrôle.
- React échappe le texte ; aucun rendu HTML de données externes.
- Aucun appel shell, aucune élévation de droits, aucun changement de groupe.
- Lectures systemctl/journalctl avec chemins absolus, arguments séparés, unités
  exactes et environnement fixe ; pas de saisie libre de commande.
- Sous-processus limités à cinq secondes, 2 Mio stdout, 8 Kio stderr et deux
  lectures concurrentes ; arrêt et récupération après annulation ou dépassement.
- Propriétés systemd en liste blanche, erreurs expurgées ; avertissements de
  visibilité journald signalés, texte des logs échappé par React.
- Masquage des motifs password/token/api_key/secret, Bearer et clés privées
  connues dans les textes ; ce mécanisme n’est pas une garantie exhaustive.

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

## Export diagnostic

Liste blanche de scalaires et agrégats, sans journaux, identités ni configuration
brute. Confirmation explicite, authentification, origine et CSRF obligatoires ;
corps 1 Kio, sortie 64 Kio, génération limitée à une toutes les cinq secondes.
Aucune collecte supplémentaire, aucun fichier serveur ni transmission externe.
L’audit SQLite enregistre seulement l’opération, sans corps exporté. Si SQLite est
indisponible, l’export indique l’absence d’audit. Les agrégats et versions restent
des informations sur la machine : examiner le téléchargement avant partage.
