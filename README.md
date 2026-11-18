# Clan Renard Bot

[![Vérifications](https://github.com/Romibou/clan-renard-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Romibou/clan-renard-bot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![discord.py](https://img.shields.io/badge/discord.py-2.7-5865F2)
![Licence](https://img.shields.io/badge/licence-MIT-green)

Clan Renard Bot est le bot Discord tout-en-un du serveur **Clan Renard**. Il réunit dans un seul service la progression des membres, une économie complète, des profils graphiques personnalisables, l’animation de la communauté, des mini-jeux et la modération, le tout administrable depuis Discord grâce à des panneaux interactifs.

Développé en Python avec `discord.py`, il s’appuie sur PostgreSQL pour la persistance des données et génère ses visuels à la volée avec Pillow.

> 📚 La liste détaillée des commandes et du fonctionnement de chaque système se trouve dans **[FONCTIONNALITES.md](./FONCTIONNALITES.md)**.

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Stack technique](#stack-technique)
- [Architecture](#architecture)
- [Principes de conception](#principes-de-conception)
- [Installation locale](#installation-locale)
- [Configuration](#configuration)
- [Application Discord](#application-discord)
- [Déploiement](#déploiement)
- [Qualité et tests](#qualité-et-tests)
- [Sauvegardes](#sauvegardes)
- [Ajouter un module](#ajouter-un-module)
- [Sécurité](#sécurité)
- [Licence](#licence)

---

## Fonctionnalités

### Progression et engagement
- **XP textuelle et vocale**, niveaux, rôles de niveau attribués automatiquement et multiplicateurs par rôle.
- **Bonus d’XP temporaires** programmables, annoncés au début et à la fin.
- **Classements** (XP, argent, série, semaine, mois), **statistiques** personnelles et **bilan annuel** illustré.

### Économie
- Portefeuille de pièces alimenté par l’activité, **récompenses quotidienne, hebdomadaire et mensuelle** avec bonus de série.
- **Missions** journalières et hebdomadaires, **dons** entre membres, **drops** et **giveaways** lancés par l’équipe.
- **Boutique permanente** de rôles et de cosmétiques, avec essayage du cosmétique sur sa propre carte avant l’achat.

### Profils et cosmétiques
- **Carte de profil graphique** : fond, cadre, badge, effet et titre, avec bio et couleur personnalisées.
- **Collections** de cosmétiques par thème et suivi de leur complétion.
- **Studio de création** depuis Discord : import d’images, création d’une collection complète en une fois, aperçu et modification, sans toucher aux fichiers du projet.

### Vie de la communauté
- **Bienvenue et départs** avec carte graphique personnalisable, modèles réutilisables et rôles attribués à l’arrivée.
- **Anniversaires** : enregistrement par les membres, souhaits automatiques, rôle du jour et cadeau.
- **Studio d’annonces** : rédaction avec aperçu, modèles, programmation, modification après publication, import et export Discohook.
- **Rôles à la réaction** et **rappels** personnels.

### Mini-jeux
- **Morpion, Puissance 4, pierre-feuille-ciseaux et pendu**, contre un membre ou contre l’IA, avec mises sécurisées et classement.
- **Bingo** animé par l’équipe dans un salon dédié.

### Modération
- Avertissements, mises en sourdine, expulsions, bannissements temporaires ou définitifs et amendes.
- **Échelle de sanctions automatique**, casier, notes internes et **contestations** traitées par l’équipe.
- Règles **AutoMod** natives de Discord et protection contre le spam.

### Événements saisonniers
- **Calendrier de l’Avent** individuel illustré : 24 cases, récompenses variées, rattrapage, points saisonniers, boutique dédiée et annonces quotidiennes personnalisables.

### Administration
- Chaque système se configure depuis Discord grâce à un **panneau dédié** (`/progression-admin`, `/boutique-admin`, `/profil-admin`, `/avent-admin`, `/bienvenue-admin`…), sans redémarrer le bot ni modifier le code.
- Journal de modération, aperçus avant publication et confirmations pour les actions sensibles.

---

## Stack technique

| Domaine | Technologie |
|---|---|
| Langage | Python 3.12 |
| Discord | `discord.py` 2.7 (commandes slash, composants, fenêtres, Components V2) |
| Base de données | PostgreSQL (Supabase), via `asyncpg` |
| Visuels | Pillow |
| Serveur HTTP | `aiohttp` (contrôle de santé) |
| Conteneur | Docker |
| Hébergement | Render |
| Intégration continue | GitHub Actions (Ruff, compilation, pytest) |

---

## Architecture

```text
clan-renard-bot/
├── bot/
│   ├── main.py                 # Point d'entrée
│   ├── core/                   # Socle commun
│   │   ├── bot.py              # Client Discord, intents, synchronisation des commandes
│   │   ├── config.py           # Lecture et validation des variables d'environnement
│   │   ├── database.py         # Pool PostgreSQL partagé et transactions
│   │   ├── extension_loader.py # Chargement automatique des extensions
│   │   ├── health.py           # Point de contrôle HTTP pour l'hébergeur
│   │   └── logging_config.py
│   ├── extensions/             # Un fichier par système, chargé au démarrage
│   │   ├── progression.py      # XP, niveaux, rôles, multiplicateurs
│   │   ├── xp_boost.py         # Bonus d'XP temporaires
│   │   ├── daily.py            # Récompense quotidienne et rappels
│   │   ├── periodic_rewards.py # Récompenses hebdomadaire et mensuelle
│   │   ├── missions.py         # Missions
│   │   ├── shop.py             # Boutique permanente
│   │   ├── donner.py · drop.py · giveaway.py
│   │   ├── profile.py          # Profils et cosmétiques
│   │   ├── collection.py       # Collections
│   │   ├── zz_rankings.py · statistics.py · bilan.py
│   │   ├── bienvenue.py        # Bienvenue, départs, rôles d'arrivée
│   │   ├── anniversaire.py     # Anniversaires
│   │   ├── annonces.py         # Studio d'annonces
│   │   ├── jeux.py · bingo.py  # Mini-jeux
│   │   ├── moderation.py       # Modération
│   │   ├── advent.py · advent_shop.py
│   │   ├── reaction_roles.py · rappel.py · aide.py · ping.py
│   │   └── draftbot_import.py  # Import d'une progression DraftBot
│   ├── features/               # Systèmes volumineux découpés en modules
│   │   ├── advent/             # Calendrier : service, dépôts, rendu, panneaux, tâches
│   │   ├── announcements/      # Annonces : modèle, rendu, stockage, studio
│   │   ├── minigames/          # Moteurs de jeux et IA
│   │   ├── moderation/         # Sanctions, AutoMod, contestations, panneau
│   │   └── cosmetics_studio.py # Création de cosmétiques depuis Discord
│   └── shared/                 # Outils réutilisés par plusieurs systèmes
│       ├── economy.py          # Crédits d'XP et de pièces, rôles de niveau
│       ├── panels.py           # Comportement commun des panneaux d'administration
│       ├── members.py · pagination.py · dates.py · embeds.py · text.py · checks.py
│       ├── cosmetic_catalogue.py
│       └── *_card.py           # Rendus graphiques (progression, classement, statistiques, bilan, bienvenue)
├── assets/                     # Polices, identité visuelle, ressources du calendrier et des cosmétiques
├── database/schema.sql         # Schéma de base appliqué au démarrage
├── scripts/                    # Sauvegarde, restauration, migration, vérifications, aperçus
├── tests/                      # Tests automatisés (pytest)
├── docs/                       # Guides d'installation et documentation complémentaire
├── .github/workflows/ci.yml    # Intégration continue
├── Dockerfile · render.yaml
├── requirements.txt · requirements-dev.txt · pyproject.toml
├── README.md
└── FONCTIONNALITES.md
```

---

## Principes de conception

**Extensions indépendantes.** Chaque fichier de `bot/extensions/` est découvert et chargé automatiquement au démarrage (les fichiers commençant par `_` sont ignorés). Un système défaillant n’empêche pas les autres de démarrer.

**Logique séparée de l’interface.** Les systèmes volumineux placent leurs règles dans des modules sans dépendance à Discord (`model.py`, `engines.py`, `core.py`…), ce qui permet de les tester de façon isolée.

**Une seule source de vérité.** Toutes les données sont stockées dans PostgreSQL. Les tables sont créées ou mises à niveau au démarrage (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`) : aucune migration manuelle n’est nécessaire. Les opérations sensibles (pièces, mises, achats) sont transactionnelles et protégées par des verrous pour éviter les doubles paiements.

**Visuels générés à la demande.** Les cartes sont composées en mémoire avec Pillow, envoyées à Discord puis libérées : aucune image n’est conservée par membre. Les calculs coûteux et invariables, comme les dégradés de fond, sont mis en cache.

**Ressources persistantes.** Les images de cosmétiques importées depuis Discord sont enregistrées en base de données et réécrites sur le disque à chaque démarrage, l’hébergeur effaçant les fichiers lors des redéploiements.

**Administration sans code.** Les réglages courants passent par des panneaux Discord avec aperçu et confirmation, accessibles uniquement aux membres disposant des permissions requises.

---

## Installation locale

**Prérequis** : Python 3.12, une base PostgreSQL (Supabase ou locale) et une application Discord (voir [Application Discord](#application-discord)).

```bash
git clone https://github.com/Romibou/clan-renard-bot.git
cd clan-renard-bot
```

Créer et activer un environnement virtuel :

```powershell
# Windows (PowerShell)
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

Installer les dépendances, puis créer le fichier de configuration à partir du modèle :

```bash
pip install -r requirements-dev.txt
cp .env.example .env    # Windows : copy .env.example .env
```

Renseigner `.env` (voir [Configuration](#configuration)), puis démarrer le bot :

```bash
python -m bot.main
```

---

## Configuration

La configuration est lue depuis les variables d’environnement, ou depuis le fichier `.env` en local.

| Variable | Obligatoire | Description |
|---|---|---|
| `DISCORD_TOKEN` | Oui | Jeton du bot (Discord Developer Portal) |
| `DATABASE_URL` | Oui | Chaîne de connexion PostgreSQL |
| `DEFAULT_TIMEZONE` | Non | Fuseau horaire par défaut (`Europe/Paris`) |
| `ENVIRONMENT` | Non | `development` ou `production` |
| `LOG_LEVEL` | Non | `DEBUG`, `INFO`, `WARNING` ou `ERROR` |
| `DEV_GUILD_ID` | Non | Serveur de test : les commandes y sont synchronisées immédiatement |
| `OWNER_ID` | Non | Identifiant Discord du propriétaire du bot |
| `PORT` | Non | Port du contrôle de santé (fourni automatiquement par Render) |

`.env.example` sert de modèle et ne doit contenir **aucune valeur réelle**.

---

## Application Discord

Depuis le [Discord Developer Portal](https://discord.com/developers/applications) :

1. Créer l’application, puis le bot dans l’onglet **Bot**, et conserver son jeton en lieu sûr.
2. Activer les intents privilégiés **Server Members Intent** et **Message Content Intent**. Sans ce dernier, le bot démarre quand même et le bingo passe automatiquement en mode bouton.
3. Inviter le bot avec la portée `applications.commands`.

**Permissions nécessaires sur le serveur** : voir les salons, envoyer des messages (y compris dans les fils), intégrer des liens, joindre des fichiers, voir les anciens messages, ajouter des réactions, utiliser des émojis externes, mentionner @everyone, gérer les rôles, gérer les messages, gérer les salons, gérer le serveur (règles AutoMod), exclure temporairement, expulser et bannir des membres.

Le rôle du bot doit être placé **au-dessus** des rôles qu’il attribue (niveaux, boutique, arrivée, anniversaire) et des membres qu’il peut sanctionner.

---

## Déploiement

Le bot est déployé sur **Render** à partir du `Dockerfile`, avec une base **Supabase**.

- Chaque envoi sur la branche `main` déclenche un nouveau déploiement automatique.
- Les variables d’environnement, et notamment les secrets, sont définies dans le tableau de bord Render, jamais dans le dépôt.
- Le bot expose un point de contrôle HTTP (`/health`) utilisé par Render, et qu’un service de surveillance externe (UptimeRobot) interroge régulièrement pour maintenir l’instance active.
- L’image Docker installe les polices utilisées par les visuels (DejaVu, Roboto).

**Synchronisation des commandes.** Avec `DEV_GUILD_ID`, les commandes apparaissent presque immédiatement sur le serveur de test. La synchronisation globale peut prendre quelques minutes ; si une commande ancienne reste affichée, redémarrer le client Discord.

Les guides détaillés se trouvent dans [`docs/`](./docs) (installation locale, Discord, GitHub, Render et cycle de déploiement).

---

## Qualité et tests

```bash
pytest -q                                     # Tests automatisés
ruff check bot scripts tests --select F,E9    # Erreurs réelles (noms inconnus, imports, syntaxe)
python scripts/check_project.py               # Vérification de la structure du projet
```

Les mêmes vérifications s’exécutent sur GitHub Actions à chaque envoi et à chaque pull request. Les tests couvrent notamment les règles métier (économie, mises, dates, récompenses), les rendus graphiques et le respect des limites de Discord par les composants.

---

## Sauvegardes

```bash
python scripts/sauvegarder_base.py    # Archive ZIP de toutes les tables (CSV + métadonnées)
python scripts/restaurer_base.py      # Restauration d'une archive dans une base
```

Les archives sont créées dans `sauvegardes/`, dossier exclu du dépôt car il contient les identifiants Discord des membres.

---

## Ajouter un module

Un système simple tient dans un seul fichier :

```text
bot/extensions/nouveau_module.py      # contient une fonction async setup(bot)
```

Un système plus important sépare sa logique de son interface :

```text
bot/extensions/nouveau_module.py      # point d'entrée : commandes et chargement
bot/features/nouveau_module/
├── model.py         # règles, sans dépendance à Discord
├── repository.py    # accès à PostgreSQL
└── views.py         # boutons, menus et fenêtres
```

Bonnes pratiques :

- utiliser le pool partagé (`bot.database`) plutôt qu’une nouvelle connexion ;
- passer par `bot/shared/economy.py` pour tout gain ou retrait d’XP et de pièces ;
- ne jamais bloquer la boucle asynchrone (déléguer le rendu d’images avec `asyncio.to_thread`) ;
- utiliser `bot/shared/panels.py` pour les panneaux d’administration ;
- ajouter des tests dans `tests/` et documenter le système dans `FONCTIONNALITES.md`.

---

## Sécurité

- Ne jamais publier le jeton Discord, le fichier `.env`, ni une chaîne de connexion contenant un mot de passe.
- `.env` est exclu par `.gitignore` ; `.env.example` ne contient que des valeurs d’exemple.
- En cas de fuite d’un secret : le régénérer immédiatement (jeton dans le Developer Portal, mot de passe dans Supabase), mettre à jour la variable sur Render, puis redéployer.

---

## Licence

Distribué sous licence MIT. Voir [LICENSE](./LICENSE).
