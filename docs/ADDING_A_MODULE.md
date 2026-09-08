# Ajouter un module à Clan Renard Bot

Le programme principal ne doit pas être modifié pour chaque nouvelle
fonctionnalité.

Le fichier suivant recherche automatiquement les extensions :

```text
bot/core/extension_loader.py
```

## Petit module

Pour une petite fonctionnalité, crée simplement :

```text
bot/extensions/moderation.py
```

Exemple minimal :

```python
import discord
from discord import app_commands
from discord.ext import commands


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="nettoyer",
        description="Supprime plusieurs messages.",
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def clear(
        self,
        interaction: discord.Interaction,
        nombre: app_commands.Range[int, 1, 100],
    ) -> None:
        if interaction.channel is None:
            return

        await interaction.response.defer(
            ephemeral=True
        )

        deleted = await interaction.channel.purge(
            limit=nombre
        )

        await interaction.followup.send(
            f"{len(deleted)} message(s) supprimé(s).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
```

Au redémarrage, le chargeur trouve automatiquement :

```text
bot.extensions.moderation
```

La nouvelle commande rejoint le même bot Discord.

## Gros module

Pour un système important, utilise cette structure :

```text
bot/extensions/tickets.py

bot/features/tickets/
├── __init__.py
├── commands.py
├── repository.py
├── service.py
├── views.py
└── exceptions.py
```

Le fichier `bot/extensions/tickets.py` sert uniquement de point
d'entrée. Il instancie les services et ajoute les Cogs.

## Base PostgreSQL

Tous les modules peuvent utiliser :

```python
bot.database
```

N'ouvre pas une nouvelle connexion PostgreSQL pour chaque
fonctionnalité.

Ajoute les nouvelles tables dans un fichier de migration ou dans le
schéma pendant le développement. Utilise des noms explicites :

```text
moderation_cases
ticket_panels
ticket_channels
level_profiles
```

## Assets

Les chemins prévus sont :

```text
assets/advent/
assets/branding/
assets/shared/
```

Pour un nouveau système :

```text
assets/tickets/
assets/moderation/
```

N'utilise pas le dossier `generated/` pour des fichiers importants :
son contenu n'est pas envoyé sur GitHub et peut disparaître sur
Render.

## Bonnes pratiques

- un Cog reçoit les interactions Discord ;
- un service contient les règles métier ;
- un repository contient les requêtes SQL ;
- une View contient les boutons et menus ;
- un fichier de thème contient les couleurs ;
- les secrets restent dans les variables d'environnement ;
- les nouvelles erreurs sont journalisées ;
- les opérations importantes disposent de tests.
