# Historique — Cockpitor

## Non publié

### Kit de préparation à la qualification VM — 28 octobre 2026

- Précontrôle CLI en lecture seule : VM/non-conteneur, Debian, compte non root,
  systemd, Python et révision propre ; profils systemd/docker/podman/all.
- Version moteur en GET uniquement, sockets explicitement choisies et ignorées si
  environnement inadapté. Aucun installateur, droit ou opération sensible.
- JSON FR/EN expurgé, rapport privé nouveau sans écrasement ; prérequis disponibles
  ne signifient jamais qualified=true ou activation système.
- 25 tests nouveaux, 465 backend et 26 frontend passants. Qualification réelle
  et revue des pilotes/privilèges toujours requises sur VM jetable.

### Autorité de session séparée — 28 octobre 2026

- RPC Unix en lecture seule : UID du pair, chemins privés, nonce par requête,
  schémas stricts, lots bornés et réponses sans jetons bruts.
- Vérificateur distant sans cache positif ni repli local : panne, délai dépassé
  ou résultat partiel invalide les tickets connus ; contrôle des sessions asynchrone.
- 20 tests nouveaux, dont une autorité dans un processus Python réellement distinct ;
  total 440 backend et 26 frontend passants.
- Aucun pilote système, compte privilégié ou lancement par l'application. Séparation
  de privilèges et qualification VM toujours non réalisées.

### Révocation de session sur le banc Unix — 27 octobre 2026

- Serveur de laboratoire avec autorité Sessions de confiance et contrôle périodique
  indépendant des clients et de l'admission des connexions.
- Scope obligatoire dans ce mode, lien immuable opération/session, vérifications
  autour des sondes et liaison au propriétaire ActionEngine côté client.
- Révocation de tous les tickets de la session après déconnexion/expiration, même
  si le client a perdu la réponse. Autorité indisponible : refus et invalidation.
- 21 tests nouveaux, 420 backend et 26 frontend passants. Autorité encore dans le
  même processus de banc ; séparation privilégiée et qualification VM non réalisées.

### Révocation ponctuelle Unix — 27 octobre 2026

- Message revoke v2 authentifié par UID et ticket ; invalidation d'une lecture
  en cours sans attendre le verrou de sonde, accusé strict et rejeu refusé.
- Validation unique des capacités consommées et nettoyage des lectures interrompues.
- Client : tentative bornée de révocation après réception du ticket lors d'un échec
  ou d'une annulation, sans masquer l'erreur initiale ni relance automatique.
- 20 tests nouveaux, 399 backend et 26 frontend passants. Révocation globale par
  session et qualification VM encore absentes ; aucune action système activée.

### Réconciliation sans envoi et blocage persistant — 26 octobre 2026

- Les essais préparés/en cours/inconnus bloquent une nouvelle réservation de la même
  cible pour tous les verbes, par empreinte opaque persistante et transaction SQL.
- Réconciliation en lecture seule liée à l'observation d'origine : deux lectures
  concordantes, audit obligatoire et état reconciled distinct du succès initial.
- Journal de banc v2 avec sauvegarde v1, gestion prudente des anciens inconnus et
  refus en cas de clé perdue ; base applicative v3 inchangée.
- 30 tests nouveaux, 379 backend et 26 frontend passants ; aucun nouvel envoi lors
  d'une réconciliation. Pas d'activation système ou de pilote réel.

### Adaptateurs et postconditions sur fixtures — 24 octobre 2026

- Opérations services/conteneurs compilées à arguments et chemins fixes, sans pilote
  système ou moteur par défaut ; autorisations positives et cibles revalidées.
- Deux lectures avant envoi, preuve de nouvelle génération et de configuration stable
  après opération ; un accusé seul ne constitue pas un succès.
- Journal privé de laboratoire indépendant, états/événements transactionnels, quota
  sans éviction, reprise inconnue après intention d'envoi et refus des rejeux persistants.
- 70 tests supplémentaires, dont processus Python et sockets HTTP Unix de fixtures ;
  total 349 backend et 26 frontend. Aucun appel à systemctl ou Docker/Podman réels.
- Aucun branchement API/IA/lanceur ; qualification VM et pilotes réels toujours requis.

### Liaison approbation, audit et vérification Unix — 24 octobre 2026

- Client Unix borné et contrôlé : permissions privées, identité noyau du serveur,
  schémas stricts, identifiant/empreinte concordants, aucun repli ni rejeu automatique.
- Protocole réseau v2 : empreinte approuvée obligatoire dès l'émission du ticket ;
  anciennes requêtes v1 refusées. Politique interne inchangée.
- Vérificateur optionnel du moteur de simulation, contrôles de session/échéance
  autour de chaque échange et événement corrélé actions.transport_verified obligatoire.
- 40 tests de liaison sur sockets réelles et trois tests v2 ; total 279 backend et
  26 frontend. Schéma SQLite v3 conservé, erreur du client traduite FR/EN.
- Liaison limitée au banc : aucun branchement dans le lanceur, ni mutation système.
  Adaptateurs, révocation distante et qualification VM restent à traiter.

### Transport de vérification L5 — 24 octobre 2026

- Serveur de laboratoire Unix Linux : UID noyau SO_PEERCRED, répertoire privé et
  socket 0600, refus des chemins existants et du lancement sous root.
- Trames JSON strictes et bornées, délais, quatre connexions traitées maximum,
  sondes sérialisées, consommation avant seconde lecture et arrêt avec invalidation.
- 32 nouveaux tests sur sockets réelles et un test de fermeture de la politique ;
  total de 236 tests backend et 26 frontend passants.
- Aucun adaptateur de mutation, route d'exécution, auxiliaire privilégié ou liaison IA.
  Qualification VM et liaison aux approbations/audit toujours requises.

### Préparation du protocole L5 — 24 octobre 2026

- Politique isolée du futur exécuteur : droits positifs, identité attendue, tickets
  expirants non rejouables et revalidation de la cible ; aucune commande exécutée.
- 24 tests unitaires du protocole et dossier de qualification VM restant à réaliser.
- Aucun transport ni activation des opérations sensibles ajouté.

### Actions contrôlées en simulation — 24 octobre 2026

- Plans typés, cibles exactes, services critiques exclus et état/configuration revérifiés.
- Approbation ponctuelle expirante liée à la session, empreinte et jeton consommé une fois.
- Simulation bornée, verrouillage, annulation et refus en cas de panne d’audit.
- SQLite v3 sauvegardé avant migration : états minimaux, audit atomique et reprise en interrupted.
- Page Actions contrôlées FR/EN et historique persistant, capture réelle ajoutée.
- 179 tests backend et 26 frontend ; parcours cron.service simulé en navigateur.
- Aucun exécuteur, helper privilégié ou changement de ressource ajouté. Qualification réelle avant L5 restante.


### Architecture, sessions, supervision et assistant — 23 octobre 2026

- API répartie en routeurs, erreurs unifiées et capacités explicites sans action système.
- Composants React extraits, navigation par domaines et traductions FR/EN complétées.
- Sessions expirables/révocables hachées en mémoire, échanges initiaux protégés,
  limitation des connexions et activité utilisateur distincte des lectures automatiques.
- SQLite v2 avec sauvegarde de migration, tendances CPU/RAM et conversations facultatives bornées.
- Sondes réseau/disques/SMART/NVIDIA/services/APT/heure/alimentation/NUT en lecture seule.
- Assistant Ollama local avec aperçu de contexte, consentement, annulation, limites
  de génération et aucune exécution ; audit applicatif consultable.
- 138 tests backend et 22 frontend, parcours navigateur et modèle local réel vérifiés.
- Les opérations sensibles restent absentes ; aucun outil ni droit système installé.


### Diagnostic et français/anglais — 23 octobre 2026

- Export JSON local confirmé, borné et audité, construit par liste blanche.
- Exclusion des identités, chemins, adresses, logs, variables et jetons.
- Export disponible sans SQLite, avec audit indisponible explicitement signalé.
- Catalogues français/anglais partagés, choix immédiat et préférence persistante.
- Dates, nombres, unités et erreurs API localisés ; données externes conservées.
- 109 tests backend et 18 frontend ; téléchargement et langue vérifiés en navigateur.
- README anglais et captures réelles ajoutés. Aucune action système ajoutée.


### Préférences et alertes — 23 octobre 2026

- SQLite v1 privé, initialisation/migration avec sauvegarde, préférences et audit borné.
- Pages Paramètres et Alertes, thèmes clair/sombre/système et fréquence d’affichage persistants.
- Règles temporisées CPU/RAM/swap/disque, Ollama indisponible, service en échec et conteneur arrêté.
- Déduplication, résolution, rétention des événements et sources indisponibles explicites.
- PUT settings limité aux réglages applicatifs, protégé par authentification, origine et CSRF.
- Collecteur CPU isolé dans un thread dédié ; panne SQLite sans arrêt de la supervision.
- 97 tests backend et 13 frontend, captures réelles et documentation mises à jour.
- Aucune action sur le système, les services ou les conteneurs ajoutée.

### Conteneurs — 23 octobre 2026

- Inventaire filtrable par nom/image et état, sélection d’un moteur et d’un conteneur.
- Détails filtrés excluant environnement, commandes, labels et montages.
- Statistiques CPU calculées sur les compteurs fournis et mémoire brute avec limites.
- Journaux TTY/multiplexés bornés, périodes et nombre de lignes configurables.
- Négociation d’API Docker/Podman et erreurs explicites de version, état et permissions.
- Masquage des secrets commun aux journaux services et conteneurs.
- 75 tests backend et 9 tests frontend, dont un test de transport sur socket Unix réel contrôlé.
- Aucune opération sensible ajoutée ; moteurs réels encore non qualifiés.

### Fonctionnalités — 23 octobre 2026

- Page Services : recherche, pagination et filtres des unités système chargées.
- Détails de service : état, démarrage et dépendances via propriétés autorisées.
- Journaux par unité : période, niveau, recherche littérale et pagination par curseur.
- Erreurs de permissions explicites et masquage de motifs de secrets connus.
- Sous-processus sans shell, limites de durée/volume/concurrence et nettoyage testé.
- 41 tests backend et 6 tests frontend, documentation et capture du module mises à jour.
- Aucune opération sensible ajoutée.

### Documentation

- README enrichi avec icônes, tableaux, diagramme, checklist et capture réelle du tableau de bord.
- Ajout de CONTEXT.md : priorités, architecture, état du projet et règles de reprise.
- Préparation du dépôt GitHub `nouhailler/cockpitor` et exclusions des fichiers locaux sensibles.

## 0.1.0 — 22 octobre 2026

- Socle FastAPI local en lecture seule et interface React responsive clair/sombre.
- Collecte système, processus paginés, capteurs et historique CPU en mémoire.
- Surveillance Ollama/OpenWebUI et inventaire optionnel Docker/Podman.
- Tests de protections API, de collecte, d'intégrations et d'interface.
- Aucune opération sensible ; limites et conformité documentées.
