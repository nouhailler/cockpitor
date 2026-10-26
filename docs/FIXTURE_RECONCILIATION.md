# L5 — réconciliation en lecture seule et blocage par cible

État au 26 octobre 2026 : implémenté sur le banc de fixtures, sans connexion à
l'interface, au lanceur, à l'IA ou au protocole Unix de vérification. Aucun pilote
systemd/Docker/Podman réel n'est activé ou qualifié.

## Blocage persistant

Chaque nouvel essai du banc réserve, dans une transaction SQLite, une empreinte
HMAC-SHA256 de la cible : famille service/conteneur, unité ou identifiant exact,
et moteur lorsqu'il existe. Le verbe n'en fait pas partie : un redémarrage inconnu
bloque aussi un démarrage ou un arrêt sur la même cible. Docker et Podman restent
deux ressources distinctes même si leurs identifiants sont identiques.

Les états prepared, dispatching et unknown empêchent une nouvelle réservation de
cette cible, y compris depuis une autre instance du banc ou après redémarrage.
Le contrôle et l'insertion sont exécutés sous BEGIN IMMEDIATE ; le verrou en mémoire
d'une seule instance n'est donc pas le seul contrôle. Aucun identifiant existant
n'est réutilisable, même après réconciliation.

Le journal ne conserve ni cible en clair ni observation d'origine. Il ajoute
resource_digest et approved_fingerprint ; une clé aléatoire de 256 bits et son
contrôle d'intégrité restent dans les métadonnées de la base privée. Une clé perdue,
tronquée ou modifiée sans contrôle concordant provoque un refus, jamais une nouvelle
clé silencieuse qui oublierait les blocages. Les empreintes ne sont pas un chiffrement
et ne protègent pas d'un acteur pouvant modifier l'ensemble du journal sous le même UID.

## Réconciliation sans envoi

L'appel interne reconcile_fixture exige l'identifiant d'essai, la requête exacte,
l'observation d'origine et le contrôle de session/échéance du banc. L'observation
d'origine est fournie à nouveau par le contrôleur de test ; elle doit être typée,
correspondre à la cible et retrouver exactement l'empreinte réservée. Si elle a été
perdue, le banc ne fabrique pas de preuve et le blocage reste en place.

1. Vérifier les droits positifs, le lien cible/action/empreinte et l'état unknown
   avant de lire la ressource.
2. Relire l'état avec délai borné et retrouver la postcondition prévue par
   [l'adaptateur](ADAPTER_TRIALS.md) : génération renouvelée ou arrêt confirmé,
   avec configuration identique.
3. Relire une seconde fois ; les deux observations complètes doivent concorder.
   Les contrôles de session/échéance entourent chaque lecture.
4. Dans une transaction, revérifier le lien et l'état unknown, puis écrire l'état
   reconciled et son événement corrélé. Une erreur d'audit annule la libération.

Aucune fonction d'envoi n'est appelée. Le résultat indique reconciled ou unconfirmed,
avec scope=fixture_only. Une lecture indisponible, changeante, expirée, une révocation
ou une postcondition non satisfaite laisse unknown et le blocage. Une annulation
interrompt l'attente sans modifier le journal. Deux réconciliateurs concurrents ne
peuvent pas tous deux valider la même résolution.

reconciled signifie que la postcondition est maintenant observée. Il ne prouve pas
que l'opération interrompue en est la cause et ne réécrit pas son histoire en verified :
l'événement unknown est conservé. Il ne déclenche aucune nouvelle opération et ne
réutilise aucune approbation. Un nouvel essai demande un nouvel identifiant et ses
propres contrôles explicites. Les échecs de lecture n'ajoutent pas d'événements sans
borne : un essai comporte au plus quatre événements, soit 1024 pour 256 essais.

## Migration du journal de banc

Le journal autonome passe de v1 à v2 ; la base principale de Cockpitor reste v3.
Avant migration, une sauvegarde SQLite cohérente de mode 0600 est créée dans le dossier
0700 du journal. Ajout des colonnes, métadonnées, changement de version et reprise sont
transactionnels. Une panne laisse le schéma antérieur et sa sauvegarde. Les versions
futures sont refusées. L'initialisation reste réservée au démarrage exclusif d'un banc,
jamais à un processus rejoignant un essai vivant.

Un ancien essai v1 inconnu ne peut pas être lié rétroactivement à une cible, faute
de métadonnées. Il bloque donc toutes les nouvelles réservations dans ce journal.
Aucune commande de forçage ou d'effacement n'est fournie. Un ancien prepared récupéré
en not_dispatched ne crée pas ce blocage. Les appels internes de réservation sans
liaison explicite restent possibles pour les tests historiques, mais un essai ainsi
ouvert bloque toutes les cibles tant qu'il est non terminal.

## Validation et limites

30 tests supplémentaires : parcours service/conteneur et chaque postcondition,
absence de nouvel envoi, blocage inter-verbes après réouverture, mauvais lien,
lectures changeantes, timeout, révocation, annulation, rollback d'audit, concurrence,
clé absente/corrompue, migration sauvegardée et migration interrompue. Total :
379 tests backend et 26 frontend passants, lint/types/format/build passants.

```sh
.venv/bin/pytest -q backend/tests/test_fixture_reconciliation.py
```

Ce mécanisme ne remplace pas une preuve d'approbation à une frontière privilégiée,
une révocation distante, une gestion des clés entre processus réels ou les essais
systemd/Docker/Podman dans une VM jetable. Il réduit les risques de relance du banc ;
les opérations sensibles de l'application restent désactivées.
