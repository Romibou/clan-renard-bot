# Commandes administratives du calendrier

Toutes ces commandes nécessitent la permission Discord
`Administrateur`.

## Création de la campagne

```text
/avent-admin-initialiser
```

Exemple :

```text
annee: 2026
fuseau: Europe/Paris
titre: Calendrier de l'Avent
```

Une campagne existante pour la même année est actualisée sans
supprimer ses ouvertures ou ses récompenses.

## Configuration générale

```text
/avent-admin-config
/avent-admin-activer
/avent-admin-canal
/avent-admin-fuseau
/avent-admin-heure
/avent-admin-rattrapage
/avent-admin-annonces
```

## Récompense textuelle

```text
/avent-admin-recompense-message
```

## Récompense en points

```text
/avent-admin-recompense-points
```

## Récompense de rôle

```text
/avent-admin-recompense-role
```

Le rôle du bot doit être placé au-dessus du rôle distribué.

## Récompense aléatoire

```text
/avent-admin-recompense-aleatoire
```

Le champ `choix_json` accepte une liste JSON sur une seule ligne.

Exemple :

```json

[
  {
    "type": "points",
    "weight": 70,
    "data": {
      "points": 100,
      "message": "Tu remportes 100 points !"
    }
  },
  {
    "type": "points",
    "weight": 25,
    "data": {
      "points": 500
    }
  },
  {
    "type": "role",
    "weight": 5,
    "data": {
      "role_id": 123456789012345678,
      "message": "Tu remportes le rôle rare !"
    }
  }
]

```

`weight` représente un poids relatif. Les valeurs n'ont pas besoin
d'avoir une somme exactement égale à 100.

Types autorisés dans les choix :

- `message` ;
- `points` ;
- `role`.

Une récompense `random` ne peut pas contenir une seconde récompense
`random`.

## Consultation et suppression

```text
/avent-admin-recompenses
/avent-admin-recompense-supprimer
```

La suppression d'une configuration ne modifie jamais les gains déjà
enregistrés. Chaque ouverture conserve un instantané de sa récompense.

## Aperçu et publication

```text
/avent-admin-apercu
/avent-admin-publier
```

Le panneau public ne contient pas le calendrier personnel d'un
administrateur. Chaque membre utilise les boutons pour recevoir son
propre calendrier en réponse éphémère.

## Gestion des membres

```text
/avent-admin-utilisateur
/avent-admin-reset-utilisateur
```

La réinitialisation demande une confirmation et efface les ouvertures
de la campagne sélectionnée. Elle ne retire pas automatiquement les
rôles déjà distribués par Discord.
