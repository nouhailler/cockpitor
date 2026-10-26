# L5 — adaptateurs et postconditions sur banc de fixtures

État au 26 octobre 2026 : logique d'adaptateurs et journal de qualification livrés.
**Aucune action sur systemd, Docker ou Podman réels n'est activée ou qualifiée.**
La machine de développement ne possède ni VM/KVM ni moteur Docker/Podman.

## Ce qui est livré

`backend/app/fixture_adapters.py` fournit deux adaptateurs qui exigent leurs fonctions
de lecture et d'envoi à la construction. Il n'existe aucun lanceur systemctl,
client de moteur, accès socket par défaut, variable d'environnement ou route web
capable de les activer. Les pilotes d'entrée/sortie sont fournis uniquement par
les tests. Les adaptateurs ne sont pas des SimulationVerifier et ne sont jamais
injectés dans ActionEngine : une modification de fixture ne doit pas être annoncée
comme une simulation applicative sans effet.

Le banc compile des opérations fixes à partir d'ActionRequest, revalidé dans chaque
adaptateur. Les services critiques et les arguments libres restent refusés.
L'autorisation positive du banc porte sur le triplet exact action/cible/moteur.

| Type | Opération construite pour le pilote de fixture |
| --- | --- |
| service.start/stop/restart | tuple `/usr/bin/systemctl --no-pager --no-ask-password <verbe> -- <unité exacte>` |
| container.start | POST `/containers/<identifiant complet>/start` |
| container.restart | POST `/containers/<identifiant complet>/restart?t=5` |

Les tests de processus vérifient le tuple, puis exécutent **un programme Python de
fixture à sa place**, jamais systemctl. Les tests HTTP utilisent un serveur Unix
créé dans un répertoire temporaire, jamais le socket d'un moteur réel. Le préfixe
API v1.47 est fixé dans ce seul pilote de test ; aucune négociation avec un vrai
moteur n'a été qualifiée. Un statut 204 est exigé exactement pour l'accusé conteneur ;
il ne suffit pas pour déclarer la réussite.

## Déroulement d'un essai

1. Réserver l'identifiant dans le journal privé, puis vérifier le contrôle de session
   et d'échéance fourni par le banc. Aucun jeton d'approbation n'est accepté ici.
   Le rapprochement avec une autorisation privilégiée réelle reste à concevoir.
2. Lire une observation strictement typée, vérifier cible/configuration, comparer
   l'empreinte attendue et refuser les états initiaux non pris en charge.
3. Valider le journal `dispatching`, refaire une lecture concordante et un contrôle
   d'autorisation juste avant l'appel au pilote injecté. Une course après cette lecture
   reste possible et n'est pas présentée comme éliminée.
4. Envoyer une seule fois. Dès l'entrée dans le pilote, une erreur, réponse ambiguë,
   annulation, révocation ou timeout est considérée comme un résultat inconnu.
5. Relire l'état jusqu'à confirmation de la postcondition, avec configuration identique,
   puis valider le journal `verified`. Une panne du journal empêche tout succès retourné.

Une seule opération par instance de banc. Les lectures sont limitées à une seconde,
l'envoi à deux secondes et les contrôles après envoi à deux secondes, espacés de 50 ms.
Ces limites asyncio supposent des pilotes coopératifs ; elles ne qualifient pas
l'annulation d'un sous-processus ou d'un moteur réel. Les écritures SQLite locales
ont une attente de verrou de 250 ms ; ce banc synchrone n'est pas destiné à être
branché tel quel sur la boucle de l'API.

## Postconditions, volontairement étroites

| Action | État initial accepté | Preuve après opération |
| --- | --- | --- |
| Service start | inactive/dead, PID 0 | active/running, PID positif et invocation non nulle nouvelle |
| Service stop | active/running, PID positif, invocation valide | inactive/dead, PID 0 |
| Service restart | active/running, PID positif, invocation valide | active/running et nouvelle invocation non nulle |
| Container start | created/exited, running=false | running et nouvelle date UTC de démarrage valide |
| Container restart | running et date UTC valide | running et date de démarrage strictement postérieure |

L'identité exacte et l'empreinte de configuration sont revérifiées. Les unités
nécessitant daemon-reload sont refusées, sans reload automatique. Les services
oneshot, les états transitoires initiaux et les conteneurs paused/restarting ne sont
pas pris en charge. Une date future ou sentinelle ne constitue pas une preuve ;
la comparaison de dates utilise la précision microseconde de Python et peut donc
refuser prudemment deux générations différant uniquement en nanosecondes.
`running` ne prouve ni la santé applicative, ni la disponibilité durable. Aucune
vérification métier ou garantie de retour arrière n'est déduite de ces postconditions.

## Journal persistant indépendant

`fixture_journal.py` crée seulement sur demande explicite `fixture-trials.sqlite3`,
dans un dossier propriétaire 0700, fichier 0600, sans liens symboliques. Root est
refusé à l'initialisation. Le schéma de ce journal est v2 (migration v1 sauvegardée) ; la base de l'application
reste en v3. Aucun nom de cible, instantané, jeton ou commande n'est persisté :
identifiant, type d'action, état, date, empreintes opaques et événements corrélés.
La liaison persistante à la cible et à l'empreinte d'origine empêche une nouvelle
réservation tant qu'un résultat reste inconnu.

État et événement sont écrits dans la même transaction, avec contrôle de l'état
précédent. L'essai est soit `not_dispatched`, `verified`, soit `unknown`.
Au démarrage exclusif d'un banc, `prepared` devient `not_dispatched`, tandis que
`dispatching` devient `unknown`. L'absence d'accusé ne prouve pas l'absence d'effet.
Un journal déjà ouvert par un banc actif ne doit pas être initialisé par un autre
processus ; la coordination de déploiement reste hors périmètre.

Les 256 identifiants ne sont jamais évincés : saturation et doublons sont refusés,
même après redémarrage. Au plus quatre événements par essai avec réconciliation, soit 1024 événements.
Aucune relance automatique, aucun retour arrière automatique et aucune promesse
qu'une annulation a annulé l'effet. Une erreur d'audit final laisse l'intention
`dispatching` ; la reprise la classe inconnue. La [réconciliation en lecture seule](FIXTURE_RECONCILIATION.md) peut lever le blocage
du banc si l'observation d'origine et deux nouvelles lectures concordent. Elle ne
qualifie pas la réconciliation de ressources réelles avant activation.

## Preuves et limites

```sh
.venv/bin/pytest -q backend/tests/test_fixture_adapters.py
```

70 tests couvrent commandes/requêtes fixes, états initiaux, configurations changées,
identités, preuve de génération, accusés trompeurs, erreurs/timeouts, annulation,
révocation, concurrence, quota, rejeu persistant, rollback d'audit, permissions et
reprise après sortie abrupte d'un processus enfant. Un processus Python modifie un
fichier JSON temporaire ; quatre essais HTTP Unix contrôlés exercent les combinaisons
Docker/Podman et start/restart, sans moteur réel.

Total du projet : 379 tests backend et 26 frontend passants ; lint, types, formatage
et build passants. Ces essais ne remplacent pas la [matrice VM](EXECUTOR_QUALIFICATION.md).
Il reste à implémenter/qualifier les vrais pilotes bornés, les privilèges minimaux,
la révocation distante, les clés inter-processus et la réconciliation après effets
partiels. L'interface, l'IA et le transport Unix v2 restent incapables d'envoyer
une mutation réelle. Aucun endpoint execute n'a été ajouté.
