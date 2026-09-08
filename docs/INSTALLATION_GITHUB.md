# Publication avec GitHub Desktop

Ce guide suppose que le générateur a créé :

```text
clan-renard-bot/
clan-renard-bot.zip
```

Il est conseillé d'utiliser directement le dossier
`clan-renard-bot` plutôt que d'extraire le ZIP au même emplacement.

## 1. Vérifier le dossier généré

Le dossier doit contenir notamment :

```text
bot/
assets/
database/
docs/
scripts/
tests/
.env.example
.gitignore
Dockerfile
README.md
render.yaml
requirements.txt
```

Le véritable fichier `.env` ne doit pas être publié.

## 2. Ouvrir GitHub Desktop

Lance GitHub Desktop et connecte-toi à ton compte GitHub.

## 3. Ajouter le dossier comme dépôt

Dans GitHub Desktop, ouvre :

```text
File
> Add Local Repository
```

Sélectionne le dossier :

```text
clan-renard-bot
```

Si GitHub Desktop indique que le dossier n'est pas encore un dépôt,
clique sur :

```text
create a repository
```

## 4. Configurer le dépôt

Utilise par exemple :

```text
Name        : clan-renard-bot
Description : Bot Discord modulaire de Clan Renard
Git Ignore  : None
License     : None
```

Le projet contient déjà :

```text
.gitignore
LICENSE
```

Il ne faut donc pas demander à GitHub Desktop de les remplacer.

Vérifie que le chemin local correspond bien au dossier généré.

## 5. Vérifier les fichiers avant le premier commit

Dans l'onglet `Changes`, vérifie que les fichiers suivants ne sont
pas présents :

```text
.env
*.log
__pycache__/
generated/apercu-calendrier.png
```

Le fichier suivant doit en revanche être présent :

```text
.env.example
```

`.env.example` ne contient aucun vrai secret.

## 6. Rechercher les secrets accidentels

Avant de publier, recherche dans le projet :

```text
DISCORD_TOKEN=
DATABASE_URL=
```

Les valeurs de `.env.example` doivent rester vides.

Aucun token réel ni mot de passe ne doit apparaître dans :

- les fichiers Python ;
- les fichiers Markdown ;
- `render.yaml` ;
- les tests ;
- les captures d'écran ;
- les messages de commit.

## 7. Créer le premier commit

Dans le champ `Summary`, écris par exemple :

```text
Initialisation du bot Clan Renard
```

Clique sur :

```text
Commit to main
```

## 8. Publier sur GitHub

Clique sur :

```text
Publish repository
```

Choisis le nom :

```text
clan-renard-bot
```

Tu peux conserver le dépôt privé si le bot est réservé au serveur.

Clique ensuite sur le bouton de publication.

## 9. Vérifier le dépôt en ligne

Ouvre le dépôt dans le navigateur.

Vérifie notamment :

- que `README.md` s'affiche ;
- que le dossier `bot/` existe ;
- que `Dockerfile` existe ;
- que `render.yaml` existe ;
- que `.env` n'existe pas ;
- qu'aucun secret n'est visible.

## 10. Ajouter le logo Clan Renard

Si le logo n'était pas présent lors de la génération, place-le ici :

```text
assets/branding/clan_renard_logo.png
```

Retourne dans GitHub Desktop.

Un nouveau fichier apparaît dans `Changes`.

Crée un commit :

```text
Ajout du logo Clan Renard
```

Puis clique sur :

```text
Push origin
```

Render pourra redéployer automatiquement le bot.

## 11. Envoyer les futures modifications

Le fonctionnement normal sera :

1. modifier les fichiers sur l'ordinateur ;
2. vérifier les changements dans GitHub Desktop ;
3. écrire un résumé de commit ;
4. cliquer sur `Commit to main` ;
5. cliquer sur `Push origin` ;
6. attendre le redéploiement de Render.

## 12. Ajouter un futur module

Par exemple, crée :

```text
bot/extensions/moderation.py
```

ou :

```text
bot/extensions/tickets.py
```

Le chargeur les détectera automatiquement au prochain démarrage.

Pour un grand module, ajoute également :

```text
bot/features/moderation/
bot/features/tickets/
```

Consulte :

```text
docs/ADDING_A_MODULE.md
```

## Ne jamais publier le fichier `.env`

Si `.env` apparaît malgré tout dans GitHub Desktop :

1. ne crée pas le commit ;
2. vérifie que `.gitignore` contient `.env` ;
3. ferme et rouvre GitHub Desktop si nécessaire ;
4. retire le fichier du suivi Git.

Si un token a déjà été publié, le supprimer dans un nouveau commit
ne suffit pas : il reste dans l'historique Git.

Il faut immédiatement :

1. réinitialiser le token Discord ;
2. changer le mot de passe PostgreSQL si nécessaire ;
3. nettoyer l'historique ou recréer un dépôt propre.
