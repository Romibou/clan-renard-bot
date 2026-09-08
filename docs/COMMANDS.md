# Commandes de Clan Renard

## Commandes accessibles aux membres

### `/avent`

Affiche le calendrier personnel de la personne qui utilise la
commande.

Le calendrier est envoyé en réponse éphémère afin de ne pas remplir
le salon avec de nombreuses images personnelles.

### `/avent-ouvrir`

Ouvre la case disponible du jour.

Si le rattrapage est activé, il est possible d'indiquer une ancienne
journée :

```text
/avent-ouvrir jour:4
```

Le bot vérifie systématiquement :

- que la campagne existe ;
- qu'elle est activée ;
- qu'elle a commencé ;
- qu'elle n'est pas terminée ;
- que la journée est autorisée ;
- que la case n'a pas déjà été ouverte.

La base PostgreSQL empêche également les doubles ouvertures causées
par deux clics très rapides.

### `/avent-profil`

Affiche :

- les cases ouvertes ;
- les cases manquées ;
- les points remportés ;
- l'état actuel de la campagne.

### `/avent-recompenses`

Affiche les récompenses obtenues pendant la campagne.

Les résultats aléatoires affichés sont ceux qui ont réellement été
enregistrés au moment de l'ouverture. Ils ne sont jamais recalculés.

### `/avent-classement`

Affiche les dix membres les mieux classés.

L'ordre est déterminé par :

1. le nombre de cases ouvertes ;
2. le nombre de points ;
3. l'identifiant Discord en cas d'égalité parfaite.

### `/avent-aide`

Affiche une aide résumée.

## Boutons

Les calendriers et panneaux utilisent quatre boutons :

- `🎁 Ouvrir la case` ;
- `🔄 Actualiser` ;
- `🏆 Mes récompenses` ;
- `❔ Aide`.

Ces boutons sont persistants et sont réenregistrés lors de chaque
redémarrage du bot.
