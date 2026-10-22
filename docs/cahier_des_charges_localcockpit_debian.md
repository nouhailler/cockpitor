# Cahier des charges --- Cockpit Personnel Debian

**Version :** 1.0\
**Date :** 22 octobre 2026\
**Nom de travail :** `LocalCockpit` (nom modifiable)\
**Cible :** ordinateur personnel sous Debian, usage local uniquement\
**Objectif :** créer une application web d'administration Linux
modulaire, inspirée de Cockpit, avec un agent système dédié, une API
locale sécurisée et des intégrations pour Ollama, OpenWebUI et
Docker/Podman.

------------------------------------------------------------------------

## 1. Vision et objectifs

L'application doit fournir depuis un navigateur une vue cohérente de
l'état de l'ordinateur Debian et permettre d'effectuer un ensemble
limité d'opérations d'administration sans devoir ouvrir constamment un
terminal.

### 1.1 Objectifs principaux

1.  Afficher en temps réel les métriques système essentielles.
2.  Inspecter les services systemd, leurs états et leurs journaux.
3.  Surveiller Ollama, OpenWebUI, les modèles locaux et les ressources
    utilisées.
4.  Superviser les conteneurs Docker ou Podman, leurs journaux et leur
    état.
5.  Exécuter uniquement des actions explicites, validées et autorisées.
6.  Fonctionner sans cloud, sans compte externe et sans télémétrie.
7.  Être installable et désinstallable proprement sur Debian.
8.  Permettre l'ajout futur de modules sans réécriture du cœur.

### 1.2 Hors périmètre de la première version

-   Administration de machines distantes.
-   Accès depuis Internet ou exposition publique.
-   Gestion multi-utilisateurs ou multi-ordinateurs.
-   Orchestration Kubernetes.
-   Remplacement complet d'un gestionnaire de fichiers ou d'un terminal
    généraliste.
-   Exécution arbitraire de commandes shell depuis l'API.
-   Mise à jour automatique du système sans confirmation.
-   Stockage cloud, comptes externes, télémétrie ou analytics.
-   Promesse de compatibilité avec toutes les distributions Linux : la
    première cible est Debian.

### 1.3 Principes non négociables

-   **Local par défaut :** écouter uniquement sur `127.0.0.1` et/ou
    `::1`.
-   **Moindre privilège :** l'interface et l'API ne tournent jamais
    intégralement en root.
-   **Pas de shell arbitraire :** les opérations privilégiées passent
    par des actions nommées et validées.
-   **État observable :** les erreurs, actions et résultats sont
    clairement affichés.
-   **Dégradation contrôlée :** l'indisponibilité d'Ollama ou de Docker
    ne doit pas empêcher l'accès au tableau de bord.
-   **Modularité :** chaque intégration est isolée derrière une
    interface stable.
-   **Pas de données inventées :** toute métrique absente est indiquée
    comme indisponible, jamais remplacée par une valeur fictive.

------------------------------------------------------------------------

## 2. Utilisateurs et scénarios

L'utilisateur principal est le propriétaire de l'ordinateur Debian.
L'application peut afficher les données système et les applications
locales. Les actions modifiant le système doivent demander une
confirmation proportionnée au risque.

Scénarios prioritaires :

1.  Vérifier rapidement si CPU, RAM, stockage ou température sont
    anormaux.
2.  Identifier les processus consommant le plus de ressources.
3.  Voir pourquoi un service systemd a échoué.
4.  Vérifier si Ollama et OpenWebUI sont disponibles.
5.  Voir les modèles Ollama présents et les informations exposées par
    l'API locale.
6.  Repérer les conteneurs arrêtés, en erreur ou consommant beaucoup de
    ressources.
7.  Consulter les journaux d'un service ou d'un conteneur.
8.  Redémarrer un service ou un conteneur autorisé après confirmation.
9.  Exporter un diagnostic local pour faciliter le dépannage, en
    masquant les secrets.

------------------------------------------------------------------------

## 3. Architecture cible

### 3.1 Vue d'ensemble

``` text
Navigateur local
  └── Frontend PWA (React + TypeScript)
        └── API locale (FastAPI)
              ├── Collecteur système (lecture seule)
              ├── Adaptateur systemd / journald
              ├── Adaptateur Ollama
              ├── Adaptateur OpenWebUI (état/URL, API si configurée)
              ├── Adaptateur Docker ou Podman
              ├── Service d'autorisations et d'audit
              └── Stockage local SQLite (préférences, alertes, audit limité)
                    └── Agent privilégié minimal, si nécessaire,
                        exposant uniquement des actions prédéfinies
```

Le frontend ne doit jamais accéder directement aux interfaces
privilégiées du système. L'API doit valider chaque requête et ne
transmettre à l'agent que des actions typées, autorisées et limitées.

### 3.2 Stack proposée

-   Frontend : React, TypeScript, Vite.
-   UI : bibliothèque de composants accessible, thème clair/sombre,
    responsive.
-   Graphiques : bibliothèque maintenue compatible React, avec unités et
    plages temporelles explicites.
-   Backend : Python 3 et FastAPI, exécuté par un service systemd
    non-root.
-   Validation : Pydantic pour les schémas API.
-   Données : SQLite pour les paramètres et événements utiles ; aucune
    base obligatoire pour les métriques instantanées.
-   Collecte : `/proc`, `/sys`, bibliothèques Python maintenues,
    `psutil` si pertinent.
-   Services : `systemctl` et `journalctl` appelés avec arguments fixes,
    sans shell.
-   Conteneurs : API Docker ou commandes/API Podman selon le moteur
    détecté.
-   IA : API HTTP locale d'Ollama ; détection d'OpenWebUI via
    URL/configuration locale, sans présumer qu'une API authentifiée est
    disponible.
-   Packaging : paquet `.deb`, unités systemd, configuration dans
    `/etc/localcockpit/`, données dans `/var/lib/localcockpit/`,
    journaux via journald.

Les versions minimales doivent être définies dans le dépôt et validées
sur une version Debian stable explicitement ciblée. Les dépendances
doivent être épinglées ou bornées de manière reproductible.

### 3.3 Processus et privilèges

**Processus API non privilégié :** - écoute locale uniquement ; -
collecte des métriques accessibles à l'utilisateur de service ; -
lecture des paramètres de l'application ; - communication avec les
adaptateurs ; - aucune capacité Linux supplémentaire par défaut.

**Agent privilégié optionnel :** - installé seulement si des actions
nécessitent réellement des droits supplémentaires ; - petit programme
séparé, idéalement avec protocole local à permissions Unix ; - accepte
exclusivement des identifiants d'action et des paramètres structurés ; -
n'accepte jamais une chaîne de commande, un chemin arbitraire ou des
arguments libres ; - valide à nouveau chaque paramètre côté agent ; -
journalise les opérations ; - refuse par défaut toute action inconnue.

**Règle :** ne pas utiliser `sudo` sans restriction, ne pas ajouter
l'utilisateur du service à un groupe trop puissant et ne pas exposer le
socket Docker au navigateur ou à un client distant. L'accès au socket
Docker est équivalent à un accès root : il doit être explicitement
documenté et activé uniquement si nécessaire.

### 3.4 Interfaces de modules

Chaque module expose au minimum : - `id`, `name`, `version`,
`description` ; - `health()` pour l'état et la raison d'indisponibilité
; - `get_status()` pour les informations en lecture ; -
`get_capabilities()` pour annoncer les fonctions prises en charge ; -
des actions séparées, nommées, typées et autorisées ; - des délais
d'expiration, une gestion d'erreur et des tests propres.

Un module défaillant ne doit pas bloquer les autres modules.

------------------------------------------------------------------------

## 4. Écrans et navigation

### 4.1 Structure globale

Barre latérale : 1. Vue d'ensemble 2. Système 3. Services 4. IA locale
5. Conteneurs 6. Journaux 7. Alertes 8. Paramètres 9. Diagnostic / À
propos

Barre supérieure : - nom de la machine ; - état de connexion à l'API ; -
indicateur local ; - heure de dernière mise à jour ; - bouton
d'actualisation ; - menu d'aide.

### 4.2 Écran « Vue d'ensemble »

Afficher : - CPU : utilisation globale et par cœur si disponible ; -
mémoire : utilisée, disponible, swap ; - stockage : utilisation des
systèmes de fichiers pertinents ; - réseau : débit entrant/sortant ; -
uptime et charge système ; - température et GPU uniquement si les
capteurs/outils sont détectés ; - nombre de services en échec ; - état
d'Ollama et d'OpenWebUI ; - nombre de conteneurs actifs/arrêtés/en
erreur ; - dernières alertes et événements récents.

Chaque carte indique la valeur, l'unité, l'heure de collecte et, si
applicable, la cause d'indisponibilité. Les graphiques proposent des
fenêtres 1 min, 15 min, 1 h et 24 h selon la rétention disponible.

### 4.3 Écran « Système »

Onglets : - **Ressources :** CPU, RAM, swap, charge, réseau,
température. - **Stockage :** périphériques et systèmes de fichiers,
capacité totale/utilisée/libre, points de montage. - **Processus :**
PID, nom, utilisateur, CPU, RAM, état ; tri et recherche. -
**Informations :** distribution, noyau, architecture, uptime,
hostname. - **GPU :** fournisseur, utilisation, mémoire et température
seulement si une source fiable est détectée.

V1 en lecture seule. Ne pas proposer de tuer un processus dans le
premier MVP. Si cette fonction est ajoutée plus tard, exiger une
confirmation et interdire les processus critiques.

### 4.4 Écran « Services »

-   Liste paginée/recherchable des unités pertinentes.
-   Nom, description, type, état actif, état au démarrage, dernière
    erreur si disponible.
-   Filtres : actifs, inactifs, échec.
-   Détail d'un service : état, horodatage, extraits de journaux
    récents, dépendances si disponibles.
-   Actions V1 : consulter et actualiser.
-   Actions V1.1 : démarrer, arrêter ou redémarrer des unités
    explicitement autorisées, après confirmation.
-   Pas d'édition arbitraire d'unités systemd depuis le navigateur en
    V1.

### 4.5 Écran « IA locale »

**Ollama** - état joignable/non joignable ; - URL locale configurée ; -
latence de vérification ; - liste des modèles renvoyés par l'API ; -
détails disponibles : nom, taille, famille, quantification, date si
exposés par l'API ; - modèles chargés en mémoire si l'API fournit cette
information ; - bouton de vérification et horodatage de la dernière
réponse ; - erreurs explicites si Ollama est arrêté ou inaccessible.

Ne pas afficher de compteur de crédits cloud : l'application cible
l'usage local et ne doit pas supposer l'existence d'une facturation ou
d'une métrique qui n'est pas fournie par l'API.

**OpenWebUI** - état HTTP local, URL et latence ; - lien ouvrant
l'interface dans un nouvel onglet ; - détection par configuration ou URL
saisie ; - aucune tentative de lire une base interne ou un secret
d'OpenWebUI ; - toute intégration API nécessitant une clé doit être
désactivée par défaut, la clé étant stockée avec permissions
restrictives et jamais envoyée au frontend.

**Ressources IA** - CPU/RAM du processus si l'identification est fiable
; - GPU/VRAM si un outil ou pilote compatible est détecté ; -
avertissement si les données sont estimées ou incomplètes ; - ne pas
déduire la VRAM utilisée depuis la taille d'un modèle.

V1 : surveillance et liens. Le téléchargement/suppression de modèles est
hors périmètre initial ; s'il est ajouté plus tard, prévoir
avertissement sur la taille, confirmation et suivi de progression.

### 4.6 Écran « Conteneurs »

-   Détecter Docker et/ou Podman sans exiger les deux.
-   Afficher moteur, version et état de connexion.
-   Tableau : nom, image, état, uptime, ports publiés, consommation si
    disponible.
-   Filtres : en cours, arrêtés, en erreur.
-   Détail : configuration non secrète, état, logs récents,
    statistiques.
-   V1 : lecture seule.
-   V1.1 : démarrer, arrêter et redémarrer un conteneur après
    confirmation.
-   V2 : actions avancées, uniquement après revue de sécurité.

Ne jamais afficher par défaut les variables d'environnement susceptibles
de contenir des secrets. Ne pas exposer de terminal de conteneur dans le
MVP.

### 4.7 Écran « Journaux »

-   Journaux de l'application et services sélectionnés.
-   Filtrage par unité, niveau, période et texte.
-   Pagination et limites strictes de taille.
-   Chargement progressif ; pas de lecture illimitée.
-   Échappement de tout contenu avant rendu HTML.
-   Les secrets connus doivent être masqués dans l'export de diagnostic.
-   Un échec de permission doit être expliqué clairement, pas présenté
    comme un journal vide.

### 4.8 Écran « Alertes »

Alertes locales configurables : - seuil CPU élevé pendant une durée
définie ; - RAM ou swap au-dessus d'un seuil ; - espace disque libre
sous un seuil ; - service critique en échec ; - Ollama indisponible ; -
conteneur critique arrêté.

Chaque alerte possède : identifiant, gravité, règle, état actif/résolu,
horodatages, message et action suggérée. Pas de notification externe en
V1. Une notification navigateur locale peut être ajoutée après
consentement.

### 4.9 Écran « Paramètres »

-   thème clair/sombre/système ;
-   fréquence d'actualisation ;
-   modules activés/désactivés ;
-   URLs locales des intégrations ;
-   seuils d'alertes ;
-   durée de rétention ;
-   export de diagnostic expurgé ;
-   informations de version et de mise à jour ;
-   état de sécurité et adresse d'écoute.

La configuration ne doit pas permettre de changer l'adresse d'écoute
vers une interface réseau sans avertissement et procédure explicite.

------------------------------------------------------------------------

## 5. API locale

Préfixe recommandé : `/api/v1`. Les routes doivent être documentées
automatiquement et leurs schémas versionnés.

### 5.1 Routes indicatives

-   `GET /api/v1/health` : santé de l'API et versions.
-   `GET /api/v1/overview` : résumé consolidé.
-   `GET /api/v1/system/metrics` : métriques instantanées.
-   `GET /api/v1/system/processes` : processus filtrés/paginés.
-   `GET /api/v1/storage` : systèmes de fichiers.
-   `GET /api/v1/services` : liste de services.
-   `GET /api/v1/services/{unit}` : détail d'une unité validée.
-   `GET /api/v1/services/{unit}/logs` : journaux limités.
-   `GET /api/v1/ai/ollama/status` : disponibilité Ollama.
-   `GET /api/v1/ai/ollama/models` : modèles exposés par Ollama.
-   `GET /api/v1/ai/openwebui/status` : disponibilité OpenWebUI.
-   `GET /api/v1/containers` : liste des conteneurs.
-   `GET /api/v1/containers/{id}` : détail d'un conteneur.
-   `GET /api/v1/containers/{id}/logs` : journaux bornés.
-   `GET /api/v1/alerts` : alertes actives et historique limité.
-   `GET /api/v1/settings` et `PUT /api/v1/settings` : configuration
    validée.
-   `POST /api/v1/actions/{action_id}` : action prédéfinie, uniquement
    si activée.

Toute route de mutation doit retourner un identifiant d'opération, un
état explicite et une erreur structurée si nécessaire. Les routes de
lecture ne doivent pas déclencher d'effet de bord.

### 5.2 Temps réel

Utiliser WebSocket uniquement pour les métriques et événements
nécessaires. Limiter le débit, authentifier la connexion, vérifier
l'origine et couper proprement les connexions inactives. Une
interrogation HTTP périodique reste acceptable pour le MVP.

### 5.3 Gestion des erreurs

Format commun : - code stable ; - message compréhensible ; - détail
technique expurgé ; - module concerné ; - possibilité ou non de
réessayer ; - identifiant de corrélation.

Ne jamais retourner de trace Python, secret, variable d'environnement
complète ou chemin sensible dans une erreur visible.

------------------------------------------------------------------------

## 6. Modèle de données

SQLite ne stocke que les éléments qui bénéficient d'une persistance. Les
métriques haute fréquence sont conservées en mémoire sur une fenêtre
courte ; une rétention longue est optionnelle.

### 6.1 Tables proposées

**settings** - `key` TEXT PRIMARY KEY - `value_json` TEXT NOT NULL -
`updated_at` TEXT NOT NULL

**alert_rules** - `id` TEXT PRIMARY KEY - `name` TEXT NOT NULL -
`metric` TEXT NOT NULL - `operator` TEXT NOT NULL - `threshold` REAL NOT
NULL - `duration_seconds` INTEGER NOT NULL - `enabled` INTEGER NOT
NULL - `severity` TEXT NOT NULL

**alert_events** - `id` TEXT PRIMARY KEY - `rule_id` TEXT - `status`
TEXT NOT NULL - `message` TEXT NOT NULL - `created_at` TEXT NOT NULL -
`resolved_at` TEXT

**audit_events** - `id` TEXT PRIMARY KEY - `actor` TEXT NOT NULL -
`action_id` TEXT NOT NULL - `target_type` TEXT - `target_id` TEXT -
`result` TEXT NOT NULL - `timestamp` TEXT NOT NULL -
`details_redacted_json` TEXT

**module_preferences** - `module_id` TEXT PRIMARY KEY - `enabled`
INTEGER NOT NULL - `config_json` TEXT NOT NULL

Ne pas conserver mots de passe, clés API en clair dans les journaux ou
événements d'audit. Si une clé est indispensable, privilégier un fichier
de configuration appartenant à l'utilisateur du service avec permissions
`0600`, ou un mécanisme système approprié. La base de données ne doit
pas contenir de secrets si cela peut être évité.

------------------------------------------------------------------------

## 7. Exigences de sécurité

### 7.1 Réseau et navigateur

-   Écoute par défaut sur loopback uniquement (`127.0.0.1`,
    éventuellement `::1`).
-   Refuser les origines web non autorisées.
-   Ne pas activer CORS globalement.
-   Protection CSRF pour toute action modifiant l'état si cookies
    utilisés.
-   Cookies de session `HttpOnly`, `SameSite=Strict` et `Secure` lorsque
    HTTPS est configuré.
-   CSP stricte, protection contre le clickjacking et politique MIME.
-   Pas de ressources tierces chargées depuis Internet en fonctionnement
    normal.
-   Pas de CDN obligatoire : les assets sont locaux.
-   Désactiver le service worker en développement ou éviter qu'il serve
    une ancienne interface après une mise à jour sensible.

### 7.2 Authentification

Même en local, ne pas supposer que toute page ouverte sur la machine est
fiable. Pour la première version : - accès local limité à un utilisateur
système prévu pour l'application ; - session locale ou mécanisme
d'authentification explicite ; - aucune authentification par simple
paramètre URL ; - limitation des tentatives et expiration de session ; -
toute action sensible exige une confirmation visible.

Documenter clairement les risques si une version « sans connexion » est
proposée pour un usage strictement mono-utilisateur.

### 7.3 Commandes et droits

-   Interdiction absolue de `shell=True` pour les commandes système.
-   Utiliser des exécutables absolus et des arguments séparés.
-   Liste blanche des opérations et des unités gérables.
-   Validation stricte des identifiants de service, conteneur et modèle.
-   Limites de temps, de sortie et de concurrence.
-   Pas de commande construite par concaténation de chaînes utilisateur.
-   Aucun endpoint générique du type `/run?command=...`.
-   Journal d'audit pour chaque mutation.
-   Confirmation explicite avant arrêt/redémarrage.
-   Actions privilégiées désactivées par défaut.

### 7.4 Données et journaux

-   Ne pas journaliser les tokens, mots de passe, clés API, variables
    d'environnement complètes ou corps de requête sensibles.
-   Échapper les logs affichés dans l'interface.
-   Limiter taille et durée de conservation.
-   Protéger fichiers de configuration et base SQLite par permissions
    Unix.
-   Exports expurgés et confirmation avant génération.
-   Ne pas collecter ni envoyer de télémétrie.

### 7.5 Menaces à tester

-   Requête HTTP forgée depuis une page malveillante.
-   DNS rebinding et validation d'hôte/origine.
-   Injection via nom de service, nom de conteneur ou filtre de logs.
-   Accès à un chemin hors périmètre.
-   Abus de l'agent privilégié.
-   Fuite de secrets dans les logs, erreurs ou export.
-   Déni de service par lecture de journaux volumineux ou connexions
    WebSocket multiples.
-   Usurpation d'un service local ou endpoint inattendu.
-   Dépendance compromise ou paquet d'installation modifié.

------------------------------------------------------------------------

## 8. Installation, configuration et désinstallation

### 8.1 Installation cible

Le livrable final doit être un paquet Debian `.deb` et un mode
installation depuis les sources pour les développeurs.

Le paquet installe : - frontend compilé dans `/usr/share/localcockpit/`
; - backend dans un emplacement système dédié ; - configuration dans
`/etc/localcockpit/` ; - données dans `/var/lib/localcockpit/` ; - unité
systemd avec utilisateur système dédié ; - éventuellement l'agent
privilégié séparé, seulement si les fonctions retenues l'exigent.

### 8.2 Service systemd

-   utilisateur et groupe système dédiés ;
-   `NoNewPrivileges=true` quand compatible ;
-   `PrivateTmp=true` ;
-   protections systemd adaptées (`ProtectSystem`, `ProtectHome`,
    `PrivateDevices`, restrictions d'accès) testées avec les modules
    activés ;
-   `UMask=0077` ;
-   redémarrage contrôlé en cas d'échec ;
-   aucune écoute sur `0.0.0.0` par défaut ;
-   limites de ressources raisonnables ;
-   journaux via journald.

Ne pas copier des options de durcissement sans vérifier leur
compatibilité avec la collecte des métriques et les intégrations
installées.

### 8.3 Dépendances optionnelles

-   Docker : module activé uniquement si le moteur et les permissions
    sont disponibles.
-   Podman : support à travers un adaptateur distinct.
-   Ollama : module activé si l'endpoint local répond.
-   OpenWebUI : lien/état si l'URL configurée répond.
-   GPU : afficher les fonctions uniquement si le matériel et les outils
    requis sont détectés.

L'absence d'une dépendance optionnelle ne doit pas faire échouer
l'installation.

### 8.4 Désinstallation

-   arrêter et désactiver les services ;
-   retirer les fichiers installés par le paquet ;
-   ne pas supprimer automatiquement les paramètres, historiques ou
    exports de l'utilisateur ;
-   proposer une procédure explicite pour supprimer les données
    résiduelles ;
-   ne jamais supprimer Docker, Podman, Ollama ou leurs données ;
-   documenter les fichiers conservés.

### 8.5 Mises à jour

-   installation reproductible ;
-   migration de schéma versionnée ;
-   sauvegarde de la configuration avant migration ;
-   retour arrière documenté ;
-   ne jamais lancer silencieusement une mise à jour système générale.

------------------------------------------------------------------------

## 9. Tests et qualité

### 9.1 Tests unitaires

-   calcul des métriques et unités ;
-   validation des paramètres ;
-   gestion des erreurs des modules ;
-   parsing de sorties ;
-   règles d'alertes ;
-   masquage des secrets ;
-   autorisations et liste blanche ;
-   migration SQLite.

### 9.2 Tests d'intégration

-   API avec services présents et absents ;
-   systemd/journald sur Debian cible ;
-   Ollama joignable, arrêté, lent, réponse invalide ;
-   OpenWebUI présent ou absent ;
-   Docker/Podman présents, absents ou permissions insuffisantes ;
-   socket inaccessible ;
-   base SQLite verrouillée ou indisponible ;
-   reconnexion après redémarrage d'un module.

### 9.3 Tests frontend

-   navigation clavier et accessibilité ;
-   affichage responsive ;
-   états chargement, vide, erreur et indisponible ;
-   filtres et pagination ;
-   confirmation des actions ;
-   rendu sûr de logs contenant HTML ou caractères spéciaux ;
-   absence de données périmées présentées comme actuelles.

### 9.4 Tests de sécurité

-   injection de commande ;
-   CSRF et vérification d'origine ;
-   contrôle d'accès à chaque action ;
-   paramètres invalides et identifiants malformés ;
-   exposition accidentelle sur interface réseau ;
-   secrets absents des logs et exports ;
-   limites de taille, temps et concurrence ;
-   analyse des dépendances ;
-   vérification des permissions du paquet et des fichiers ;
-   tests d'abus de l'agent privilégié.

### 9.5 Tests d'installation

-   installation propre sur une Debian supportée ;
-   démarrage automatique ;
-   accès uniquement via loopback ;
-   fonctionnement sans Internet après installation ;
-   fonctionnement quand tous les modules optionnels sont absents ;
-   mise à jour depuis la version précédente ;
-   désinstallation sans suppression des données externes ;
-   vérification des permissions et unités systemd.

### 9.6 Outils CI

-   formatage et lint du frontend ;
-   TypeScript strict ;
-   lint Python et vérification des types ;
-   tests unitaires et intégration ;
-   audit des dépendances ;
-   build reproductible ;
-   tests API ;
-   génération des artefacts de version.

Aucun test ne doit dépendre d'un service cloud ou d'une clé API externe.
Utiliser des mocks et des environnements locaux contrôlés.

------------------------------------------------------------------------

## 10. Critères d'acceptation

La version MVP est acceptée uniquement si tous les critères P0 sont
satisfaits.

### P0 --- Obligatoires

1.  Le paquet s'installe sur la version Debian cible documentée.
2.  L'application démarre via systemd et survit à un redémarrage.
3.  L'API écoute uniquement sur loopback par défaut.
4.  L'interface affiche CPU, RAM, stockage, uptime et réseau avec unités
    correctes.
5.  Les données indisponibles sont identifiées comme telles.
6.  Les erreurs d'un module n'empêchent pas les autres de fonctionner.
7.  L'état d'Ollama et la liste de modèles sont visibles si Ollama est
    présent.
8.  L'état d'OpenWebUI est affiché si l'URL est configurée.
9.  Docker/Podman sont détectés et les conteneurs affichés en lecture
    seule si l'accès est autorisé.
10. Les journaux sont limités en taille et rendus sans interprétation
    HTML.
11. Aucune commande shell arbitraire ne peut être déclenchée via l'API.
12. Les actions de mutation sont absentes ou désactivées par défaut dans
    le MVP.
13. Aucun secret n'apparaît dans les logs ou l'export de diagnostic.
14. L'application fonctionne sans accès Internet une fois installée.
15. Le test automatisé et le build passent dans la CI.

### P1 --- Première évolution

-   actions de service et conteneur avec confirmation ;
-   alertes configurables ;
-   historique de métriques court ;
-   export de diagnostic expurgé ;
-   détection GPU améliorée ;
-   accessibilité et documentation d'administration.

### P2 --- Évolutions futures

-   modules additionnels ;
-   sauvegardes locales ;
-   gestion plus poussée du stockage ;
-   éditeur de configuration sécurisé ;
-   intégration d'autres runtimes IA ;
-   accès réseau privé, uniquement après conception de sécurité dédiée.

------------------------------------------------------------------------

## 11. Plan de développement par étapes

### Étape 0 --- Cadrage technique

-   choisir et documenter la version Debian cible ;
-   vérifier la disponibilité des APIs et commandes requises ;
-   définir le modèle de sécurité ;
-   initialiser dépôt, conventions, licences et CI.

**Livrable :** ADR (décisions d'architecture), structure du dépôt et
pipeline vert.

### Étape 1 --- Squelette applicatif

-   frontend React/TypeScript ;
-   backend FastAPI ;
-   endpoint de santé ;
-   navigation et thème ;
-   configuration et logs ;
-   écoute loopback.

**Validation :** installation de développement, interface accessible
localement, tests de base réussis.

### Étape 2 --- Collecte système en lecture seule

-   CPU, RAM, swap, uptime, stockage et réseau ;
-   processus ;
-   rafraîchissement périodique ;
-   états d'indisponibilité ;
-   graphiques avec fenêtre courte.

**Validation :** comparaison des valeurs avec des outils Debian connus
et tests sur données simulées.

### Étape 3 --- Modules IA locale

-   adaptateur Ollama ;
-   liste de modèles ;
-   détection OpenWebUI ;
-   timeouts et erreurs ;
-   panneau de ressources IA si données fiables.

**Validation :** cas Ollama présent, absent, arrêté et lent ; aucun
secret exposé.

### Étape 4 --- Modules conteneurs en lecture seule

-   détection Docker/Podman ;
-   liste et détail des conteneurs ;
-   logs limités ;
-   gestion des permissions insuffisantes.

**Validation :** l'interface reste fonctionnelle sans moteur installé et
sans socket accessible.

### Étape 5 --- Services et journaux

-   inventaire des unités pertinentes ;
-   état des services ;
-   lecture bornée des journaux ;
-   filtres et masquage.

**Validation :** absence d'injection, erreurs de permission explicites,
volumes bornés.

### Étape 6 --- Alertes et persistance

-   SQLite ;
-   règles et événements d'alertes ;
-   préférences ;
-   rétention et export expurgé.

**Validation :** migrations testées, seuils vérifiés, aucune télémétrie.

### Étape 7 --- Actions contrôlées

Uniquement après revue de sécurité : - actions nommées pour les services
et conteneurs ; - confirmations explicites ; - liste blanche ; - agent
privilégié séparé si nécessaire ; - audit des actions.

**Validation :** tests d'injection, refus par défaut, aucun endpoint de
shell générique.

### Étape 8 --- Packaging Debian

-   paquet `.deb` ;
-   unités systemd durcies ;
-   configuration et données séparées ;
-   installation, mise à jour et désinstallation ;
-   documentation de dépannage.

**Validation :** installation propre et mise à jour sur machine Debian
de test.

### Étape 9 --- Stabilisation

-   revue sécurité ;
-   tests de charge raisonnables ;
-   accessibilité ;
-   documentation utilisateur et développeur ;
-   version `1.0.0`.

**Validation :** tous les P0 sont verts et les limitations connues sont
documentées.

------------------------------------------------------------------------

## 12. Structure de dépôt suggérée

``` text
localcockpit/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── modules/
│   │   ├── api/
│   │   └── styles/
│   └── tests/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── security/
│   │   ├── collectors/
│   │   ├── modules/
│   │   │   ├── system/
│   │   │   ├── services/
│   │   │   ├── ai/
│   │   │   └── containers/
│   │   ├── storage/
│   │   └── main.py
│   └── tests/
├── privileged-agent/       # seulement si nécessaire
├── packaging/
│   ├── debian/
│   └── systemd/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   ├── INSTALL.md
│   ├── API.md
│   └── TESTING.md
├── scripts/
├── .github/workflows/
├── pyproject.toml
├── package.json
├── README.md
├── LICENSE
└── CHANGELOG.md
```

La structure est indicative : Codex peut l'adapter, mais doit préserver
la séparation frontend/backend, modules, sécurité, tests et packaging.

------------------------------------------------------------------------

## 13. Documentation obligatoire

-   `README.md` : objectif, captures, prérequis, démarrage rapide.
-   `INSTALL.md` : installation Debian, configuration, désinstallation
    et dépannage.
-   `ARCHITECTURE.md` : processus, flux, modules, frontières de
    privilèges.
-   `SECURITY.md` : modèle de menace, limites, signalement des
    vulnérabilités.
-   `API.md` : routes, schémas, erreurs et exemples.
-   `TESTING.md` : exécution des tests et environnements simulés.
-   `CHANGELOG.md` : modifications par version.
-   Guide utilisateur : interprétation des métriques, alertes et états
    d'intégration.

------------------------------------------------------------------------

## 14. Instructions impératives pour Codex

1.  Inspecter le dépôt existant avant de modifier quoi que ce soit.
2.  Présenter un plan de réalisation par étapes et conserver un état
    d'avancement.
3.  Implémenter les étapes dans l'ordre, sans générer toute
    l'application en un seul bloc non testé.
4.  Pour chaque étape, écrire les tests correspondants avant de déclarer
    la tâche terminée.
5.  Ne jamais inventer une API, une métrique ou une capacité
    d'Ollama/OpenWebUI/Docker : vérifier la documentation et gérer les
    différences de version.
6.  Ne pas ajouter de cloud, analytics, télémétrie, PostgreSQL ou
    service externe.
7.  Ne pas activer de commande privilégiée ou d'action destructive sans
    conception et tests de sécurité.
8.  Ne pas utiliser `shell=True`, ni exposer une route d'exécution de
    commande générique.
9.  Garder les dépendances optionnelles réellement optionnelles.
10. Après chaque étape, lancer lint, vérification de types, tests et
    build ; corriger les échecs avant de continuer.
11. Fournir les fichiers réellement créés/modifiés, les commandes de
    test exécutées et leurs résultats.
12. Ne jamais affirmer qu'une fonction est implémentée si elle n'est pas
    reliée de bout en bout et couverte par un test pertinent.
13. Marquer explicitement `IMPLÉMENTÉ`, `PARTIEL`, `ABSENT` et
    `NON TESTÉ` dans le rapport de conformité.
14. Terminer par une revue de sécurité, une procédure d'installation
    reproductible et une liste des limites connues.

------------------------------------------------------------------------

## 15. Définition de « terminé »

La version 1.0 est terminée lorsque : - les critères P0 sont tous
validés ; - l'installation `.deb` est testée sur la Debian cible ; - les
tests frontend, backend, intégration et sécurité passent ; -
l'application reste utilisable si Ollama, OpenWebUI et Docker/Podman
sont absents ; - l'écoute réseau et les privilèges sont vérifiés ; - la
documentation permet d'installer, configurer, dépanner et désinstaller
; - un rapport de conformité relie chaque exigence à des fichiers et
tests réels.

**Recommandation finale :** livrer d'abord un MVP strictement en lecture
seule. Ajouter les opérations de redémarrage/arrêt et tout agent
privilégié uniquement après validation de l'architecture, des tests
d'autorisation et du modèle de menace. Cette stratégie réduit fortement
le risque tout en donnant rapidement un outil utile au quotidien.
