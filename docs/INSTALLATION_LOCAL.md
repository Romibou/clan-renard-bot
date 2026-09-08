# Installation locale

L'installation locale permet de tester le bot avant son déploiement
sur Render.

## 1. Installer Python

Installe Python 3.11 ou 3.12 depuis :

<https://www.python.org/downloads/>

Sous Windows, coche :

```text
Add Python to PATH
```

Vérifie l'installation :

```bash
python --version
```

ou :

```bash
py --version
```

## 2. Ouvrir un terminal dans le projet

Le terminal doit être ouvert dans le dossier contenant :

```text
README.md
requirements.txt
render.yaml
bot/
```

Vérifie avec :

### Windows

```bat
dir
```

### Linux ou macOS

```bash
ls
```

## 3. Créer l'environnement virtuel

### PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Invite de commandes Windows

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
```

### Linux ou macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Une fois activé, le terminal affiche généralement :

```text
(.venv)
```

## 4. Installer les dépendances

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

## 5. Préparer PostgreSQL

Le bot exige PostgreSQL. SQLite n'est pas utilisé.

Si PostgreSQL fonctionne localement, crée une base nommée par
exemple :

```text
clan_renard
```

Exemple d'URL :

```env
DATABASE_URL=postgresql://postgres:mot_de_passe@localhost:5432/clan_renard
```

Il est également possible d'utiliser temporairement l'URL externe
d'une base PostgreSQL Render pour les essais locaux.

Ne publie jamais une URL contenant un mot de passe.

## 6. Créer le fichier `.env`

Copie :

```text
.env.example
```

vers :

```text
.env
```

Remplis les valeurs :

```env
DISCORD_TOKEN=
DATABASE_URL=
DEFAULT_TIMEZONE=Europe/Paris
ENVIRONMENT=development
LOG_LEVEL=INFO
DEV_GUILD_ID=
OWNER_ID=
PORT=10000
```

`DEV_GUILD_ID` correspond à l'identifiant du serveur Discord de
développement.

Grâce à cette valeur, les commandes slash sont généralement
disponibles rapidement sur ce serveur.

## 7. Ajouter le logo facultatif

Place le logo ici :

```text
assets/branding/clan_renard_logo.png
```

Le bot fonctionne également sans logo.

## 8. Vérifier le projet

```bash
python scripts/check_project.py
```

Puis :

```bash
pytest
```

## 9. Générer un aperçu graphique

```bash
python scripts/preview_calendar.py
```

Ouvre ensuite :

```text
generated/apercu-calendrier.png
```

Cette commande ne se connecte pas à Discord.

## 10. Lancer le bot

```bash
python -m bot.main
```

Les logs doivent notamment contenir :

```text
Connexion PostgreSQL établie
Schéma PostgreSQL vérifié
Extension chargée : bot.extensions.advent
Système du calendrier de l'Avent initialisé
Bot connecté
```

## Arrêter le bot

Dans le terminal :

```text
Ctrl + C
```

## Problèmes fréquents

### `DISCORD_TOKEN est absent`

Le fichier `.env` manque ou la variable n'est pas remplie.

### `DATABASE_URL est absente`

Ajoute une URL PostgreSQL valide dans `.env`.

### Échec de connexion PostgreSQL

Vérifie :

- le nom d'utilisateur ;
- le mot de passe ;
- l'hôte ;
- le port ;
- le nom de la base ;
- l'accès réseau.

### Les commandes slash n'apparaissent pas

Vérifie :

- que `DEV_GUILD_ID` est correct ;
- que le bot a été invité avec le scope `applications.commands` ;
- que le bot a terminé son démarrage ;
- les logs de synchronisation des commandes.

### Le rôle n'est pas attribué

Vérifie :

- la permission `Gérer les rôles` ;
- la position du rôle du bot ;
- la position du rôle récompensé ;
- que le rôle n'est pas géré par une intégration.

Le rôle du bot doit être placé au-dessus du rôle distribué.

### L'aperçu ne trouve aucune police

Le Dockerfile installe DejaVu Sans sur Render.

Localement, tu peux ajouter :

```text
assets/advent/fonts/title.ttf
assets/advent/fonts/regular.ttf
```
