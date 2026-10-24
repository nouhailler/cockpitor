# Sécurité et frontières de confiance

Prototype local en lecture seule, pas une version validée pour exposition réseau.

## Protections implémentées

- Lanceur non root, écoute fixe sur 127.0.0.1, sans proxy de confiance.
- Jeton d’amorçage aléatoire par démarrage, échangé contre une session en mémoire.
- Hôtes loopback autorisés uniquement ; origine étrangère refusée ; aucun CORS global.
- Aucun cookie d'authentification ; une page étrangère ne peut pas attacher le jeton
  détenu uniquement en mémoire par l'interface. Aucun jeton dans les URL.
- Méthodes d’écriture en liste blanche : réglages, sessions, diagnostic, assistant ; aucun endpoint d’action système.
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

Le jeton du lanceur est un secret d’amorçage pour le fonctionnement mono-utilisateur.
Il reste valide jusqu’au redémarrage sauf configuration explicite, mais ne permet
que l’ouverture d’une session. Les sessions expirent et sont révocables côté serveur.
Ne pas réutiliser un jeton faible ou permanent.
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

## Sessions et assistant — tranche L0–L3

Sessions 256 bits, clés SHA-256 en mémoire, inactivité 15 min et durée absolue 8 h ;
32 sessions maximum, dix connexions/minute globales. Les lectures automatiques ne
repoussent pas l’expiration ; seule une activité explicite la repousse. La révocation
est immédiate pour les prochaines requêtes et annule l’attente IA associée. Les autres
lectures déjà autorisées ne sont pas interrompues rétroactivement. Aucun secret de
session en base, localStorage ou URL. Pas de multi-utilisateurs, MFA ou accès distant.

Les limites d’authentification sont globales : un programme local peut provoquer une
saturation temporaire. Le compte système propriétaire peut consulter le secret de
lanceur : ce mécanisme n’isole pas des applications malveillantes du même compte.
La récupération passe par le terminal local/redémarrage, sans endpoint de secours.

L’IA reçoit la question, un historique borné et, sur consentement explicite, un contexte
numérique prévisualisé lié à la session. Aucun log ou identifiant système joint par
défaut ; pas d’outil, shell, instruction privilégiée ou route d’action. Le contenu
est du texte échappé et peut être incorrect ou hostile. Un prompt système n’est pas
une protection suffisante : l’absence de capacités d’exécution impose la frontière.
Le masquage des secrets dans prompts/réponses reste partiel. La conservation est
facultative et privée, commune à l’utilisateur local ; ne pas saisir de secrets.

Le diagnostic par liste blanche ne reprend ni conversations, ni adresses des nouvelles
sondes. La collecte complémentaire et les erreurs restent bornées et expurgées.
Les droits de lecture sur SMART, journald et autres sondes ne sont jamais élargis.

Les modèles déclarés distants dans l’inventaire sont exclus de l’assistant. Avant
chaque envoi du prompt, /api/show doit confirmer des métadonnées locales sans
remote_host/remote_model. Cockpitor fait confiance au serveur Ollama local : ce n’est
pas un pare-feu pour ce processus. Son mode OLLAMA_NO_CLOUD=1 peut renforcer cette
frontière, à configurer côté Ollama sans modification automatique par Cockpitor.
Référence : [mode local Ollama](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).

## Plans et simulations L4

Le nouveau module autorise seulement la préparation, l’approbation, la simulation
et l’annulation applicatives. Aucune mutation système, aucune bascule d’activation,
aucun sudo/helper. Les configurations sont comparées par HMAC et les approbations
restent hachées en mémoire, liées à la session et à une échéance monotone.
L’audit est obligatoire pour chaque transition ; panne = refus, résultat inconnu ou
interruption, jamais succès supposé. La validation du simulateur ne qualifie pas une
exécution privilégiée. Voir [ACTIONS_SECURITY.md](ACTIONS_SECURITY.md) pour les tests
et la barrière de validation avant L5, encore non franchie.
