# Clan Renard Bot

Bot Discord modulaire en Python, conçu pour être hébergé sur Render.

La première fonctionnalité entièrement intégrée est un calendrier
de l'Avent individuel, avec une identité visuelle violet sombre,
rose poudré et renard.

## Fonctionnalités de la version actuelle

- architecture Python modulaire ;
- chargement automatique des extensions ;
- commandes slash Discord ;
- calendrier individuel pour chaque membre ;
- image générée dynamiquement avec Pillow ;
- 24 cases réparties dans une grille de 6 × 4 ;
- cadeaux ouverts, disponibles, verrouillés et manqués ;
- case spéciale pour le 24 décembre ;
- fuseau horaire configurable ;
- heure quotidienne configurable ;
- rattrapage activable ou désactivable ;
- récompenses textuelles ;
- récompenses en points ;
- récompenses sous forme de rôles Discord ;
- récompenses aléatoires pondérées ;
- historique personnel ;
- classement ;
- panneau public ;
- boutons persistants après redémarrage ;
- annonces quotidiennes automatiques ;
- protection PostgreSQL contre les doubles ouvertures ;
- commandes administratives ;
- journal d'audit ;
- contrôle de santé HTTP pour Render ;
- Dockerfile ;
- configuration Blueprint Render ;
- tests automatisés ;
- chemins prêts pour les futurs modules.

## Architecture

```text
clan-renard-bot/
├── bot/
│   ├── main.py
│   ├── core/
│   ├── extensions/
│   ├── features/
│   │   └── advent/
│   └── shared/
├── assets/
│   ├── advent/
│   ├── branding/
│   └── shared/
├── database/
├── docs/
├── generated/
├── scripts/
├── tests/
├── .env.example
├── Dockerfile
├── render.yaml
└── requirements.txt
```

## Principe des extensions

Le fichier principal démarre un seul bot Discord.

Les fonctionnalités présentes dans :

```text
bot/extensions/
```

sont détectées automatiquement.

Pour ajouter plus tard une fonctionnalité de modération, il sera
possible de créer :

```text
bot/extensions/moderation.py
```

Pour un système plus important :

```text
bot/extensions/tickets.py

bot/features/tickets/
├── __init__.py
├── commands.py
├── repository.py
├── service.py
└── views.py
```

Il ne faut pas placer tout le bot dans un seul fichier Python.

## Génération des images

Les calendriers ne sont pas enregistrés définitivement.

À chaque demande :

1. PostgreSQL retourne les cases ouvertes du membre ;
2. Pillow dessine le fond et les 24 cadeaux ;
3. le pseudo et l'avatar sont ajoutés ;
4. le PNG est créé en mémoire ;
5. Discord reçoit le fichier ;
6. le tampon mémoire est ensuite libéré.

Il n'est donc pas nécessaire de produire des milliers d'images.

## Prérequis

Pour une installation locale :

- Python 3.11 ou 3.12 ;
- PostgreSQL ;
- une application Discord ;
- le token du bot ;
- Git, ou GitHub Desktop.

Pour la production :

- un compte GitHub ;
- un compte Render ;
- une base PostgreSQL Render ou compatible.

## Installation locale rapide

Crée un environnement virtuel :

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell refuse l'activation :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Windows Invite de commandes

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
```

### Linux ou macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Installe les dépendances :

```bash
pip install --upgrade pip
pip install -r requirements-dev.txt
```

Copie le fichier d'environnement :

### Windows

```bat
copy .env.example .env
```

### Linux ou macOS

```bash
cp .env.example .env
```

Remplis au minimum :

```env
DISCORD_TOKEN=ton_token
DATABASE_URL=postgresql://utilisateur:mot_de_passe@serveur:5432/base
DEFAULT_TIMEZONE=Europe/Paris
ENVIRONMENT=development
LOG_LEVEL=INFO
DEV_GUILD_ID=identifiant_du_serveur_de_test
```

Lance le bot :

```bash
python -m bot.main
```

## Prévisualisation du calendrier

La prévisualisation graphique ne nécessite ni Discord ni PostgreSQL :

```bash
python scripts/preview_calendar.py
```

Résultat :

```text
generated/apercu-calendrier.png
```

Avec une année et un pseudo personnalisés :

```bash
python scripts/preview_calendar.py --year 2026 --name "Mon pseudo"
```

## Logo Clan Renard

Le logo facultatif doit être placé ici :

```text
assets/branding/clan_renard_logo.png
```

Format conseillé :

- PNG transparent ;
- image carrée ;
- au moins 512 × 512 pixels ;
- peu de marge autour du renard.

Sans ce fichier, le calendrier dessine automatiquement un emblème
de renard stylisé.

## Premier démarrage sur Discord

Une fois le bot connecté :

```text
/avent-admin-initialiser
```

Configure ensuite :

```text
/avent-admin-canal
/avent-admin-rattrapage
/avent-admin-annonces
```

Ajoute les récompenses :

```text
/avent-admin-recompense-message
/avent-admin-recompense-points
/avent-admin-recompense-role
/avent-admin-recompense-aleatoire
```

Vérifie le rendu :

```text
/avent-admin-apercu
```

Puis publie le panneau :

```text
/avent-admin-publier
```

## Tests

Exécute les tests avec :

```bash
pytest
```

Vérifie aussi tous les fichiers Python :

```bash
python scripts/check_project.py
```

## Documentation

Consulte :

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

## Sécurité

Ne publie jamais :

- le token Discord ;
- le fichier `.env` ;
- le mot de passe PostgreSQL ;
- une URL de base contenant un mot de passe ;
- des codes cadeaux privés.

Le véritable fichier `.env` est exclu par `.gitignore`.

Sur Render, les secrets doivent être enregistrés dans les variables
d'environnement du service.
