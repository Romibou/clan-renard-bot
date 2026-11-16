"""
/collections : tableau des collections de cosmétiques d'un membre.

Les cosmétiques sont regroupés automatiquement grâce à leur identifiant,
écrit sous la forme « type-collection » :

    background-volcan-2026, badge-volcan-2026, frame-volcan-2026…
    → collection « volcan-2026 », affichée « 🌋 Volcan 2026 ».

Une collection doit contenir au moins 2 cosmétiques. Les émojis du
serveur nommés clanrenard_yes et clanrenard_no sont utilisés s'ils
existent, sinon ✅ et ❌.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)

COLLECTION_COLOR = discord.Color.from_rgb(226, 104, 161)

# Premier mot de l'identifiant qui désigne le type du cosmétique.
TYPE_PREFIXES = {
    "badge",
    "background",
    "bg",
    "fond",
    "frame",
    "cadre",
    "effect",
    "effet",
    "title",
    "titre",
}

# Nom et émoji affichés pour les thèmes connus. Un thème absent de
# cette liste s'affiche avec son nom, sans émoji particulier.
THEMES = {
    "snow": ("❄️", "Hiver"),
    "hiver": ("❄️", "Hiver"),
    "noel": ("🎄", "Noël"),
    "volcan": ("🌋", "Volcan"),
    "ocean": ("🌊", "Océan"),
    "eau": ("💧", "Eau"),
    "nocturne": ("🌙", "Nocturne"),
    "desert": ("🏜️", "Désert"),
    "foret": ("🌲", "Forêt"),
    "temple": ("🏯", "Temple"),
    "halloween": ("🎃", "Halloween"),
}

TYPE_ORDER = ["background", "frame", "badge", "effect", "title"]
YES_EMOJI_NAME = "clanrenard_yes"
NO_EMOJI_NAME = "clanrenard_no"


@dataclass(frozen=True, slots=True)
class CollectionItem:
    name: str
    cosmetic_type: str
    owned: bool


@dataclass(frozen=True, slots=True)
class Collection:
    key: str
    label: str
    items: tuple[CollectionItem, ...]

    @property
    def owned(self) -> int:
        return sum(1 for item in self.items if item.owned)

    @property
    def complete(self) -> bool:
        return self.owned == len(self.items)


def collection_key(identifier: str) -> str | None:
    """« badge-volcan-2026 » → « volcan-2026 » ; « title-bot » → « bot »."""
    parts = identifier.strip().lower().split("-")

    if len(parts) < 2 or parts[0] not in TYPE_PREFIXES:
        return None

    return "-".join(parts[1:])


def collection_label(key: str) -> str:
    """« volcan-2026 » → « 🌋 Volcan 2026 »."""
    parts = key.split("-")
    year = parts.pop() if len(parts) > 1 and parts[-1].isdigit() else None
    theme = "-".join(parts)
    emoji, name = THEMES.get(theme, ("", theme.replace("-", " ").capitalize()))
    label = f"{emoji} {name}".strip()

    return f"{label} {year}" if year else label


def build_collections(
    cosmetics: list,
    owned_ids: set[int],
) -> list[Collection]:
    groups: dict[str, list] = {}

    for cosmetic in cosmetics:
        key = collection_key(str(cosmetic["identifier"]))

        if key is not None:
            groups.setdefault(key, []).append(cosmetic)

    collections = []

    for key, members in groups.items():
        if len(members) < 2:
            continue

        members.sort(
            key=lambda cosmetic: (
                TYPE_ORDER.index(cosmetic["cosmetic_type"])
                if cosmetic["cosmetic_type"] in TYPE_ORDER
                else len(TYPE_ORDER),
                str(cosmetic["display_name"]),
            )
        )
        collections.append(
            Collection(
                key=key,
                label=collection_label(key),
                items=tuple(
                    CollectionItem(
                        name=str(cosmetic["display_name"]),
                        cosmetic_type=str(cosmetic["cosmetic_type"]),
                        owned=int(cosmetic["id"]) in owned_ids,
                    )
                    for cosmetic in members
                ),
            )
        )

    # Collections terminées en premier, puis les plus avancées.
    collections.sort(
        key=lambda collection: (
            not collection.complete,
            -collection.owned / len(collection.items),
            collection.label,
        )
    )

    return collections


def server_emoji(guild: discord.Guild | None, name: str, fallback: str) -> str:
    if guild is not None:
        emoji = discord.utils.get(guild.emojis, name=name)

        if emoji is not None and emoji.is_usable():
            return str(emoji)

    return fallback


def build_collections_embed(
    collections: list[Collection],
    *,
    member_name: str,
    yes: str = "✅",
    no: str = "❌",
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📚 Collections de {member_name}",
        color=COLLECTION_COLOR,
    )

    if not collections:
        embed.description = (
            "Aucune collection n'est disponible pour le moment."
        )
        return embed

    complete = sum(1 for collection in collections if collection.complete)
    embed.description = (
        f"Collections complètes : **{complete}/{len(collections)}**\n"
        "Obtiens tous les cosmétiques d'un thème pour compléter sa collection."
    )

    for collection in collections[:25]:
        items = "\n".join(
            f"{yes if item.owned else no} {item.name}"
            for item in collection.items
        )
        embed.add_field(
            name=(
                f"{collection.label} — {collection.owned}/{len(collection.items)} "
                f"{yes if collection.complete else no}"
            ),
            value=items[:1024],
            inline=True,
        )

    return embed


class CollectionCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("Le gestionnaire PostgreSQL est indisponible.")

        return database.require_pool()

    async def build_embed(
        self,
        guild: discord.Guild,
        member: discord.abc.User,
    ) -> discord.Embed:
        pool = self.get_pool()
        cosmetics = await pool.fetch(
            """
            SELECT id, identifier, cosmetic_type, display_name
            FROM profile_cosmetics
            WHERE guild_id = $1
              AND enabled = TRUE
            """,
            guild.id,
        )
        owned = await pool.fetch(
            """
            SELECT cosmetic_id
            FROM profile_inventory
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild.id,
            member.id,
        )

        return build_collections_embed(
            build_collections(
                list(cosmetics),
                {int(row["cosmetic_id"]) for row in owned},
            ),
            member_name=member.display_name,
            yes=server_emoji(guild, YES_EMOJI_NAME, "✅"),
            no=server_emoji(guild, NO_EMOJI_NAME, "❌"),
        )

    async def send_collections(
        self,
        interaction: discord.Interaction,
        member: discord.abc.User,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            embed = await self.build_embed(guild, member)
        except Exception:
            LOGGER.exception("Collections de %s indisponibles", member.id)
            await interaction.followup.send(
                "❌ Les collections n'ont pas pu être chargées. Réessaie plus tard.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="collections",
        description="Affiche tes collections de cosmétiques ou celles d'un membre.",
    )
    @app_commands.rename(member="membre")
    @app_commands.describe(member="Membre dont tu veux voir les collections.")
    @app_commands.guild_only()
    async def collections(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        await self.send_collections(interaction, member or interaction.user)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CollectionCog(bot))
    LOGGER.info("Commande /collections chargée")
