# Clan Renard Bot

Clan Renard Bot est un bot Discord communautaire et modulaire développé en Python avec `discord.py`.

Il regroupe plusieurs systèmes connectés entre eux :

- calendrier de l’Avent individuel ;
- profils graphiques personnalisables ;
- progression par niveaux ;
- XP textuelle et vocale ;
- économie permanente ;
- boutique permanente ;
- boutique saisonnière ;
- rôles de niveau ;
- multiplicateurs d’XP ;
- importation de données depuis DraftBot ;
- panneaux administratifs interactifs ;
- stockage permanent avec PostgreSQL.

Le projet est conçu pour fonctionner localement ou être hébergé sur Render avec Docker.

La liste complète des fonctionnalités et des commandes est disponible ici :

[📚 Voir toutes les fonctionnalités et commandes](./FONCTIONNALITES.md)


## Technologies utilisées

- Python 3.11 ou 3.12 ;
- `discord.py` ;
- PostgreSQL ;
- `asyncpg` ;
- Pillow ;
- Docker ;
- Render ;
- commandes slash Discord ;
- vues, boutons, menus et formulaires Discord.

---

## Architecture du projet

```text
clan-renard-bot/
├── bot/
│   ├── main.py
│   ├── core/
│   │   ├── bot.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── extension_loader.py
│   │   ├── health.py
│   │   └── logging_config.py
│   ├── extensions/
│   │   ├── advent.py
│   │   ├── advent_shop.py
│   │   ├── draftbot_import.py
│   │   ├── profile.py
│   │   ├── progression.py
│   │   └── shop.py
│   ├── features/
│   │   └── advent/
│   └── shared/
│       └── progression_card.py
├── assets/
│   ├── advent/
│   ├── branding/
│   ├── profile/
│   │   ├── badges/
│   │   ├── backgrounds/
│   │   ├── frames/
│   │   └── effects/
│   └── shared/
├── database/
├── docs/
├── generated/
├── scripts/
├── tests/
├── .env.example
├── Dockerfile
├── render.yaml
├── requirements.txt
├── requirements-dev.txt
├── README.md
└── FONCTIONNALITES.md
```

L’arborescence exacte peut évoluer lorsque de nouveaux modules sont ajoutés.

---

## Principe des extensions

Le bot utilise une architecture modulaire.

Les extensions placées dans :

```text
bot/extensions/
```

sont chargées automatiquement au démarrage.

Chaque grand système peut ainsi être développé dans son propre fichier ou dans son propre dossier sans placer tout le projet dans un unique fichier Python.

Exemple d’une extension simple :

```text
bot/extensions/moderation.py
```

Exemple d’un système plus important :

```text
bot/extensions/tickets.py

bot/features/tickets/
├── __init__.py
├── commands.py
├── repository.py
├── service.py
└── views.py
```

---

## Prérequis

### Installation locale

Il faut disposer de :

- Python 3.11 ou Python 3.12 ;
- PostgreSQL ;
- Git ou GitHub Desktop ;
- une application Discord ;
- le token du bot ;
- l’identifiant d’un serveur Discord de développement.

### Hébergement en production

Pour un déploiement sur Render, il faut disposer de :

- un compte GitHub ;
- un compte Render ;
- une base PostgreSQL Render ou compatible ;
- les variables d’environnement nécessaires ;
- une application Discord correctement configurée.

---

## Création de l’application Discord

Depuis le portail des développeurs Discord :

1. créer une nouvelle application ;
2. ouvrir la rubrique **Bot** ;
3. créer le bot ;
4. récupérer son token ;
5. ne jamais publier ce token ;
6. activer l’intent **Server Members Intent** ;
7. inviter le bot sur le serveur.

Permissions généralement nécessaires :

- voir les salons ;
- envoyer des messages ;
- intégrer des liens ;
- joindre des fichiers ;
- utiliser les commandes de l’application ;
- gérer les rôles ;
- lire l’historique des messages.

La permission **Gérer les rôles** est indispensable pour :

- distribuer les récompenses de niveau ;
- distribuer les récompenses du calendrier ;
- vendre des rôles dans les boutiques ;
- restaurer les rôles achetés.

Le rôle principal du bot doit être placé au-dessus des rôles qu’il doit distribuer.

---

## Installation locale

### 1. Cloner le dépôt

```bash
git clone https://github.com/Romibou/clan-renard-bot.git
cd clan-renard-bot
```

### 2. Créer un environnement virtuel

#### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloque l’activation :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

#### Windows Invite de commandes

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
```

#### Linux ou macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Installer les dépendances

Pour utiliser le bot :

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Pour le développement et les tests :

```bash
pip install -r requirements-dev.txt
```

### 4. Créer le fichier `.env`

#### Windows

```bat
copy .env.example .env
```

#### Linux ou macOS

```bash
cp .env.example .env
```

### 5. Configurer les variables

Exemple :

```env
DISCORD_TOKEN=ton_token_discord
DATABASE_URL=postgresql://utilisateur:mot_de_passe@serveur:5432/base
DEFAULT_TIMEZONE=Europe/Paris
ENVIRONMENT=development
LOG_LEVEL=INFO
DEV_GUILD_ID=identifiant_du_serveur_de_test
```

Certaines versions du projet peuvent contenir des variables supplémentaires dans `.env.example`.

Il faut utiliser `.env.example` comme référence principale.

### 6. Démarrer le bot

```bash
python -m bot.main
```

---

## Base de données PostgreSQL

Le bot utilise PostgreSQL pour conserver de manière permanente :

- la configuration des serveurs ;
- les campagnes du calendrier ;
- les ouvertures de cases ;
- les récompenses ;
- les points saisonniers ;
- les achats saisonniers ;
- les profils ;
- les cosmétiques ;
- les inventaires ;
- les équipements ;
- l’XP ;
- les niveaux ;
- l’argent permanent ;
- les transactions ;
- les récompenses vocales ;
- les multiplicateurs d’XP ;
- les rôles de niveau ;
- les articles de la boutique permanente ;
- les achats réalisés ;
- les journaux d’administration.

Les tables nécessaires sont créées ou vérifiées automatiquement au démarrage des extensions.

Des migrations utilisant notamment :

```sql
ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...
```

peuvent être exécutées au démarrage afin de rendre les anciennes bases compatibles avec les nouvelles fonctionnalités.

---

## Ressources graphiques

### Calendrier de l’Avent

Les ressources du calendrier sont placées dans :

```text
assets/advent/
```

### Identité visuelle

Le logo du bot peut être placé dans :

```text
assets/branding/clan_renard_logo.png
```

Format conseillé :

- PNG transparent ;
- image carrée ;
- au moins 512 × 512 pixels ;
- peu de marge autour du renard.

### Profils

Les ressources des cosmétiques de profil sont placées dans :

```text
assets/profile/
├── badges/
├── backgrounds/
├── frames/
└── effects/
```

Exemples :

```text
assets/profile/badges/flocon.png
assets/profile/backgrounds/noel.png
assets/profile/frames/givre.png
assets/profile/effects/neige.png
```

Dans `/profil-admin`, les chemins sont relatifs à `assets/profile/`.

Il faut donc écrire :

```text
badges/flocon.png
```

et non :

```text
assets/profile/badges/flocon.png
```

### Titres de profil

Les titres sont du texte et ne nécessitent aucune image.

Il n’est donc pas nécessaire de créer :

```text
assets/profile/titles/
```

Pour un cosmétique de type `title` :

- laisser le chemin de l’image vide ;
- placer le texte du titre dans le champ **Valeur facultative**.

---

## Génération des images

Les cartes graphiques sont générées avec Pillow.

Selon le système concerné, la procédure générale est la suivante :

1. PostgreSQL retourne les données du membre ;
2. le bot récupère son pseudo et son avatar ;
3. Pillow compose la carte ;
4. l’image est produite en mémoire ;
5. Discord reçoit le fichier PNG ;
6. le tampon mémoire est ensuite libéré.

Cela concerne notamment :

- les calendriers de l’Avent ;
- les cartes de profil ;
- les cartes de progression.

Il n’est pas nécessaire de conserver définitivement une image différente pour chaque membre.

---

## Prévisualisation du calendrier

La prévisualisation graphique du calendrier peut être générée sans Discord.

```bash
python scripts/preview_calendar.py
```

Résultat attendu :

```text
generated/apercu-calendrier.png
```

Avec une année et un pseudo personnalisés :

```bash
python scripts/preview_calendar.py --year 2026 --name "Mon pseudo"
```

---

## Vérification du projet

Pour lancer les tests :

```bash
pytest
```

Pour vérifier les fichiers Python du projet :

```bash
python scripts/check_project.py
```

Il est conseillé d’effectuer ces vérifications avant chaque déploiement.

---

## Déploiement sur Render

Le projet contient notamment :

```text
Dockerfile
render.yaml
```

Le service Render doit recevoir les variables d’environnement nécessaires, notamment :

```env
DISCORD_TOKEN=
DATABASE_URL=
DEFAULT_TIMEZONE=Europe/Paris
ENVIRONMENT=production
LOG_LEVEL=INFO
```

Les secrets doivent être enregistrés directement dans Render.

Il ne faut jamais les écrire dans :

- le dépôt GitHub ;
- `render.yaml` ;
- un fichier public ;
- une capture d’écran ;
- la documentation.

Le bot possède un contrôle de santé HTTP permettant à Render de vérifier que le service fonctionne.

---

## Synchronisation des commandes Discord

En environnement de développement, `DEV_GUILD_ID` permet généralement de synchroniser rapidement les commandes sur un serveur de test.

La synchronisation globale peut prendre plus de temps à apparaître sur tous les serveurs.

Après une modification des commandes :

1. redémarrer complètement le bot ;
2. vérifier les logs ;
3. attendre la synchronisation Discord ;
4. redémarrer Discord si l’interface affiche encore une ancienne commande.

---

## Documentation

La documentation principale est répartie entre :

```text
README.md
FONCTIONNALITES.md
```

Des documents supplémentaires peuvent être présents dans :

```text
docs/
```

Par exemple :

```text
docs/INSTALLATION_LOCAL.md
docs/INSTALLATION_DISCORD.md
docs/INSTALLATION_GITHUB.md
docs/INSTALLATION_RENDER.md
docs/COMMANDS.md
docs/COMMANDS_ADMIN.md
docs/ASSETS.md
docs/ADDING_A_MODULE.md
```

---

## Sécurité

Ne jamais publier :

- le token Discord ;
- le fichier `.env` ;
- le mot de passe PostgreSQL ;
- une URL PostgreSQL contenant un mot de passe ;
- des codes cadeaux privés ;
- des exports contenant des informations sensibles ;
- les journaux complets d’un serveur de production.

Le fichier `.env` réel doit être exclu par `.gitignore`.

En cas de fuite du token Discord :

1. ouvrir le portail des développeurs Discord ;
2. régénérer immédiatement le token ;
3. remplacer la variable `DISCORD_TOKEN` ;
4. redémarrer le bot.

---

## Ajouter une fonctionnalité

Les nouveaux systèmes doivent idéalement être ajoutés sous forme d’extensions.

Exemple :

```text
bot/extensions/nouvelle_fonctionnalite.py
```

Pour les fonctionnalités importantes :

```text
bot/features/nouvelle_fonctionnalite/
```

Une extension ne doit pas :

- contenir de token directement dans le code ;
- ouvrir sa propre connexion PostgreSQL si le gestionnaire partagé existe ;
- bloquer la boucle asynchrone ;
- enregistrer inutilement des milliers d’images ;
- dupliquer les outils déjà présents dans `bot/core/` ou `bot/shared/`.
