# Installation de Clan Renard sur Discord

Ce guide explique comment créer l'application Discord, configurer
le bot, activer les intents nécessaires et l'inviter sur le serveur.

## 1. Ouvrir le portail développeur Discord

Rendez-vous sur :

<https://discord.com/developers/applications>

Connecte-toi avec ton compte Discord.

## 2. Créer l'application

Clique sur :

```text
New Application
```

Donne-lui le nom :

```text
Clan Renard
```

Accepte les conditions, puis clique sur le bouton de création.

Tu peux ensuite personnaliser :

- l'icône de l'application ;
- sa description ;
- ses informations générales.

## 3. Récupérer l'identifiant de l'application

Dans :

```text
General Information
```

repère :

```text
Application ID
```

Cet identifiant n'est pas secret. Il pourra servir à vérifier
l'application ou à générer un lien d'invitation manuellement.

## 4. Créer le bot

Dans le menu de gauche, ouvre :

```text
Bot
```

Clique sur :

```text
Add Bot
```

ou sur le bouton permettant de créer le compte bot.

Confirme la création.

## 5. Configurer le nom et l'avatar

Dans la page `Bot`, configure si nécessaire :

```text
Username : Clan Renard
```

Ajoute également l'avatar du serveur ou du renard.

## 6. Récupérer le token

Toujours dans la page `Bot`, utilise :

```text
Reset Token
```

puis copie le token.

Le token est un mot de passe extrêmement sensible.

Ne le place jamais :

- dans un message Discord ;
- dans une capture d'écran ;
- dans un fichier envoyé à quelqu'un ;
- directement dans le code Python ;
- dans le dépôt GitHub ;
- dans le fichier `.env.example`.

Pour un test local, place-le uniquement dans le fichier `.env` :

```env
DISCORD_TOKEN=colle_le_token_ici
```

Pour Render, ajoute-le dans les variables d'environnement secrètes.

Si le token a été publié par erreur, retourne immédiatement sur le
portail développeur et utilise `Reset Token`.

## 7. Activer les intents

Dans la page :

```text
Bot
```

cherche la section :

```text
Privileged Gateway Intents
```

Active :

```text
Server Members Intent
```

Cet intent est utile pour :

- retrouver les membres du serveur ;
- attribuer les rôles gagnés ;
- préparer les futurs modules ;
- faciliter les fonctionnalités de modération futures.

Le calendrier n'utilise pas le contenu des messages ordinaires.
Il n'est donc pas nécessaire d'activer `Message Content Intent`
pour la version actuelle.

`Presence Intent` n'est pas nécessaire non plus.

Enregistre les modifications.

## 8. Configurer l'installation

Dans le menu de gauche, ouvre :

```text
Installation
```

ou, selon l'interface du portail :

```text
OAuth2 > URL Generator
```

Sélectionne les scopes :

```text
bot
applications.commands
```

Les permissions recommandées pour la version actuelle sont :

```text
View Channels
Send Messages
Embed Links
Attach Files
Read Message History
Use External Emojis
```

Ajoute également :

```text
Manage Roles
```

uniquement si le calendrier doit distribuer des rôles.

Il n'est pas nécessaire de donner la permission `Administrator`
au bot.

Le bot doit recevoir uniquement les permissions dont il a réellement
besoin.

## 9. Inviter le bot

Copie l'URL d'installation générée.

Ouvre-la dans le navigateur, sélectionne le serveur Clan Renard puis
confirme l'autorisation.

Ton compte Discord doit posséder une permission permettant d'ajouter
des applications au serveur.

Une fois invité, le bot apparaît hors ligne tant que le programme
Python ou le service Render n'est pas lancé.

## 10. Configurer la hiérarchie des rôles

Dans Discord, ouvre :

```text
Paramètres du serveur
> Rôles
```

Repère le rôle du bot Clan Renard.

Place-le au-dessus de tous les rôles qu'il devra distribuer.

Exemple correct :

```text
Administrateur
Modérateur
Clan Renard Bot
Récompense Avent rare
Récompense Avent
Membres
@everyone
```

Le bot ne peut jamais attribuer :

- un rôle placé au-dessus de son rôle principal ;
- un rôle situé exactement au même niveau ;
- un rôle géré par une autre intégration ;
- le rôle `@everyone`.

## 11. Activer le mode développeur Discord

Pour récupérer les identifiants nécessaires, ouvre dans Discord :

```text
Paramètres utilisateur
> Avancés
> Mode développeur
```

Active le mode développeur.

Tu peux ensuite faire un clic droit sur :

- le serveur ;
- un utilisateur ;
- un rôle ;
- un salon ;
- un message.

Puis choisir :

```text
Copier l'identifiant
```

## 12. Récupérer l'identifiant du serveur de test

Fais un clic droit sur le serveur Clan Renard et utilise :

```text
Copier l'identifiant du serveur
```

Pour les tests locaux, ajoute-le au fichier `.env` :

```env
DEV_GUILD_ID=123456789012345678
```

Lorsque cette variable est configurée, les commandes slash sont
synchronisées directement sur ce serveur et apparaissent
généralement beaucoup plus rapidement.

En production, tu peux conserver cette variable pour un serveur
précis ou la laisser vide afin d'utiliser les commandes globales.

Les commandes globales peuvent demander davantage de temps avant
d'apparaître partout.

## 13. Premier lancement

Lance le bot localement avec :

```bash
python -m bot.main
```

ou déploie-le sur Render.

Dans les logs, vérifie la présence de messages semblables à :

```text
Connexion PostgreSQL établie
Schéma PostgreSQL vérifié
Extension chargée : bot.extensions.advent
Bot connecté
```

## 14. Initialiser le calendrier

Dans Discord, utilise :

```text
/avent-admin-initialiser
```

Exemple :

```text
annee: 2026
fuseau: Europe/Paris
titre: Calendrier de l'Avent
```

Configure ensuite le canal :

```text
/avent-admin-canal
```

Configure les récompenses, puis vérifie l'aperçu :

```text
/avent-admin-apercu
```

Enfin, publie le panneau :

```text
/avent-admin-publier
```

## 15. Vérifier les commandes

Les commandes membres principales sont :

```text
/avent
/avent-ouvrir
/avent-profil
/avent-recompenses
/avent-classement
/avent-aide
```

Les commandes dont le nom commence par :

```text
/avent-admin-
```

nécessitent la permission Discord `Administrateur`.

## Problèmes fréquents

### Le bot apparaît hors ligne

Le programme Python ou le service Render n'est pas lancé.

Consulte les logs afin de rechercher :

- une variable manquante ;
- un token invalide ;
- une erreur PostgreSQL ;
- une erreur de syntaxe ;
- une extension impossible à charger.

### Le bot indique un token invalide

Retourne dans le portail développeur, réinitialise le token, puis
remplace la valeur de `DISCORD_TOKEN`.

Ne laisse aucun espace avant ou après le token.

### Les commandes slash n'apparaissent pas

Vérifie :

- le scope `applications.commands` ;
- que le bot est bien connecté ;
- la valeur de `DEV_GUILD_ID` ;
- les logs de synchronisation ;
- que tu utilises le bon serveur.

### Les boutons ne fonctionnent plus après un redémarrage

Le projet réenregistre automatiquement `AdventView` au démarrage.

Vérifie que l'extension suivante est correctement chargée :

```text
bot.extensions.advent
```

### Le bot ne peut pas envoyer l'image

Vérifie dans le salon :

- `Voir le salon` ;
- `Envoyer des messages` ;
- `Intégrer des liens` ;
- `Joindre des fichiers`.

### Le bot ne peut pas attribuer un rôle

Vérifie :

- `Gérer les rôles` ;
- la hiérarchie des rôles ;
- que le rôle n'est pas géré par une intégration ;
- que le rôle existe toujours.
