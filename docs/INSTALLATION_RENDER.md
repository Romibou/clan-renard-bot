# Déploiement de Clan Renard Bot sur Render

Le projet contient :

```text
Dockerfile
render.yaml
```

Le bot peut donc être créé avec un Blueprint Render ou avec une
configuration manuelle.

Le projet utilise un service web léger, car le bot expose :

```text
GET /
GET /health
```

Cet endpoint permet à Render de contrôler le service pendant que
la connexion Discord fonctionne en arrière-plan.

## Prérequis

Avant de commencer :

- le projet doit être publié sur GitHub ;
- l'application Discord doit exister ;
- le token Discord doit être disponible ;
- aucun secret ne doit être présent dans le dépôt.

## Option recommandée : Blueprint Render

### 1. Ouvrir Render

Rendez-vous sur :

<https://dashboard.render.com/>

Connecte-toi puis relie ton compte GitHub.

### 2. Créer un Blueprint

Dans le tableau de bord, utilise :

```text
New
> Blueprint
```

Sélectionne le dépôt :

```text
clan-renard-bot
```

Render lit automatiquement :

```text
render.yaml
```

Le Blueprint prévoit :

- le service `clan-renard-bot` ;
- la base PostgreSQL `clan-renard-db` ;
- la liaison automatique de `DATABASE_URL` ;
- le contrôle de santé `/health`.

### 3. Valider les ressources

Vérifie les noms et les offres proposées.

Les offres disponibles et leurs limitations peuvent évoluer.
Sélectionne les plans compatibles avec ton compte Render.

Si Render refuse une valeur de plan présente dans `render.yaml`,
modifie le plan depuis l'interface ou adapte le fichier aux offres
actuellement disponibles.

### 4. Ajouter le token Discord

Render demande la valeur de :

```text
DISCORD_TOKEN
```

Colle le token du bot Discord.

Cette valeur doit être marquée comme secrète et ne doit jamais être
ajoutée au dépôt GitHub.

### 5. Facultatif : serveur de développement

Ajoute éventuellement :

```text
DEV_GUILD_ID
```

avec l'identifiant du serveur Clan Renard.

Cela permet une synchronisation rapide des commandes sur ce serveur.

### 6. Déployer

Lance la création du Blueprint.

Render va :

1. créer PostgreSQL ;
2. construire l'image Docker ;
3. installer Python et les dépendances ;
4. copier le code et les assets ;
5. démarrer `python -m bot.main` ;
6. créer automatiquement les tables PostgreSQL ;
7. connecter le bot à Discord.

## Configuration manuelle

Si tu ne souhaites pas utiliser le Blueprint, crée d'abord une base
PostgreSQL depuis le tableau de bord Render.

Donne-lui par exemple le nom :

```text
clan-renard-db
```

Crée ensuite un nouveau service web relié au dépôt GitHub.

Choisis l'environnement Docker afin que Render utilise :

```text
Dockerfile
```

Configure :

```text
Health Check Path : /health
```

Ajoute les variables d'environnement suivantes :

```text
DISCORD_TOKEN
DATABASE_URL
DEFAULT_TIMEZONE
ENVIRONMENT
LOG_LEVEL
DEV_GUILD_ID
OWNER_ID
```

Valeurs recommandées :

```env
DEFAULT_TIMEZONE=Europe/Paris
ENVIRONMENT=production
LOG_LEVEL=INFO
```

`DEV_GUILD_ID` et `OWNER_ID` sont facultatifs.

Pour `DATABASE_URL`, utilise de préférence la liaison fournie par
Render entre le service et la base PostgreSQL.

## Variables obligatoires

### `DISCORD_TOKEN`

Token secret obtenu sur le portail développeur Discord.

### `DATABASE_URL`

URL de connexion PostgreSQL.

Le programme accepte une URL commençant par :

```text
postgres://
```

ou :

```text
postgresql://
```

## Variables facultatives

### `DEFAULT_TIMEZONE`

Valeur par défaut :

```text
Europe/Paris
```

### `ENVIRONMENT`

En production :

```text
production
```

### `LOG_LEVEL`

Valeur conseillée :

```text
INFO
```

Pour un diagnostic temporaire :

```text
DEBUG
```

Évite de conserver trop longtemps le niveau DEBUG en production.

### `DEV_GUILD_ID`

Identifiant du serveur où synchroniser rapidement les commandes.

Si cette variable est absente, les commandes sont synchronisées
globalement.

### `OWNER_ID`

Identifiant Discord du propriétaire du bot.

Cette valeur prépare les futures commandes réservées au propriétaire.

### `PORT`

Render fournit généralement cette variable automatiquement.

Valeur locale par défaut :

```text
10000
```

## Lire les logs

Dans le service Render, ouvre l'onglet :

```text
Logs
```

Un démarrage correct affiche des lignes ressemblant à :

```text
Démarrage de Clan Renard Bot
Connexion PostgreSQL établie
Schéma PostgreSQL vérifié
Système du calendrier de l'Avent initialisé
Extension chargée : bot.extensions.advent
Serveur de santé disponible
Bot connecté
```

## Contrôle de santé

Render appelle :

```text
/health
```

La réponse contient notamment :

```json
{
  "status": "ok",
  "discord_ready": true,
  "database_ready": true,
  "latency_ms": 42
}
```

Juste après un démarrage, `discord_ready` peut être temporairement
faux pendant la connexion à Discord.

`database_ready` doit normalement être vrai.

## Premier paramétrage après déploiement

Dans Discord :

```text
/avent-admin-initialiser
```

Puis :

```text
/avent-admin-canal
/avent-admin-heure
/avent-admin-rattrapage
/avent-admin-annonces
```

Configure les récompenses :

```text
/avent-admin-recompense-message
/avent-admin-recompense-points
/avent-admin-recompense-role
/avent-admin-recompense-aleatoire
```

Vérifie :

```text
/avent-admin-apercu
```

Publie enfin :

```text
/avent-admin-publier
```

## Déploiements automatiques

Lorsque tu envoies un nouveau commit sur GitHub :

```text
GitHub Desktop
> Push origin
```

Render détecte normalement le changement et reconstruit le service.

Surveille toujours les logs après un déploiement.

## Stockage des images

Les calendriers sont générés en mémoire.

Le bot ne dépend donc pas du disque local Render pour conserver les
données des membres.

Toutes les données importantes sont enregistrées dans PostgreSQL :

- campagnes ;
- récompenses ;
- ouvertures ;
- points ;
- panneaux ;
- annonces ;
- journaux d'audit.

## Sauvegardes PostgreSQL

Consulte les possibilités de sauvegarde liées au plan PostgreSQL
sélectionné sur Render.

Avant une modification importante ou une réinitialisation massive,
effectue une sauvegarde si ton offre le permet.

## Problèmes fréquents

### Le build Docker échoue

Consulte les premières lignes marquées `ERROR`.

Vérifie notamment :

- `requirements.txt` ;
- la version de Python ;
- la présence de tous les fichiers ;
- la syntaxe Python avec `scripts/check_project.py`.

### Le service démarre puis s'arrête

Les causes fréquentes sont :

- `DISCORD_TOKEN` absent ;
- `DATABASE_URL` absente ;
- token Discord invalide ;
- base PostgreSQL inaccessible ;
- extension impossible à charger.

### Le contrôle de santé échoue

Vérifie :

- que Render fournit `PORT` ;
- que le service écoute sur `0.0.0.0` ;
- que le chemin est `/health` ;
- que PostgreSQL répond.

### Les commandes Discord ne sont pas visibles

Vérifie :

- le scope `applications.commands` ;
- `DEV_GUILD_ID` ;
- les logs de synchronisation ;
- que le bot est bien en ligne.

### PostgreSQL refuse la connexion

Vérifie que le service utilise la bonne URL de connexion et que la
base n'est pas suspendue, expirée ou supprimée.

Les conditions des offres Render peuvent évoluer. Consulte le tableau
de bord et la documentation Render si une ressource gratuite n'est
plus disponible.

### Le bot redémarre après une modification

C'est normal lors d'un nouveau déploiement.

Les ouvertures restent enregistrées dans PostgreSQL et les boutons
persistants sont réenregistrés au démarrage.
