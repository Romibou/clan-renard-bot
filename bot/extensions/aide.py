from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)

HELP_COLOR = discord.Color.from_rgb(226, 104, 161)

# Catégorie de chaque commande. Une commande absente de cette liste
# apparaît quand même, dans « Autres ».
CATEGORIES: dict[str, tuple[str, ...]] = {
    "⭐ Progression": (
        "progression",
        "classement",
        "stats",
        "bilan",
    ),
    "🎁 Récompenses": (
        "quotidien",
        "hebdomadaire",
        "mensuel",
        "missions",
    ),
    "🛍️ Boutique et profil": (
        "boutique",
        "profil",
        "collections",
        "donner",
    ),
    "🎄 Calendrier de l'Avent": (
        "avent",
        "avent-profil",
        "avent-recompenses",
        "avent-classement",
        "avent-boutique",
        "avent-aide",
    ),
    "🎮 Mini-jeux": (
        "jeu",
    ),
    "🧰 Outils": (
        "anniversaire",
        "anniversaires-liste",
        "rappel",
        "ping",
        "aide",
    ),
}

OTHER_CATEGORY = "📦 Autres"


def is_admin_command(
    command: app_commands.Command | app_commands.Group,
) -> bool:
    """
    Une commande est réservée à l'administration lorsqu'elle exige une
    permission Discord par défaut (Gérer le serveur, Administrateur…).
    """
    permissions = command.default_permissions

    return permissions is not None and permissions.value != 0


def format_command(
    command: app_commands.Command | app_commands.Group,
) -> str:
    description = command.description or "Aucune description."
    return f"`/{command.name}` — {description}"


def build_help_embed(
    commands_list: list[app_commands.Command | app_commands.Group],
    *,
    show_admin: bool,
) -> discord.Embed:
    member_commands = [
        command
        for command in commands_list
        if not is_admin_command(command)
    ]
    admin_commands = sorted(
        (
            command
            for command in commands_list
            if is_admin_command(command)
        ),
        key=lambda command: command.name,
    )

    by_name = {
        command.name: command
        for command in member_commands
    }

    embed = discord.Embed(
        title="❔ Aide du Clan Renard",
        description=(
            "Voici les commandes disponibles. Tape `/` dans le salon "
            "puis le nom de la commande pour l'utiliser."
        ),
        color=HELP_COLOR,
    )

    placed: set[str] = set()

    for category, names in CATEGORIES.items():
        lines = [
            format_command(by_name[name])
            for name in names
            if name in by_name
        ]
        placed.update(
            name
            for name in names
            if name in by_name
        )

        if lines:
            embed.add_field(
                name=category,
                value="\n".join(lines)[:1024],
                inline=False,
            )

    others = sorted(
        name
        for name in by_name
        if name not in placed
    )

    if others:
        embed.add_field(
            name=OTHER_CATEGORY,
            value="\n".join(
                format_command(by_name[name])
                for name in others
            )[:1024],
            inline=False,
        )

    if show_admin and admin_commands:
        lines = [
            f"`/{command.name}`"
            for command in admin_commands
        ]
        embed.add_field(
            name="🛡️ Administration (visible par toi seulement)",
            value=", ".join(lines)[:1024],
            inline=False,
        )

    embed.set_footer(text="Clan Renard")

    return embed


class HelpCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    @app_commands.command(
        name="aide",
        description="Affiche la liste des commandes du bot.",
    )
    async def aide(
        self,
        interaction: discord.Interaction,
    ) -> None:
        show_admin = (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.manage_guild
        )

        embed = build_help_embed(
            list(self.bot.tree.get_commands()),
            show_admin=show_admin,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(HelpCog(bot))
    LOGGER.info("Commande /aide chargée")
