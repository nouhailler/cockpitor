# Fichiers locaux et sauvegardes des préférences

## Portée livrée

Menu → Données locales → Fichiers / Sauvegardes, FR/EN.

L’explorateur liste et filtre le dossier courant, affiche un aperçu texte UTF-8
expurgé et télécharge l’original. Il n’écrit aucun fichier et n’extrait aucune
archive. Aperçu : 16 Kio ; téléchargement : 1 Mio ; 500 entrées examinées par
liste, filtre littéral limité à ces entrées ; profondeur maximale 16 composants.
Deux lectures concurrentes au maximum. Choisir des dossiers sur un système de
fichiers local fiable : les limites de volume ne garantissent pas un délai maximal
si un montage ou le noyau bloque une lecture.

Aucun dossier n’est accessible par défaut. Configurer au lancement, par exemple :

```sh
export LOCALCOCKPIT_FILE_ROOTS='[{"id":"documents","label":"Documents","path":"/chemin/absolu/vers/documents"}]'
.venv/bin/python scripts/serve.py
```

Remplacer le chemin par un dossier existant explicitement choisi. Ne pas ajouter
un dossier contenant des secrets. Au maximum huit racines, identifiants uniques.
Une configuration invalide refuse toutes les racines sans exporter leurs chemins.
Les permissions Unix ordinaires restent applicables ; aucun sudo ni droit ajouté.

Chaque ancêtre est ouvert avec O_DIRECTORY/O_NOFOLLOW ; l’identité de la racine
est vérifiée et les descendants sont ouverts par dir_fd. Traversée, liens
symboliques, fichiers spéciaux, fichiers à plusieurs liens physiques et changement
de périphérique sont refusés. /, /proc, /sys et /dev ne peuvent être des racines.
Les dossiers .ssh/.aws/.git/.codex/.agents/.localcockpit, fichiers .env/.env.* et le
répertoire privé de données applicatives sont exclus. Ce filtre n’est pas un
inventaire universel de secrets : le choix de la racine reste une autorisation de
lecture de son contenu. Les changements de métadonnées pendant une lecture sont
refusés ; ce contrôle ne fournit pas un snapshot transactionnel du système de fichiers.

L’aperçu utilise le masquage commun, partiel. Le téléchargement est l’original,
non expurgé, envoyé en pièce jointe application/octet-stream. Aucun HTML/SVG n’est
rendu et aucun contenu de fichier n’est envoyé automatiquement à l’IA.

## Sauvegarde et restauration

Le format JSON `cockpitor.preferences`, version 1, sauvegarde uniquement les
préférences Cockpitor et les règles d’alerte. Il inclut les noms/cibles des règles.
Il exclut les fichiers explorés, bases SQLite, conversations, clés, sessions,
chemins de racines et configurations de services ou moteurs.
Le SHA-256 porte sur les réglages normalisés : détection de corruption des réglages,
pas signature, chiffrement ou preuve d’origine. Importer une copie de confiance.

1. Confirmer puis exporter les préférences : audit obligatoire avant réponse.
2. Charger un fichier JSON de 32 Kio maximum ou coller son contenu.
3. Examiner les différences. Schéma strict, doublons et nombres non finis refusés.
4. Confirmer la restauration dans les 120 secondes.
5. Une copie privée de récupération est enregistrée et synchronisée sur disque
   avant l’écriture. Les réglages et l’audit backups.restore sont transactionnels.
6. La langue, le thème et le rafraîchissement restaurés s’appliquent immédiatement.

Le plan est lié à la session et à l’empreinte des réglages précédents, consommé
une seule fois et borné à 32 plans en attente. Session recontrôlée après copie.
Une transaction BEGIN IMMEDIATE recompare les réglages avant remplacement ; une
modification concurrente oblige à refaire l’aperçu. Copie impossible ou audit en
panne = pas de remplacement. Après entrée dans la transaction locale, une
annulation HTTP attend la fin avant de libérer le verrou ; en cas de réponse perdue,
consulter les réglages et l’audit plutôt que rejouer le plan.

Les copies `preferences-backup-<id>.json` restent dans le dossier privé de données,
mode 0600, sans écrasement ; au maximum 20, sans suppression automatique. Les
interfaces permettent de les télécharger puis de les réimporter par le même examen.
À la limite, conserver les téléchargements et archiver manuellement les anciennes
copies avant de reprendre. La base applicative reste en version 3.

## Validation et suites

514 tests backend et 44 frontend, dont 37 tests de confinement/restauration et
cinq scénarios frontend nouveaux. Restauration effective sur SQLite et répertoire
temporaires, refus de révocation/expiration/rejeu, concurrence et audit en panne.
Parcours navigateur réel sur instance temporaire : exploration, aperçu, export
audité, examen fr→en, restauration et copie de récupération. Capture files-fr.jpg :
interface réelle avec dossiers/fichier de test explicitement temporaires.

Restent hors de ce lot : recherche récursive, images, édition, transfert,
suppression récupérable, archives et sauvegarde/restauration de fichiers ou du
système. Ces écritures ne sont pas activées par la restauration des préférences.
