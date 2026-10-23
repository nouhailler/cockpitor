# Évolution de Cockpitor inspirée de Linux Made Sane

Plan proposé le 23 octobre 2026. Ce document ne déclenche aucune implémentation
ni activation de privilèges. Il complète le plan existant ; les lots ci-dessous
restent À FAIRE sauf les capacités explicitement signalées comme acquises.

## Périmètre et méthode

Référence : [Linux Made Sane Community Edition](https://github.com/lmsowner/linuxmadesanerelease),
branche main consultée le 23 octobre 2026. Analyse du README, de la documentation
sécurité et bureau distant, des pages Blazor, des interfaces applicatives et des
services d’infrastructure publics. Il s’agit d’un inventaire des familles de
fonctionnalités documentées ou représentées dans les sources, pas d’une certification
de leur fonctionnement : LMS n’a été ni installé ni exécuté pendant cette analyse.
Le dépôt annonce un sous-ensemble Community ; les offres privées ne sont pas auditées.
La présence d’une interface ou d’une page ne prouve pas une fonction opérationnelle.

Cockpitor conserve Python/FastAPI et React/TypeScript, le fonctionnement local,
l’absence de télémétrie, le français/anglais et les intégrations optionnelles.
Les fonctions seront réimplémentées à partir des besoins. Aucune reprise de code,
d’actifs ou de marque LMS n’est prévue ; toute réutilisation éventuelle devra faire
l’objet d’un examen séparé des conditions de licence et dépendances applicables.

## Couverture fonctionnelle de la référence

| Famille observée dans LMS | Cockpitor aujourd’hui | Destination proposée |
| --- | --- | --- |
| Tableau de bord, analyse et résumé de configuration | métriques, processus, historique RAM de 15 min | L2 : tendances persistantes, synthèse et navigation contextuelle |
| Hôtes locaux/distants, inventaire et découverte | machine locale | L7 : inventaire explicite, sondes SSH et santé par hôte |
| Terminal web, fenêtres et espace de travail | absent | L7 : terminal utilisateur optionnel, sessions révocables |
| Fichiers, recherche, aperçus, archives et transferts SFTP | absent | L6 puis L7 : lecture bornée, écritures contrôlées, transferts distants |
| Services, journaux, diagnostic et réparation | lecture des services chargés et logs bornés | L2 puis L5 : inventaire complet et actions typées |
| Mises à jour système, application et parc | absent | L2 : inventaire ; L5/L12 : exécution, suivi et récupération |
| Runbooks, tâches planifiées et historique | absent | L8 : recettes typées, planification, annulation et journal |
| Fournisseurs IA, chat, fils et aide au terminal | surveillance Ollama et état OpenWebUI | L3 : assistant local ; L8 : propositions d’opérations contrôlées |
| Gestion du moteur IA et des modèles, GPU, partage entre pairs | modèles Ollama en lecture | L2/L3 : matériel et capacités ; L8/L11 : gestion et partage optionnels |
| Applications Home Lab, groupes, catalogue et recettes | inventaire Docker/Podman | L8 : catalogue validé, installation et cycle de vie contrôlés |
| Réseaux de conteneurs, passerelles VPN et connexions d’apps | absent | L8/L10 : plans réseau, vérification et restauration des configurations |
| Interfaces réseau, équipements, sous-réseaux, DHCP, Wake-on-LAN | débit réseau agrégé | L2 : observation ; L10 : actions explicites |
| Surface d’attaque, écoute locale/réseau, pare-feu UFW | absent | L2 : audit ; L10 : règles et retour automatique de configuration |
| Administration SSH, clés, durcissement et authentification renforcée | absent | L7 : connexions ; L10 : modification SSH protégée contre la perte d’accès |
| Comptes applicatifs, utilisateurs/groupes Linux et identifiants enregistrés | jeton de lancement | L1 : sessions ; L4/L9 : permissions, secrets et gestion des identités |
| Passkeys, authenticator/MFA, durée de session et récupération | absent | L1 puis L11 : sessions locales d’abord, MFA avant accès distant |
| Partages Samba, accès, montages distants et SSHFS | absent | L9 : inspection, assistants, permissions et montages contrôlés |
| Serveur SFTP, chroot, utilisateurs, permissions et sauvegardes | absent | L9 : module dédié, isolé du navigateur de fichiers |
| Stockage, arborescence disques, SMART et gros répertoires | capacité des systèmes de fichiers | L2 : diagnostic ; L12 : attachement et redimensionnement à risque élevé |
| Sauvegarde/restauration hôte et configuration | diagnostic exportable ; sauvegarde manuelle SQLite | L6/L12 : sauvegardes versionnées et restauration testée |
| Alimentation/UPS et synchronisation de l’heure | absent | L2 : état et alertes ; L12 : actions système si nécessaires |
| Caddy, redirections de ports, tunnels SSH et Tailscale | absent | L10/L11 : intégrations distinctes, activées explicitement |
| Edge Gateway, Cloudflare Tunnel/DNS et publication protégée | absent | L11 : accès distant facultatif avec identité et révocation |
| Messagerie SMTP/Microsoft Graph et tests de livraison | aucune notification externe | L11 : connecteurs facultatifs et consentement par destination |
| Relais mail sortant, files/logs, DKIM/SPF/DMARC et préflight | absent | L11 : extension autonome, après les fonctions centrales |
| Bureau distant RDP/VNC via Guacamole | absent | L11 : composant éprouvé, accès ponctuel lié à la session |
| Assistant de bureau local, X11/Wayland et optimisation RDP | absent | L11 : diagnostic puis helper de session graphique optionnel |
| Bibliothèque média et analyses de contenu | absent | L11 : extension facultative, périmètre de dossiers explicite |
| Modules, installation, mise à niveau et récupération | lancement depuis les sources | L0/L12 : contrats de modules, paquet Debian, sauvegarde et mise à niveau |
| Portail, licences commerciales et fonctions privées | hors objectif du cockpit personnel | aucun équivalent commercial prévu ; besoins multi-hôtes traités en L7 |

Les recettes du catalogue constituent du contenu extensible : on reprend les
catégories et le mécanisme, pas une promesse de compatibilité avec chaque recette.
Une matrice par recette devra qualifier images, licences, ports, stockage et secrets.

## Architecture cible commune

- Un module expose un manifeste de capacités, son état, sa fraîcheur, ses routes
  de lecture, ses actions éventuelles et ses clés de traduction. Un échec local
  ne bloque pas le reste de l’application.
- Séparer collecte, présentation, planification d’actions et exécution. Aucun accès
  root dans le serveur web. Un auxiliaire privilégié minimal sera étudié en L4,
  avec protocole typé, identité du demandeur et règles d’autorisation explicites.
- Une opération possède un identifiant, un hôte, une cible, un type, un état,
  les contrôles préalables, l’approbation, les résultats et un audit expurgé.
- Préférences et métadonnées dans SQLite avec migrations sauvegardées. Secrets
  dans un coffre séparé, clé hors base, politique de sauvegarde et récupération.
- Définir capacités de lecture, d’écriture applicative et d’administration par module.
  Les connexions distantes ne doivent jamais réutiliser implicitement les droits locaux.
- Prévoir quotas de collecte, taille des sorties, concurrence, rétention et espace disque.
  Un canal d’événements authentifié pourra compléter le polling pour les opérations longues.

## Ordre de livraison et critères d’acceptation

### L0 — Structurer le socle sans modifier les comportements

Extraire progressivement les grandes vues React et les routes API en modules.
Définir schémas d’erreur et réponses, manifeste de capacités et navigation par groupes
(Observer, IA, Administrer, Connexions). Conserver les fonctionnalités existantes.

Validation : suites actuelles vertes, parcours de toutes les pages en FR/EN,
aucune régression de collecte, aucun nouveau privilège.

### L1 — Sessions, sécurité d’accès et audit consultable

Remplacer le jeton durable de développement par un échange initial vers une session
à expiration absolue et d’inactivité, révocable à la déconnexion. Limiter les tentatives,
protéger l’amorçage et définir une récupération locale sans porte dérobée distante.
Afficher l’historique d’audit filtrable, sans secrets. Préparer les capacités par rôle.
Décider explicitement du transport de session et de sa protection CSRF/XSS.

Validation : expiration, révocation, rejeu, bruteforce, origine/Host, CSRF,
concurrence et messages ne divulguant pas les comptes. Aucun secret persistant navigateur.

### L2 — Enrichir la supervision et l’interface

Historique SQLite agrégé avec rétention bornée ; CPU par cœur et GPU si accessibles ;
vue des disques/partitions et SMART ; état UPS/heure ; interfaces/routes/DNS/ports ;
services installés et chargés ; mises à jour disponibles ; synthèse de configuration.
Ajouter audit d’exposition distinguant loopback, réseau privé et écoute publique,
sans prétendre déduire l’exposition Internet depuis un port local seul.
Distinguer lecture locale et sondes réseau actives : ces dernières restent explicites.

Validation : permissions refusées, outils absents, données périmées, IPv4/IPv6,
plafond SQLite, charge du collecteur et accessibilité clavier/mobile en FR/EN.

### L3 — Assistant IA local, sans exécution

Chat Ollama, fils conservés selon préférence, choix du modèle et capacités matérielles.
Contexte système minimal présenté avant envoi au modèle, réponses sourcées par les
observations et fraîcheur. Suggestions de diagnostic et plans d’action affichables.
OpenWebUI reste une intégration distincte ; ne pas supposer une API interne stable.
Prévoir un adaptateur de fournisseurs, les services cloud restant désactivés par défaut.

Validation : absence de modèle, interruption/timeout, quotas, contenu hostile dans
les logs, absence d’exécution d’un texte IA et absence de fuite de secrets.

### L4 — Moteur d’actions contrôlées et barrière de sécurité

Définir actions typées en liste blanche, préflight, aperçu des changements, cible
exacte, approbation ponctuelle expirante liée au plan et à la session, contrôle
immédiatement avant exécution, verrouillage, durée maximale, annulation et audit.
Refuser si la cible/configuration a changé depuis l’approbation. L’IA ne peut ni
s’approuver elle-même ni créer une commande privilégiée libre.
L’auxiliaire, s’il est nécessaire, n’accorde que les actions approuvées ; aucun sudo
sans restriction. Les actions sont désactivées par défaut.

Validation bloquante avant L5 : injections d’arguments/chemins, dépassement de
permissions, rejeu, concurrence, changement de cible, session expirée, crash,
audit indisponible et échec partiel. Pour les actions sensibles, échec fermé si
autorisation ou audit requis indisponibles. Revue de sécurité et VM jetable obligatoires.

### L5 — Premières actions services, conteneurs et mises à jour

Activer action par action : démarrer/redémarrer un conteneur, démarrer/arrêter/
redémarrer un service, puis mises à jour APT avec simulation et journal de progression.
Exclure initialement services critiques, suppression de volumes et purge de paquets.
Prévoir verrou APT, espace libre, interruption, redémarrage requis et état final vérifié.
Une mise à jour de paquets ne garantit pas un retour arrière universel : sauvegarde
et procédure de récupération doivent être explicites.

Validation : intégrations sur Docker/Podman et systemd réels dans une VM, erreurs
de droits, nom trompeur, cible disparue, verrou concurrent et panne pendant l’opération.

### L6 — Fichiers locaux et sauvegardes de configuration

Navigateur limité à des racines choisies : liste, recherche bornée, aperçu texte/image
et téléchargement. Ajouter ensuite transferts, édition avec diff et version de fichier,
renommage, archives et suppression récupérable. Sauvegarde/restauration de la
configuration avec secrets traités séparément. Ne pas suivre implicitement un lien
vers une zone non autorisée ; limiter archives, liens, fichiers spéciaux et volumes.

Validation : traversée, liens et courses de changement de fichier, archives hostiles,
quotas et collision, droits, fichiers volumineux ; restauration effective en environnement isolé.

### L7 — Hôtes distants, SSH/SFTP et terminal

Inventaire explicite, groupes, sondes et état par hôte ; coffre d’identifiants,
vérification des clés d’hôte et changement de clé signalé. D’abord collecte distante,
puis SFTP et terminal utilisateur. Sessions terminal limitées, authentifiées,
révocables et séparées des actions structurées. Un terminal arbitraire ne peut pas
promettre une approbation par commande : son ouverture constitue une capacité
sensible distincte et ne donne jamais accès au helper privilégié.
Pas de découverte réseau illimitée ni acceptation automatique de clé SSH.

Validation : hôte indisponible, clé modifiée, SSRF/destinations interdites,
permissions par hôte, déconnexion, expiration, quotas WebSocket et secrets non exposés.

### L8 — Automatisation, gestion IA et catalogue Home Lab

Runbooks typés, versionnés et relus ; tâches planifiées avec fuseau horaire,
verrouillage, durée maximale et reprise explicite. Actions autonomes limitées à une
politique préalablement autorisée ; changement de recette invalide cette autorisation.
Installation/suppression de modèles et moteur IA via le même moteur d’actions.
Catalogue d’applications conteneurisées, versions vérifiées, ports/volumes explicites,
groupes/dépendances, réseaux et passerelles VPN. Pas d’exécution directe de recettes
téléchargées ou générées par IA. L’IA propose un plan ; le moteur décide des droits.

Validation : fuseau/heure d’été, doublons, reboot, secrets, approbation révoquée,
recettes altérées, collisions ports/volumes, rollback de configuration et données préservées.

### L9 — Identités, partages et serveur SFTP

Inventaire utilisateurs/groupes, permissions, partages Samba et montages SSHFS/Samba.
Assistants d’accès et prévisualisation des ACL, puis gestion explicite des comptes,
partages et chroot SFTP. Séparer comptes Cockpitor et comptes Linux. Préserver les
ACL d’origine et définir récupération avant modification d’un accès.

Validation : confinement, élévation, ACL héritées, chroot, accès croisés, refus de
droits et restauration ; tests Samba/SFTP réels dans un environnement isolé.

### L10 — Administration réseau et protections contre la perte d’accès

UFW, administration SSH, DHCP/réservations, Wake-on-LAN, tunnels SSH et redirections
de ports. Inspection avant édition. Montrer la portée et l’impact avant approbation.
Toute modification susceptible de couper l’accès exige un mécanisme autonome de
retour à la configuration précédente, une fenêtre de confirmation et un accès de secours.

Validation : vraie perte de connexion, timer survivant au processus web, redémarrage,
IPv6, règles contradictoires, ports occupés ; aucune modification du réseau de travail.

### L11 — Extensions facultatives d’accès distant et d’intégration

Sous-lots indépendants après revue de menace :

1. Accès privé via tunnel SSH/Tailscale ; MFA/passkeys et révocation pour l’accès distant.
2. Caddy et publication Cloudflare/Edge Gateway avec politique d’identité explicite,
   consentement de publication, secrets séparés et aucun service publié par défaut.
3. Notifications SMTP/Graph, puis relais mail distinct : domaines, DNS, DKIM/SPF/DMARC,
   files, tests et limites d’envoi. Aucune garantie de livraison à partir d’un test local.
4. RDP/VNC via un composant maintenu comme Guacamole : jetons ponctuels, cibles
   validées, révocation, TLS et transports authentifiés ; ne pas réécrire les protocoles.
5. Assistant du bureau local : helper sous le compte de session, consentement,
   diagnostic X11/Wayland, écrans et clavier ; changements du bureau approuvés.
6. Bibliothèque média : répertoires explicites, scans bornés et aperçus locaux.
7. Partage de moteur IA entre pairs, uniquement sur destinations et droits approuvés.

Validation par intégration réelle et révocation de session ; aucun compte cloud,
mail, tunnel public ou partage de données créé pendant le développement par défaut.

### L12 — Distribution, récupération et stockage à risque élevé

Premier sous-lot : paquet .deb, service systemd non root, répertoires standard,
durcissement, installation/mise à niveau/désinstallation et sauvegardes restaurables.
Le packaging du mode lecture peut être livré dès L2 ; ne pas attendre toutes les
extensions pour distribuer une version utile. Chaque module privilégié reste optionnel.

Sous-lot séparé, tout à la fin : attachement de disque, partitionnement, systèmes
de fichiers et redimensionnement. Plans détaillés par backend et type de stockage,
préconditions, sauvegarde restaurée en test, identification stable des périphériques,
refus des configurations inconnues et tests destructifs exclusivement en VM.
Ne jamais promettre d’annuler un formatage ou toute opération de stockage.

Validation : Debian cible explicitement choisie, VM propre, upgrade des anciennes
bases, reboot, désinstallation conservant les données, restauration après incident ;
matrice stockage documentant précisément les opérations supportées et refusées.

## Dépendances et politique de livraison

L0 → L1 → L2 → L3 constitue la première tranche utile, encore sans action système.
L4 est le verrou obligatoire pour L5 et pour les écritures administratives de
L6–L12. L7 nécessite aussi coffre et permissions par hôte. L11 nécessite sessions,
MFA et permissions distantes validées ; il ne change pas le mode local par défaut.
La stabilisation Debian et le packaging en lecture peuvent avancer après L2.

Pour chaque lot : FR/EN complets, aides/états indisponibles, tests fonctionnels
et d’abus pertinents, CI verte, documentation et captures réelles. Les scénarios
simulés et les essais sur systèmes réels restent identifiés séparément.
L’état « livré » exige un parcours UI → API → résultat observable, pas uniquement
un endpoint ou un bouton. Une validation technique ne vaut pas autorisation
implicite d’exécuter une action sensible sur le poste de l’utilisateur.

Le découpage est un ordre de dépendances, pas un calendrier. Chaque lot devra être
estimé après cadrage ; fichiers, SSH, stockage et exposition distante constituent
des chantiers distincts. L’inventaire par famille pourra évoluer avec la référence.

## Sources principales

- [Présentation et installation](https://github.com/lmsowner/linuxmadesanerelease/blob/main/README.md).
- [Navigation et modules visibles](https://github.com/lmsowner/linuxmadesanerelease/blob/main/src/LinuxMadeSane.Web/Components/Layout/NavMenu.razor).
- [Pages applicatives](https://github.com/lmsowner/linuxmadesanerelease/tree/main/src/LinuxMadeSane.Web/Components/Pages).
- [Interfaces métier](https://github.com/lmsowner/linuxmadesanerelease/tree/main/src/LinuxMadeSane.Application/Interfaces).
- [Services d’infrastructure](https://github.com/lmsowner/linuxmadesanerelease/tree/main/src/LinuxMadeSane.Infrastructure/Services).
- [Modèle de sécurité](https://github.com/lmsowner/linuxmadesanerelease/blob/main/docs/SECURITY.md).
- [Architecture RDP/VNC](https://github.com/lmsowner/linuxmadesanerelease/blob/main/docs/remote-desktop.md).
