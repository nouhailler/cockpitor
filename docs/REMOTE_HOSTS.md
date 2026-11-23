# Hôtes distants : SSH et première lecture SFTP

## Fonctionnalités disponibles

Menu → Intégrations → Hôtes distants, FR/EN : inventaire de huit hôtes maximum,
filtre par groupe, choix explicite d’une destination, empreinte attendue affichée,
vérification de l’authentification SSH et liste SFTP d’une racine configurée.
Aucun hôte, connexion ou balayage automatique. Les résultats sont ponctuels,
conservés en mémoire jusqu’au redémarrage ; aucune session SSH persistante.

Ce premier sous-lot n’expose aucun terminal, commande distante, tunnel, transfert,
lecture de contenu distant ou écriture SFTP. La liste est limitée aux 200 premières
entrées examinées, sans navigation récursive. Les liens sont indiqués comme
bloqués ; les dossiers sensibles usuels (.ssh, .env, etc.) sont exclus du résultat.
Un filtre de noms ne peut pas détecter tous les secrets propres à une application.

## Configuration explicite au lancement

Exemple à adapter, ne contenant aucune clé privée :

```sh
export LOCALCOCKPIT_REMOTE_HOSTS='[{
  "id":"debian-lab",
  "label":"Debian de test",
  "group":"Laboratoire",
  "address":"192.168.1.50",
  "port":22,
  "username":"cockpitor",
  "server_host_key":"ssh-ed25519 REMPLACER_PAR_LA_CLE_PUBLIQUE_VERIFIEE",
  "client_key":"/chemin/absolu/vers/cle-dediee",
  "allow_sftp":true,
  "remote_root":"/exports"
}]'
.venv/bin/python scripts/serve.py
```

L’exemple est volontairement invalide tant que la clé publique n’a pas été
remplacée. Récupérer la clé d’hôte et son empreinte depuis la console de la machine
ou un canal déjà authentifié. Ne pas considérer une simple découverte réseau de
clé comme une vérification. Le champ accepte les deux composants
`ssh-ed25519 <base64>`, sans commentaire ni certificat/autorité implicite.
Une clé présentée différente bloque l’authentification : vérifier hors bande,
modifier explicitement la configuration puis redémarrer ; aucune acceptation automatique.

Les adresses doivent être des IP numériques RFC1918, IPv6 ULA ou loopback pour
les essais. DNS, adresses publiques, link-local/métadonnées, multicast, adresses
indéfinies et IPv4 mappées en IPv6 sont refusés. Les plages CGNAT, tunnels publics
et sauts intermédiaires ne font pas partie de cette version.

Préparer séparément un compte distant dédié, sans droits administratifs. Le nom
root est refusé, mais le client ne peut pas prouver les privilèges effectifs d’un
compte renommé. Les permissions du compte et le confinement fort doivent être
imposés sur le serveur. Pour SFTP, imposer un chroot et une politique en lecture
seule côté serveur ; le contrôle client de la racine n’est pas une frontière de
sécurité contre un serveur compromis ou une course de renommage distante.
Le produit n’installe ni compte, ni authorized_keys, ni chroot sur une machine.

## Identifiants et protections

- Clé cliente Ed25519 existante, non chiffrée, explicitement choisie : fichier
  régulier appartenant au compte local, mode 0600, un seul lien physique, 8 Kio
  maximum. Liens symboliques de tous les ancêtres refusés. Choisir un stockage local
  fiable ; un blocage du noyau/stockage n’offre pas de délai de lecture garanti.
- Aucune clé privée copiée en base, dans les sauvegardes ou renvoyée à l’interface.
  Le chemin de clé n’est pas exposé par l’inventaire. Il reste dans la configuration
  de lancement ; limiter l’accès au compte et au mécanisme de lancement.
- Aucun agent SSH, clé par défaut, fichier ~/.ssh/config, ProxyCommand/ProxyJump,
  mot de passe, authentification interactive, certificat ou autorité implicite.
  Le coffre de secrets et les clés chiffrées interactives restent à réaliser.
- AsyncSSH vérifie la clé épinglée avant l’authentification. Le client transmet
  uniquement l’identité publique et la preuve d’authentification, jamais la clé privée.
- Chaque lecture POST exige session, origine exacte, CSRF, JSON strict, confirmation
  booléenne et identifiant de configuration. Un redémarrage invalide cet identifiant.
- Deux opérations admises au maximum, une par session et par hôte. Budget de huit
  secondes pour l’opération asynchrone, connexion/login limités à quatre secondes.
  Les limites temporelles restent coopératives, notamment pendant le nettoyage et
  la lecture locale d’une clé ; le slot reste occupé jusqu’à la fin du travail suivi.
- Annulation, navigation/déconnexion et expiration de session interrompent les
  travaux ; contrôle de session nominal toutes les 50 ms, plus avant/après résultat.
- Audit d’intention avant réseau et audit de succès avant réponse. Échecs réseau,
  clés refusées et erreurs de lecture audités sans hôte, chemin, clé ou erreur brute.
  Une panne d’audit empêche un résultat réussi. Les annulations peuvent ne conserver
  que l’intention ; aucun résultat positif n’est alors présenté.

Le contrôle réel de lecture reste celui du serveur distant. REALPATH et LSTAT
refusent une racine non canonique ou non répertoire ; aucune donnée fournie par
un serveur authentifié ne constitue une preuve universelle de son confinement.

## Tests et limites de qualification

540 tests backend et 48 frontend passent. Les 26 tests du lot couvrent
configurations interdites, clé privée non conforme, refus de clé d’hôte avant
authentification, droits SFTP, révocation, concurrence, quotas, audit en panne,
isolation multi-hôtes, erreurs et annulation. Les quatre tests UI couvrent FR/EN,
confirmation explicite, absence de connexion automatique et rendu textuel sûr.

Les tests d’intégration effectuent de vrais échanges SSH/SFTP avec un serveur
AsyncSSH éphémère loopback, clés et répertoires jetables. Le navigateur a confirmé
la sélection, l’empreinte, la lecture SFTP et la fermeture de connexion ; capture
`images/remote-fr.jpg` sur ce banc temporaire. Aucun hôte personnel contacté.
Ce banc ne qualifie pas OpenSSH/Debian réel, sa configuration chroot, les pare-feu,
les versions de SFTP ni des droits réels. Ces essais restent à réaliser sur serveur
isolé ; transferts, terminal et écritures demeurent absents.

Référence : [documentation officielle AsyncSSH](https://asyncssh.readthedocs.io/en/latest/api.html).
