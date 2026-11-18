"""
Catalogue des cosmétiques pour les administrateurs (/profil-admin →
« Catalogue ») : tous les cosmétiques du bot, vendus ou non, rangés
par thème, avec leur nom affiché, leur ID et l'endroit où ils sont
vendus.

L'ID (#12) est celui à écrire dans une récompense aléatoire de l'Avent
({"cosmetic_id": 12}).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import discord

from bot.extensions.collection import TYPE_ORDER, collection_key, collection_label

LOGGER = logging.getLogger(__name__)

COLOR = discord.Color.from_rgb(226, 104, 161)
TYPE_EMOJIS = {"background": "🖼️", "frame": "🔲", "badge": "🏅", "effect": "✨", "title": "🏷️"}
OTHER_KEY = "~autres"
MAX_FIELD = 1024
MAX_EMBED = 5500
MAX_FIELDS = 25


@dataclass
class CatalogueItem:
    id: int
    identifier: str
    name: str
    cosmetic_type: str
    enabled: bool = True
    shop_price: int | None = None
    advent_price: int | None = None
    owners: int = 0


@dataclass
class Theme:
    key: str
    label: str
    items: list[CatalogueItem] = field(default_factory=list)


def format_number(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def item_line(item: CatalogueItem) -> str:
    """« `#12` 🖼️ **Fond d'hiver** · 💰 500 · 🎄 175 pts · 👥 3 »."""
    parts = [f"`#{item.id}` {TYPE_EMOJIS.get(item.cosmetic_type, '🎨')} **{item.name}**"]

    if item.shop_price is not None:
        parts.append(f"💰 {format_number(item.shop_price)}")
    if item.advent_price is not None:
        parts.append(f"🎄 {format_number(item.advent_price)} pts")
    if item.owners:
        parts.append(f"👥 {item.owners}")
    if not item.enabled:
        parts.append("🚫 désactivé")

    return " · ".join(parts)


def group_by_theme(items: list[CatalogueItem]) -> list[Theme]:
    themes: dict[str, Theme] = {}

    for item in items:
        key = collection_key(item.identifier) or OTHER_KEY
        label = "📦 Autres" if key == OTHER_KEY else collection_label(key)
        themes.setdefault(key, Theme(key=key, label=label)).items.append(item)

    for theme in themes.values():
        theme.items.sort(
            key=lambda item: (
                TYPE_ORDER.index(item.cosmetic_type) if item.cosmetic_type in TYPE_ORDER else len(TYPE_ORDER),
                item.name.lower(),
            )
        )

    # Thèmes par ordre alphabétique de leur identifiant, « Autres » à la fin.
    return sorted(themes.values(), key=lambda theme: (theme.key == OTHER_KEY, theme.key))


def theme_fields(theme: Theme) -> list[tuple[str, str]]:
    """Un thème peut prendre plusieurs champs s'il a beaucoup d'objets."""
    fields: list[tuple[str, str]] = []
    lines: list[str] = []
    title = f"{theme.label} — {len(theme.items)} objet(s)"

    for line in (item_line(item) for item in theme.items):
        if lines and len("\n".join([*lines, line])) > MAX_FIELD:
            fields.append((title if not fields else f"{theme.label} (suite)", "\n".join(lines)))
            lines = []
        lines.append(line[:MAX_FIELD])

    if lines:
        fields.append((title if not fields else f"{theme.label} (suite)", "\n".join(lines)))

    return fields


LEGEND = (
    "`#ID` à utiliser dans les récompenses aléatoires de l'Avent (`\"cosmetic_id\": 12`).\n"
    "🖼️ fond · 🔲 cadre · 🏅 badge · ✨ effet · 🏷️ titre\n"
    "💰 prix en boutique · 🎄 prix dans la boutique de l'Avent · 👥 membres qui l'ont"
)


def build_pages(themes: list[Theme], *, total: int) -> list[discord.Embed]:
    pages: list[discord.Embed] = []

    def new_page() -> discord.Embed:
        embed = discord.Embed(
            title="📚 Catalogue des cosmétiques",
            description=f"**{total}** cosmétique(s) dans **{len(themes)}** thème(s).\n\n{LEGEND}",
            color=COLOR,
        )
        pages.append(embed)
        return embed

    if not themes:
        embed = new_page()
        embed.description = "Aucun cosmétique pour le moment. Crée-en avec **➕ Créer un cosmétique**."
        return pages

    embed = new_page()

    for theme in themes:
        for name, value in theme_fields(theme):
            if len(embed.fields) >= MAX_FIELDS or len(embed) + len(name) + len(value) > MAX_EMBED:
                embed = new_page()

            embed.add_field(name=name, value=value, inline=False)

    for index, page in enumerate(pages, start=1):
        page.set_footer(text=f"Page {index}/{len(pages)} • visible par toi seul")

    return pages


class CataloguePager(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], owner_id: int) -> None:
        super().__init__(timeout=600)
        self.pages = pages
        self.owner_id = owner_id
        self.index = 0
        self.update_buttons()

    def update_buttons(self) -> None:
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index = max(0, self.index - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index = min(len(self.pages) - 1, self.index + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)


async def load_items(pool: Any, guild_id: int) -> list[CatalogueItem]:
    cosmetics = await pool.fetch(
        """
        SELECT id, identifier, cosmetic_type, display_name, enabled
        FROM profile_cosmetics
        WHERE guild_id = $1
        """,
        guild_id,
    )
    items = {
        int(row["id"]): CatalogueItem(
            id=int(row["id"]),
            identifier=str(row["identifier"]),
            name=str(row["display_name"]),
            cosmetic_type=str(row["cosmetic_type"]),
            enabled=bool(row["enabled"]),
        )
        for row in cosmetics
    }

    # Chaque source est facultative : une table absente n'empêche pas le catalogue.
    queries = (
        (
            "shop_price",
            """
            SELECT cosmetic_id, MIN(price) AS price
            FROM permanent_shop_items
            WHERE guild_id = $1 AND item_type = 'cosmetic' AND enabled = TRUE
            GROUP BY cosmetic_id
            """,
        ),
        (
            "advent_price",
            """
            SELECT DISTINCT ON (item.cosmetic_id) item.cosmetic_id, item.price
            FROM advent_shop_items_v2 AS item
            JOIN advent_campaigns AS campaign ON campaign.id = item.campaign_id
            WHERE item.guild_id = $1 AND item.cosmetic_id IS NOT NULL AND item.enabled = TRUE
            ORDER BY item.cosmetic_id, campaign.year DESC
            """,
        ),
        (
            "owners",
            """
            SELECT cosmetic_id, COUNT(*) AS price
            FROM profile_inventory
            WHERE guild_id = $1
            GROUP BY cosmetic_id
            """,
        ),
    )

    for attribute, query in queries:
        try:
            rows = await pool.fetch(query, guild_id)
        except Exception:
            LOGGER.warning("Catalogue : information « %s » indisponible", attribute, exc_info=True)
            continue

        for row in rows:
            item = items.get(int(row["cosmetic_id"]))

            if item is not None:
                setattr(item, attribute, int(row["price"]))

    return list(items.values())


async def send_catalogue(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        items = await load_items(interaction.client.database.require_pool(), interaction.guild_id)
    except Exception:
        LOGGER.exception("Catalogue des cosmétiques indisponible")
        await interaction.followup.send("❌ Le catalogue n'a pas pu être chargé. Réessaie plus tard.", ephemeral=True)
        return

    pages = build_pages(group_by_theme(items), total=len(items))
    kwargs: dict[str, Any] = {"embed": pages[0], "ephemeral": True}

    if len(pages) > 1:
        kwargs["view"] = CataloguePager(pages, interaction.user.id)

    await interaction.followup.send(**kwargs)

