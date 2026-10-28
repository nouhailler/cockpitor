# L5 — autorité de session dans un processus séparé

État au 28 octobre 2026 : canal Unix en lecture seule implémenté et testé avec
une autorité dans un vrai processus Python enfant. Les deux processus du banc
restent non privilégiés sous le même UID. Aucun lancement par l'application,
aucun auxiliaire root, aucune action système activée.

## Composants et frontière

session_authority.py fournit SessionAuthorityServer, SessionAuthorityClient et
RemoteSessionVerificationServer. L'autorité possède seule l'objet Sessions ;
le vérificateur distant n'en reçoit ni référence mémoire ni jeton de connexion.
Les contrôles de session sont désormais asynchrones. Le serveur historique avec
référence Sessions directe reste disponible pour les tests locaux.

L'autorité réutilise le transport privé existant : dossier propriétaire 0700,
socket 0600, chemin sans alias symbolique, refus de chemin existant, UID Linux
SO_PEERCRED contrôlé aux deux extrémités, lancement root refusé. Le client vérifie
le propriétaire et les permissions avant connexion. Ce mécanisme authentifie la
frontière de compte Unix ; il n'isole pas les programmes malveillants du même UID.

## RPC strictement en lecture

Une requête v1 check_sessions contient un nonce aléatoire de 128 bits et de un à
seize identifiants de session opaques, distincts et exactement hexadécimaux de
64 caractères. L'autorité appelle Sessions.valid_owner ; elle ne peut créer,
révoquer ou approuver une session via ce canal. Il n'existe pas de commande système,
chemin de cible ou argument libre dans le schéma.

La réponse contient version, nonce identique et une liste de booléens stricts dans
le même ordre. Nonce incohérent/rejoué, longueur incorrecte, champs supplémentaires,
version inconnue ou valeurs coercibles comme 1 sont refusés. Ni jeton brut ni
identifiant de session ne figure dans la réponse. Le nonce lie la réponse à la
requête ; il ne constitue pas une approbation humaine.

Le cadrage est celui du transport : longueur réseau sur quatre octets et JSON de
2 Kio maximum, une requête par connexion et quatre connexions traitées simultanément.
Le client découpe au plus 256 identifiants uniques par lots de seize. Chaque RPC a
un délai nominal de 200 ms, et l'ensemble des lots de 400 ms, plus le nettoyage de
connexion borné à 100 ms. Ces limites asyncio supposent une boucle coopérative.

Aucune réponse positive n'est mise en cache. Si un lot échoue, aucun résultat
partiel ne devient une autorisation. Un lot n'est pas un instantané transactionnel
avec le processus distant ; chaque session est consultée au moment de sa lecture.
Les refus et exceptions sont expurgés.

## Révocation et panne

Le moniteur du vérificateur consulte périodiquement l'autorité par ce canal, sans
passer par l'admission des connexions du vérificateur. Les contrôles entourant les
sondes consultent également l'autorité, sans repli local en cas de panne.

- Session absente, révoquée ou expirée : les tickets de cette session sont invalidés.
- Autorité inaccessible, arrêtée, saturée, réponse invalide ou délai dépassé : tous
  les tickets connus du vérificateur sont invalidés, y compris ceux enregistrés
  pendant l'attente du contrôle périodique.
- Panne ou révocation pendant une sonde : aucune validation ne peut utiliser un
  ticket dont l'invalidation a été constatée avant la fin de la vérification.
- Retour de l'autorité : une nouvelle réponse valide peut autoriser de nouveaux
  contrôles, mais ne ressuscite jamais les anciens tickets ou identifiants réservés.

Le passage périodique est nominalement de 50 ms auquel s'ajoute le coût du canal ;
ce n'est pas une garantie temps réel. La dernière vérification d'autorité et l'envoi
d'une réponse ne sont pas une transaction atomique entre processus. Le protocole
ne réalise aucune mutation et ne prétend pas annuler un effet passé.

## Preuves

20 nouveaux tests dans test_remote_session_authority.py : autorité réellement dans
un autre PID, deux sessions indépendantes, révocation et expiration dans l'enfant,
arrêt brutal de l'autorité, panne pendant une sonde, nonce rejoué, réponses falsifiées,
UID incohérent, schémas non modifiants, découpage en lots et refus des résultats
partiels, timeout après réponse positive et socket absente.

La fixture session_authority_fixture.py dispose d'un contrôle stdin **uniquement
pour les tests**. Ce contrôle provoque révocation/avancée d'horloge/arrêt dans l'enfant ;
ce n'est pas une commande du RPC et il n'est ni installé ni utilisé par le lanceur.
Les tests nettoient leurs processus et sockets temporaires, sans service ni moteur réel.

```sh
.venv/bin/pytest -q backend/tests/test_remote_session_authority.py
```

Total : 440 tests backend et 26 frontend passants, lint/types/format/build passants.
La base applicative reste v3, le journal de fixtures v2. Aucun nouvel état persistant.

## Qualification restante

Le canal vérifie l'identité Unix et la fraîcheur de ses réponses, mais ne prouve
pas une approbation indépendante du moteur applicatif et ne sépare pas deux UID
de privilèges différents. Il reste à qualifier les vrais pilotes bornés, les
permissions minimales, les clés/approbations entre composants et les essais
systemd/Docker/Podman dans une VM jetable. Aucun de ces droits n'est accordé par
le succès du banc, et aucune variable d'activation système n'est ajoutée.
