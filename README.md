# 🦊 Clan Renard Bot

Bot Discord communautaire modulaire développé en Python avec
[discord.py](https://discordpy.readthedocs.io/), PostgreSQL et Pillow.

Le projet regroupe plusieurs systèmes connectés :

- calendrier de l’Avent ;
- profils personnalisables ;
- progression par niveaux ;
- XP textuelle et vocale ;
- économie permanente ;
- boutique permanente ;
- boutique saisonnière de l’Avent ;
- rôles automatiques de niveau ;
- multiplicateurs d’XP ;
- import de progression depuis DraftBot ;
- panneaux administratifs interactifs ;
- hébergement Docker et Render.

Les données importantes sont enregistrées dans PostgreSQL et les images
sont générées dynamiquement en mémoire.

---

# Fonctionnalités principales

## 🎄 Calendrier de l’Avent

Chaque membre possède son propre calendrier de l’Avent.

Le système comprend :

- un calendrier individuel de 24 cases ;
- une grille graphique de 6 × 4 ;
- une image générée avec Pillow ;
- l’avatar et le pseudo du membre ;
- des cases ouvertes, disponibles, verrouillées ou manquées ;
- une apparence spéciale pour le 24 décembre ;
- une date et une heure d’ouverture configurables ;
- un fuseau horaire configurable ;
- un système de rattrapage activable ou désactivable ;
- une protection contre les doubles ouvertures ;
- un historique personnel ;
- un classement des points ;
- des annonces quotidiennes automatiques ;
- un panneau interactif utilisant des boutons ;
- des composants persistants après redémarrage du bot ;
- une boutique saisonnière utilisant les points de l’Avent.

### Récompenses disponibles

Une case peut contenir :

- un message ;
- des points saisonniers ;
- un rôle Discord ;
- une récompense aléatoire pondérée.

Les récompenses aléatoires peuvent sélectionner plusieurs types de
cadeaux selon les probabilités configurées.

### Points de l’Avent

Les points du calendrier sont une monnaie **saisonnière**.

Ils sont séparés des pièces permanentes du système de progression.

Ils peuvent servir à :

- participer au classement de l’Avent ;
- acheter des articles dans la boutique saisonnière ;
- obtenir des rôles ;
- obtenir des éléments cosmétiques de profil.

Les achats cosmétiques obtenus avec les points de l’Avent restent
enregistrés dans l’inventaire permanent du membre.

### Panneau membre

La commande :

```text
/avent
```

ouvre le panneau personnel du calendrier.

Selon la configuration actuelle, le panneau peut notamment proposer :

- l’ouverture de la case du jour ;
- l’actualisation du calendrier ;
- la consultation du profil de l’Avent ;
- l’historique des récompenses ;
- le classement ;
- la boutique saisonnière ;
- l’aide.

### Panneau administratif

La commande :

```text
/avent-admin
```

ouvre le panneau administratif complet.

Il permet notamment de :

- initialiser une saison ;
- modifier l’année ;
- choisir le fuseau horaire ;
- choisir l’heure quotidienne ;
- activer ou désactiver le rattrapage ;
- configurer les annonces ;
- choisir le salon public ;
- gérer les récompenses ;
- gérer la boutique saisonnière ;
- publier ou actualiser le panneau public ;
- afficher un aperçu du calendrier ;
- consulter les informations de la saison.

---

# 👤 Profils personnalisables

Le bot possède un système de profil indépendant du calendrier de
l’Avent.

La commande :

```text
/profil
```

génère une carte de profil avec Pillow et l’envoie directement comme
image Discord.

La carte peut contenir :

- l’avatar du membre ;
- son pseudo ;
- sa biographie ;
- une couleur personnalisée ;
- un titre équipé ;
- un badge équipé ;
- un arrière-plan ;
- un cadre ;
- un effet visuel ;
- les éléments cosmétiques débloqués.

## Personnalisation

Les membres peuvent personnaliser leur profil grâce aux éléments qu’ils
possèdent dans leur inventaire.

Les principales catégories sont :

- titres ;
- badges ;
- arrière-plans ;
- cadres ;
- effets ;
- autres éléments cosmétiques compatibles.

Un élément peut être équipé ou retiré depuis les menus interactifs du
profil.

## Inventaire permanent

Les cosmétiques obtenus dans :

- la boutique permanente ;
- la boutique de l’Avent ;
- une distribution administrative ;

sont enregistrés durablement dans PostgreSQL.

Ils ne sont pas perdus à la fin d’une saison de l’Avent.

## Administration des profils

La commande :

```text
/profil-admin
```

permet aux administrateurs de gérer les cosmétiques.

Selon les options installées, elle permet notamment de :

- créer un cosmétique ;
- choisir son type ;
- définir son nom et sa description ;
- associer une ressource graphique ;
- distribuer un cosmétique à un membre ;
- retirer un cosmétique ;
- supprimer ou désactiver un cosmétique ;
- consulter les éléments existants.

---

# 📈 Progression, niveaux et économie

Le bot possède un système permanent de progression.

Les membres peuvent gagner :

- de l’XP ;
- des niveaux ;
- des pièces permanentes ;
- des rôles de niveau ;
- des multiplicateurs grâce à leurs rôles.

La progression est propre à chaque serveur.

## XP par message

Lorsqu’un membre envoie un message éligible, il peut recevoir :

- une quantité aléatoire d’XP ;
- une quantité aléatoire de pièces.

Les paramètres suivants sont configurables :

- XP minimum par message ;
- XP maximum par message ;
- pièces minimum par message ;
- pièces maximum par message ;
- délai entre deux récompenses ;
- activation ou désactivation du système ;
- activation ou désactivation des notifications de niveau.

Les bots et les messages de webhooks sont ignorés.

Un verrou PostgreSQL empêche plusieurs récompenses concurrentes de
modifier incorrectement la progression d’un membre.

## Courbe de niveaux

Le système utilise une courbe progressive compatible avec la logique
d’import prévue pour DraftBot.

L’XP totale nécessaire pour atteindre un niveau est calculée avec une
courbe croissante.

Plus le niveau est élevé, plus la quantité d’XP nécessaire pour atteindre
le niveau suivant augmente.

## XP vocale

Les membres peuvent également gagner de l’XP en restant dans un salon
vocal.

Le fonctionnement actuel est le suivant :

- l’XP vocale est attribuée environ une fois par minute ;
- la valeur d’XP par minute est configurable ;
- le vocal ne donne pas de pièces ;
- au moins deux membres humains actifs doivent être présents ;
- les bots ne comptent pas ;
- les membres dans le salon AFK ne comptent pas ;
- les membres rendus muets ou sourds ne sont pas récompensés ;
- les membres qui se rendent eux-mêmes muets ou sourds ne sont pas
  récompensés ;
- le minuteur est réinitialisé lors d’un changement d’état vocal ;
- les multiplicateurs d’XP s’appliquent aussi à l’XP vocale ;
- les montées de niveau peuvent déclencher une notification ;
- les rôles de niveau peuvent être attribués grâce à l’XP vocale.

Une valeur de `0 XP par minute` désactive les récompenses vocales.

## Multiplicateurs d’XP

Un administrateur peut associer un multiplicateur d’XP à un rôle.

Exemples :

```text
VIP       → x1.5 XP
Booster   → x2 XP
Premium   → x3 XP
```

Les multiplicateurs s’appliquent :

- à l’XP gagnée par message ;
- à l’XP gagnée en vocal.

Si un membre possède plusieurs rôles avec un multiplicateur, seul le
multiplicateur le plus élevé est utilisé.

Les multiplicateurs ne sont donc pas additionnés et ne sont pas
multipliés entre eux.

## Rôles de niveau

Des rôles Discord peuvent être associés à certains niveaux.

Exemple :

```text
Niveau 10  → rôle Bronze
Niveau 30  → rôle Argent
Niveau 50  → rôle Or
```

Le membre conserve uniquement le rôle correspondant au palier le plus
élevé qu’il a atteint.

Par exemple, lorsqu’un membre passe du niveau 30 au niveau 50 :

1. le rôle du niveau 50 lui est attribué ;
2. le rôle du niveau 30 lui est retiré ;
3. les autres anciens rôles de niveau sont également retirés.

Cela évite qu’un membre accumule tous les rôles de progression.

Le bot doit posséder la permission **Gérer les rôles** et son rôle
principal doit être placé au-dessus des rôles qu’il doit attribuer ou
retirer.

## Pièces permanentes

Les pièces du système de progression sont une monnaie permanente.

Elles sont séparées des points saisonniers de l’Avent.

Le système enregistre notamment :

- le portefeuille actuel ;
- le total de pièces gagnées au cours du temps ;
- les récompenses de messages ;
- les ajustements administratifs ;
- les transactions importantes.

## Carte de progression

La commande :

```text
/progression
```

affiche une carte graphique contenant notamment :

- l’avatar ;
- le pseudo ;
- le niveau ;
- le rang ;
- l’XP totale ;
- la progression vers le prochain niveau ;
- le portefeuille ;
- le total historique de pièces gagnées.

La carte est générée dynamiquement avec Pillow.

Il est également possible de consulter la progression d’un autre membre
avec l’option prévue dans la commande.

## Classements

Le panneau de progression contient deux classements :

- classement XP ;
- classement argent.

Les classements affichent les dix premiers membres du serveur.

## Administration de la progression

La commande :

```text
/progression-admin
```

ouvre le panneau administratif.

Il permet notamment de :

- activer ou désactiver le système ;
- configurer le délai entre deux récompenses ;
- configurer l’XP minimum et maximum ;
- configurer les pièces minimum et maximum ;
- configurer l’XP vocale par minute ;
- activer ou désactiver les notifications ;
- modifier l’XP d’un membre ;
- modifier les pièces d’un membre ;
- réinitialiser entièrement un membre ;
- configurer les multiplicateurs d’XP ;
- configurer les rôles de niveau ;
- consulter toutes les règles de progression.

Les modifications administratives d’argent sont enregistrées dans
l’historique des transactions.

---

# 🛍️ Boutique permanente

Le bot possède une boutique permanente utilisant les pièces du système de
progression.

La commande :

```text
/boutique
```

permet aux membres de consulter les articles disponibles et de les
acheter.

Les articles peuvent notamment être :

- des rôles Discord ;
- des titres ;
- des badges ;
- des arrière-plans ;
- des cadres ;
- des effets ;
- d’autres cosmétiques de profil.

## Conditions d’achat

Un article peut avoir :

- un prix en pièces ;
- un niveau minimum ;
- une disponibilité définie ;
- un rôle ou un cosmétique associé.

Les vérifications sont effectuées avant l’achat.

## Sécurité des achats

Les achats sont effectués avec une transaction PostgreSQL afin d’éviter :

- les doubles paiements ;
- les achats concurrents ;
- les soldes négatifs ;
- les objets accordés sans paiement ;
- les paiements validés sans objet reçu.

Si Discord refuse l’attribution d’un rôle, le système peut annuler ou
rembourser l’opération selon le type d’erreur rencontré.

## Restauration d’un rôle acheté

Lorsqu’un membre a déjà acheté un rôle mais ne le possède plus, la boutique
peut lui permettre de le récupérer sans le lui faire payer une seconde
fois.

## Administration de la boutique

La commande :

```text
/boutique-admin
```

permet notamment de :

- créer un article ;
- choisir le type de l’article ;
- définir son prix ;
- définir un niveau minimum ;
- associer un rôle ;
- associer un cosmétique ;
- activer ou désactiver un article ;
- modifier les articles existants ;
- supprimer un article ;
- consulter le catalogue.

---

# 🔄 Import depuis DraftBot

Le bot possède un outil administratif permettant de migrer la progression
d’un membre depuis DraftBot.

Commande prévue :

```text
/import_draftbot
```

Selon la version déployée, elle peut également apparaître sous un nom
proche comme :

```text
/import-draftbot-xp
```

L’import peut utiliser un fichier HTML exporté depuis DraftBot.

Le système peut notamment extraire :

- l’identifiant Discord du membre ;
- le niveau ;
- l’XP actuelle dans le niveau ;
- l’XP nécessaire au niveau suivant ;
- les informations utiles présentes dans l’export.

L’XP est ensuite convertie dans la courbe de progression du Clan Renard.

## Sécurité de l’import

L’outil d’import prévoit plusieurs protections :

- utilisation réservée à l’administration ou au propriétaire ;
- lecture locale du fichier envoyé à Discord ;
- aperçu avant validation ;
- contrôle de l’identifiant du membre ;
- verrouillage PostgreSQL pendant la modification ;
- validation manuelle avant application ;
- prévention des modifications accidentelles ;
- possibilité de fusion ou de remplacement selon la configuration.

Après une migration définitive, l’extension d’import peut être désactivée
ou supprimée si elle n’est plus nécessaire.

---

# Commandes principales

## Commandes membres

```text
/avent
/profil
/progression
/boutique
```

## Commandes administratives

```text
/avent-admin
/profil-admin
/progression-admin
/boutique-admin
/import_draftbot
```

Les commandes administratives nécessitent généralement la permission :

```text
Gérer le serveur
```

Certaines opérations sensibles peuvent être réservées au propriétaire du
bot.

---

# Architecture du projet

```text
clan-renard-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── health.py
│   │   └── logging.py
│   │
│   ├── extensions/
│   │   ├── advent.py
│   │   ├── profile.py
│   │   ├── progression.py
│   │   ├── shop.py
│   │   └── import_draftbot.py
│   │
│   ├── features/
│   │   └── advent/
│   │       ├── commands.py
│   │       ├── models.py
│   │       ├── repository.py
│   │       ├── service.py
│   │       ├── views.py
│   │       └── renderer.py
│   │
│   └── shared/
│       ├── progression_card.py
│       └── profile_card.py
│
├── assets/
│   ├── advent/
│   ├── branding/
│   ├── profile/
│   │   ├── backgrounds/
│   │   ├── badges/
│   │   ├── frames/
│   │   ├── effects/
│   │   └── titles/
│   └── shared/
│
├── database/
│   └── migrations/
│
├── docs/
├── generated/
├── scripts/
├── tests/
│
├── .env.example
├── .gitignore
├── Dockerfile
├── render.yaml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

L’arborescence exacte peut légèrement varier selon les versions, mais les
extensions restent séparées afin d’éviter de placer tout le bot dans un
seul fichier.

---

# Chargement automatique des extensions

Le fichier principal démarre un seul client Discord.

Les extensions présentes dans :

```text
bot/extensions/
```

sont détectées et chargées automatiquement.

Chaque extension doit généralement contenir une fonction :

```python
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MonCog(bot))
```

Exemple de nouvelle extension :

```text
bot/extensions/moderation.py
```

Pour une fonctionnalité plus importante, il est recommandé de créer un
module dédié :

```text
bot/features/tickets/
├── __init__.py
├── commands.py
├── repository.py
├── service.py
└── views.py
```

Cette organisation permet :

- de faciliter la maintenance ;
- d’isoler les systèmes ;
- de limiter les dépendances circulaires ;
- de tester les fonctionnalités séparément ;
- d’ajouter de nouveaux modules sans modifier tout le bot.

---

# Base de données PostgreSQL

PostgreSQL stocke les données permanentes du bot.

Les données enregistrées comprennent notamment :

- la configuration de l’Avent ;
- les ouvertures de cases ;
- les récompenses ;
- les points saisonniers ;
- les achats saisonniers ;
- les profils ;
- les biographies ;
- les couleurs ;
- les cosmétiques ;
- les inventaires ;
- les équipements ;
- l’XP ;
- les niveaux ;
- les portefeuilles ;
- le total historique de pièces ;
- les récompenses vocales ;
- les multiplicateurs d’XP ;
- les rôles de niveau ;
- les articles de boutique ;
- les achats permanents ;
- les transactions ;
- les journaux administratifs.

Les tables sont créées ou vérifiées au démarrage des différentes
extensions.

Des migrations utilisant notamment :

```sql
CREATE TABLE IF NOT EXISTS ...
```

et :

```sql
ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...
```

permettent de mettre à jour une base existante sans supprimer les données
déjà présentes.

---

# Protection contre les actions concurrentes

Pour les opérations sensibles, le bot utilise :

- des transactions PostgreSQL ;
- des lignes verrouillées avec `FOR UPDATE` ;
- des verrous consultatifs PostgreSQL ;
- des contraintes de base de données ;
- des clés primaires et contraintes d’unicité.

Ces protections sont utilisées notamment pour :

- l’ouverture des cases ;
- les gains de pièces ;
- les achats ;
- les imports ;
- les récompenses vocales ;
- les ajustements administratifs.

L’objectif est d’empêcher qu’un membre obtienne deux fois une récompense ou
dépense deux fois le même solde.

---

# Génération dynamique des images

Les images ne sont généralement pas stockées définitivement.

Lorsqu’une commande graphique est utilisée :

1. les données sont récupérées depuis PostgreSQL ;
2. l’avatar est téléchargé depuis Discord ;
3. Pillow dessine la carte ;
4. l’image est créée dans un tampon mémoire ;
5. le fichier est envoyé à Discord ;
6. le tampon peut ensuite être libéré.

Ce fonctionnement est utilisé pour :

- le calendrier de l’Avent ;
- la carte de profil ;
- la carte de progression.

Il n’est donc pas nécessaire de générer et conserver une image différente
pour chaque membre.

Certains éléments graphiques statiques peuvent cependant être mis en cache
pour améliorer les performances.

---

# Ressources graphiques

## Logo du Clan Renard

Le logo principal peut être placé ici :

```text
assets/branding/clan_renard_logo.png
```

Format conseillé :

- PNG transparent ;
- image carrée ;
- au moins 512 × 512 pixels ;
- peu de marge autour du renard.

Si aucune image n’est disponible, certains rendus peuvent utiliser un
emblème de remplacement.

## Ressources du calendrier

Les images liées au calendrier doivent être placées dans :

```text
assets/advent/
```

Cela peut comprendre :

- arrière-plans ;
- cadeaux ;
- décorations ;
- textures ;
- icônes ;
- éléments spéciaux du 24 décembre.

## Ressources de profil

Les cosmétiques graphiques peuvent être organisés dans :

```text
assets/profile/backgrounds/
assets/profile/badges/
assets/profile/frames/
assets/profile/effects/
assets/profile/titles/
```

Les fichiers doivent correspondre aux chemins enregistrés dans la base de
données.

Les formats recommandés sont :

- PNG pour la transparence ;
- JPG ou WEBP pour les arrière-plans ;
- dimensions cohérentes avec le moteur de rendu ;
- noms de fichiers simples, sans caractères spéciaux.

---

# Prérequis

## Installation locale

Il faut disposer de :

- Python 3.11 ou 3.12 ;
- PostgreSQL ;
- Git ou GitHub Desktop ;
- une application Discord ;
- un token de bot Discord.

## Production

Pour l’hébergement prévu par le projet :

- un compte GitHub ;
- un compte Render ;
- une base PostgreSQL Render ou compatible ;
- un service Web ou Docker Render.

---

# Configuration de l’application Discord

Crée une application depuis :

```text
https://discord.com/developers/applications
```

Ajoute ensuite un bot à l’application.

## Intents recommandés

Dans l’onglet **Bot**, active au minimum les intents nécessaires au projet.

Le plus important pour les systèmes utilisant les membres est :

```text
Server Members Intent
```

Le bot doit également recevoir les événements liés :

- aux serveurs ;
- aux membres ;
- aux messages ;
- aux états vocaux.

Le `Message Content Intent` n’est pas nécessaire pour lire le contenu des
messages si le bot récompense uniquement leur envoi, mais il peut être
nécessaire pour d’autres extensions futures.

## Permissions recommandées

Le bot doit disposer au minimum de :

- Voir les salons ;
- Envoyer des messages ;
- Intégrer des liens ;
- Joindre des fichiers ;
- Lire l’historique des messages ;
- Utiliser les commandes de l’application ;
- Gérer les rôles, si les récompenses de rôles sont utilisées.

Pour les rôles automatiques, le rôle principal du bot doit être placé
au-dessus :

- des rôles de niveau ;
- des rôles de boutique ;
- des rôles du calendrier de l’Avent.

---

# Installation locale

## 1. Cloner le dépôt

```bash
git clone URL_DU_DEPOT
cd clan-renard-bot
```

## 2. Créer un environnement virtuel

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell refuse l’activation :

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

## 3. Installer les dépendances

Pour utiliser le bot :

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Pour le développement et les tests :

```bash
pip install -r requirements-dev.txt
```

## 4. Créer le fichier `.env`

### Windows

```bat
copy .env.example .env
```

### Linux ou macOS

```bash
cp .env.example .env
```

## 5. Configurer les variables

Exemple :

```env
DISCORD_TOKEN=ton_token_discord
DATABASE_URL=postgresql://utilisateur:mot_de_passe@serveur:5432/base
DEFAULT_TIMEZONE=Europe/Paris
ENVIRONMENT=development
LOG_LEVEL=INFO
DEV_GUILD_ID=identifiant_du_serveur_de_test
OWNER_ID=ton_identifiant_discord
PORT=10000
```

Une variable de test peut également exister pour simuler une date de
l’Avent :

```env
ADVENT_TEST_DATE=2025-12-01
```

Cette variable doit être supprimée ou laissée vide en production afin que
le bot utilise la vraie date.

Exemple :

```env
ADVENT_TEST_DATE=
```

## 6. Démarrer le bot

```bash
python -m bot.main
```

---

# Variables d’environnement

## `DISCORD_TOKEN`

Token privé du bot Discord.

```env
DISCORD_TOKEN=...
```

Cette valeur ne doit jamais être publiée.

## `DATABASE_URL`

Adresse complète de la base PostgreSQL.

```env
DATABASE_URL=postgresql://user:password@host:5432/database
```

## `DEFAULT_TIMEZONE`

Fuseau horaire utilisé par défaut.

```env
DEFAULT_TIMEZONE=Europe/Paris
```

## `ENVIRONMENT`

Environnement d’exécution.

```env
ENVIRONMENT=development
```

ou :

```env
ENVIRONMENT=production
```

## `LOG_LEVEL`

Niveau des journaux.

```env
LOG_LEVEL=INFO
```

Valeurs courantes :

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

## `DEV_GUILD_ID`

Identifiant du serveur de développement.

```env
DEV_GUILD_ID=123456789012345678
```

Il permet d’accélérer la synchronisation des commandes pendant le
développement.

## `OWNER_ID`

Identifiant Discord du propriétaire du bot.

```env
OWNER_ID=123456789012345678
```

Cette valeur peut être utilisée pour protéger les outils sensibles comme
l’import.

## `PORT`

Port utilisé par le contrôle de santé HTTP.

```env
PORT=10000
```

Render fournit généralement cette variable automatiquement.

## `ADVENT_TEST_DATE`

Date artificielle utilisée uniquement pour tester le calendrier.

```env
ADVENT_TEST_DATE=2025-12-24
```

Ne pas conserver une date de test active en production.

---

# Premier démarrage

Après avoir démarré le bot :

1. vérifie que PostgreSQL est connecté ;
2. vérifie que les extensions sont chargées ;
3. vérifie que les commandes slash sont synchronisées ;
4. lance les panneaux administratifs.

## Configurer l’Avent

```text
/avent-admin
```

Initialise ensuite la saison, les dates, le salon, les récompenses et le
panneau public.

## Configurer les profils

```text
/profil-admin
```

Crée ou distribue les premiers cosmétiques.

## Configurer la progression

```text
/progression-admin
```

Configure :

- l’XP des messages ;
- les pièces ;
- le cooldown ;
- l’XP vocale ;
- les notifications ;
- les multiplicateurs ;
- les rôles de niveau.

## Configurer la boutique

```text
/boutique-admin
```

Ajoute les rôles et les cosmétiques disponibles à l’achat.

---

# Aperçu du calendrier

La prévisualisation graphique du calendrier peut être générée sans Discord.

```bash
python scripts/preview_calendar.py
```

Résultat habituel :

```text
generated/apercu-calendrier.png
```

Avec une année et un pseudo personnalisés :

```bash
python scripts/preview_calendar.py --year 2026 --name "Mon pseudo"
```

---

# Génération de cosmétiques

Si le projet contient un script de génération de ressources de profil, il
peut être exécuté avec :

```bash
python scripts/generate_profile_cosmetics.py
```

Les fichiers générés doivent ensuite être vérifiés dans les dossiers
correspondants de :

```text
assets/profile/
```

La génération automatique ne remplace pas une vérification manuelle du
rendu dans Discord.

---

# Tests

Exécute les tests avec :

```bash
pytest
```

Ou :

```bash
python -m pytest
```

Pour vérifier les fichiers Python et la structure du projet :

```bash
python scripts/check_project.py
```

Une compilation rapide de tous les fichiers Python peut également être
effectuée avec :

```bash
python -m compileall bot scripts
```

---

# Docker

Le projet contient un `Dockerfile`.

Construction locale :

```bash
docker build -t clan-renard-bot .
```

Démarrage :

```bash
docker run --env-file .env clan-renard-bot
```

Si PostgreSQL est exécuté en dehors du conteneur, vérifie que
`DATABASE_URL` pointe vers une adresse accessible depuis Docker.

---

# Déploiement sur Render

Le projet est prévu pour être déployé sur Render.

Les fichiers utilisés sont notamment :

```text
Dockerfile
render.yaml
```

## Déploiement conseillé

1. pousse le projet sur GitHub ;
2. connecte le dépôt à Render ;
3. crée une base PostgreSQL ;
4. crée le service du bot ;
5. ajoute les variables d’environnement ;
6. déploie le service ;
7. consulte les journaux ;
8. vérifie la connexion Discord ;
9. vérifie la synchronisation des commandes.

## Variables à enregistrer sur Render

Au minimum :

```text
DISCORD_TOKEN
DATABASE_URL
DEFAULT_TIMEZONE
ENVIRONMENT
LOG_LEVEL
OWNER_ID
```

Render fournit généralement :

```text
PORT
```

Les secrets doivent être enregistrés dans l’interface Render et non dans
le dépôt GitHub.

---

# Contrôle de santé HTTP

Le bot démarre un petit serveur HTTP pour permettre à Render ou à un
service de surveillance de vérifier qu’il fonctionne.

Une route de santé peut être disponible, par exemple :

```text
/health
```

Elle permet de vérifier que le processus répond toujours.

Les requêtes régulières provenant d’un outil comme UptimeRobot peuvent
être masquées ou enregistrées avec un niveau de journalisation réduit afin
d’éviter de remplir les logs.

Le contrôle HTTP ne remplace pas la vérification de la connexion Discord
ou PostgreSQL.

---

# Journaux

Le bot utilise le module standard `logging`.

Les journaux peuvent notamment indiquer :

- la connexion à PostgreSQL ;
- la création ou la migration des tables ;
- le chargement des extensions ;
- la synchronisation des commandes ;
- la connexion du bot à Discord ;
- le lancement des boucles automatiques ;
- les erreurs d’envoi de messages ;
- les erreurs d’attribution de rôles ;
- les erreurs de génération d’image ;
- les erreurs de récompense vocale ;
- les erreurs d’achat ;
- les erreurs d’import.

En production, le niveau recommandé est généralement :

```env
LOG_LEVEL=INFO
```

Utilise `DEBUG` uniquement pour diagnostiquer un problème, car il peut
produire beaucoup plus de journaux.

---

# Permissions et hiérarchie des rôles

Pour que les rôles automatiques fonctionnent :

1. ouvre les paramètres du serveur Discord ;
2. va dans **Rôles** ;
3. place le rôle du bot au-dessus des rôles à gérer ;
4. donne au bot la permission **Gérer les rôles**.

Le bot ne peut pas gérer :

- le rôle `@everyone` ;
- les rôles gérés par une intégration ;
- les rôles situés au-dessus de son propre rôle ;
- les rôles ayant la même position ou une position supérieure.

Cela concerne :

- les rôles de l’Avent ;
- les rôles de boutique ;
- les rôles de niveau ;
- les rôles distribués par l’administration.

---

# Différence entre les monnaies

Le bot possède deux économies séparées.

## Points de l’Avent

```text
Monnaie saisonnière
```

Utilisation :

- calendrier de l’Avent ;
- classement saisonnier ;
- boutique de l’Avent.

Ils peuvent être réinitialisés ou remplacés lors d’une nouvelle saison.

## Pièces permanentes

```text
Monnaie permanente
```

Utilisation :

- récompenses de messages ;
- boutique permanente ;
- classement argent ;
- achats durables.

Les pièces ne sont pas réinitialisées avec le calendrier de l’Avent, sauf
action administrative explicite.

---

# Sécurité

Ne publie jamais :

- le token Discord ;
- le fichier `.env` ;
- le mot de passe PostgreSQL ;
- une URL PostgreSQL contenant un mot de passe ;
- les cookies ou identifiants d’un autre service ;
- les exports privés contenant des informations sensibles ;
- les codes cadeaux privés ;
- les sauvegardes de la base de données.

Le fichier `.env` doit être exclu par `.gitignore`.

Exemple :

```gitignore
.env
.venv/
__pycache__/
*.pyc
generated/
```

Sur Render, les secrets doivent être enregistrés dans les variables
d’environnement du service.

Si un token Discord est publié accidentellement :

1. ouvre le portail développeur Discord ;
2. réinitialise immédiatement le token ;
3. modifie la variable `DISCORD_TOKEN` sur Render ;
4. redéploie le service ;
5. supprime le token de l’historique Git si nécessaire.

---

# Sauvegardes

La base PostgreSQL contient toutes les données permanentes importantes.

Il est recommandé de sauvegarder régulièrement :

- les profils ;
- les inventaires ;
- les achats ;
- les progressions ;
- les portefeuilles ;
- les configurations ;
- les récompenses de l’Avent.

Avant une modification importante de la structure SQL, crée une sauvegarde
de la base.

---

# Documentation complémentaire

Selon la version du dépôt, des guides supplémentaires peuvent être
disponibles dans :

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

# Ajouter un nouveau module

Pour ajouter une fonctionnalité simple, crée une extension :

```text
bot/extensions/nom_du_module.py
```

Exemple minimal :

```python
from discord.ext import commands


class ExempleCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ExempleCog(bot))
```

Pour un système plus important, sépare :

- les commandes ;
- les vues ;
- la logique métier ;
- les requêtes PostgreSQL ;
- les modèles ;
- le rendu graphique.

Évite de placer plusieurs milliers de lignes dans un seul fichier si les
fonctionnalités peuvent être séparées proprement.

---

# Résumé des systèmes

| Système | Commande membre | Commande administrative | Données permanentes |
|---|---|---|---|
| Calendrier de l’Avent | `/avent` | `/avent-admin` | Oui |
| Profils | `/profil` | `/profil-admin` | Oui |
| Progression | `/progression` | `/progression-admin` | Oui |
| Boutique permanente | `/boutique` | `/boutique-admin` | Oui |
| Import DraftBot | — | `/import_draftbot` | Oui |
| XP vocale | Automatique | `/progression-admin` | Oui |
| Rôles de niveau | Automatique | `/progression-admin` | Oui |
| Contrôle de santé | HTTP | Configuration Render | Non |

---

# État actuel du projet

Le bot prend actuellement en charge :

- plusieurs extensions chargées automatiquement ;
- des commandes slash ;
- des interfaces avec boutons, menus et formulaires ;
- PostgreSQL ;
- des transactions sécurisées ;
- des images générées avec Pillow ;
- les profils personnalisés ;
- la progression textuelle et vocale ;
- les économies saisonnière et permanente ;
- les boutiques ;
- les rôles automatiques ;
- l’import de données ;
- Docker ;
- Render ;
- un contrôle de santé HTTP ;
- des scripts et tests de maintenance.

Le projet est conçu pour continuer à recevoir de nouveaux modules sans
devoir réécrire le cœur du bot.

---

# Licence et utilisation

Projet développé pour la communauté **Clan Renard**.

Avant de redistribuer ou de publier une version modifiée, vérifie les
conditions de licence présentes dans le dépôt.
````*
