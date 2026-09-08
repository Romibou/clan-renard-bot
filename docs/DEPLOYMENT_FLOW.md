# Flux de déploiement

Le fonctionnement global est :

```text
Ordinateur
    ↓
GitHub Desktop
    ↓
Dépôt GitHub
    ↓
Render
    ├── Service Clan Renard Bot
    └── PostgreSQL
            ↓
         Discord
```

## Lors d'une modification

1. Modifie les fichiers sur ton ordinateur.
2. Lance les tests.
3. Vérifie le calendrier si le graphisme a changé.
4. Crée un commit dans GitHub Desktop.
5. Utilise `Push origin`.
6. Render détecte le changement.
7. Render reconstruit le service.
8. Le bot redémarre.
9. Les extensions sont chargées.
10. Les boutons persistants sont réenregistrés.
11. PostgreSQL conserve les données.

## Commandes de vérification locale

```bash
python scripts/check_project.py
pytest
python scripts/preview_calendar.py
```

## Commande de démarrage

```bash
python -m bot.main
```

## Endpoint Render

```text
GET /health
```

## Source de vérité

Le dépôt GitHub contient :

- le code ;
- les assets ;
- la documentation ;
- la configuration non secrète.

PostgreSQL contient :

- les campagnes ;
- les récompenses ;
- les ouvertures ;
- les points ;
- les annonces ;
- les journaux.

Render contient les secrets :

- `DISCORD_TOKEN` ;
- `DATABASE_URL`.

Aucun secret réel ne doit être présent dans GitHub.
