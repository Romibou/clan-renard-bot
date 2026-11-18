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

OTHER_KEY = "~autres"


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



# Colonnes du tableau : (titre, largeur, aligné à droite).
COLUMNS = (
    ("ID", 4, False),
    ("Type", 5, False),
    ("Nom affiché", 22, False),
    ("Identifiant", 26, False),
    ("Prix", 6, True),
    ("Avent", 5, True),
    ("Nb", 3, True),
)
TYPE_NAMES = {"background": "Fond", "frame": "Cadre", "badge": "Badge", "effect": "Effet", "title": "Titre"}
MAX_MESSAGE = 1900  # un message fait 2 000 caractères au plus


def cell(text: str, width: int, right: bool) -> str:
    """Texte coupé ou complété avec des espaces pour tenir dans la colonne."""
    text = " ".join(str(text).split())

    if len(text) > width:
        text = text[: width - 1] + "…"

    return text.rjust(width) if right else text.ljust(width)


def table_row(values: list[str]) -> str:
    return " ".join(cell(value, width, right) for value, (_, width, right) in zip(values, COLUMNS)).rstrip()


TABLE_HEADER = table_row([title for title, _, _ in COLUMNS])


def item_row(item: CatalogueItem) -> str:
    """Une ligne alignée : ID, type, nom, identifiant, prix, prix Avent, membres."""
    name = item.name if item.enabled else f"[off] {item.name}"

    return table_row(
        [
            f"#{item.id}",
            TYPE_NAMES.get(item.cosmetic_type, item.cosmetic_type),
            name,
            item.identifier,
            format_number(item.shop_price) if item.shop_price is not None else "-",
            format_number(item.advent_price) if item.advent_price is not None else "-",
            str(item.owners),
        ]
    )


def theme_blocks(theme: Theme) -> list[str]:
    """Le titre du thème puis son tableau (coupé en plusieurs s'il est très long)."""
    blocks: list[str] = []
    rows: list[str] = []

    def flush(suffix: str = "") -> None:
        table = "\n".join([TABLE_HEADER, *rows])
        blocks.append(f"**{theme.label}** ({len(theme.items)}){suffix}\n```\n{table}\n```")

    for row in (item_row(item) for item in theme.items):
        if rows and len(TABLE_HEADER) + sum(len(r) + 1 for r in rows) + len(row) > MAX_MESSAGE - 200:
            flush(" — suite" if blocks else "")
            rows = []
        rows.append(row)

    if rows:
        flush(" — suite" if blocks else "")

    return blocks


LEGEND = (
    "-# **ID** : cases mystère de l'Avent (`\"cosmetic_id\": 12`) · **Identifiant** : boutique de l'Avent "
    "et distribution · **Prix** : boutique (pièces) · **Avent** : boutique de l'Avent (points) · "
    "**Nb** : membres qui l'ont · `[off]` : désactivé"
)


def build_pages(themes: list[Theme], *, total: int) -> list[str]:
    """Pages de texte (message normal, pleine largeur) avec un tableau par thème."""
    header = (
        f"### 📚 Catalogue des cosmétiques\n**{total}** cosmétique(s) dans **{len(themes)}** thème(s)\n{LEGEND}"
    )

    if not themes:
        return [
            "### 📚 Catalogue des cosmétiques\n"
            "Aucun cosmétique pour le moment. Crée-en avec **➕ Créer un cosmétique**."
        ]

    pages: list[str] = []
    current = header

    for theme in themes:
        for block in theme_blocks(theme):
            if len(current) + len(block) + 2 > MAX_MESSAGE:
                pages.append(current)
                current = block
            else:
                current = f"{current}\n\n{block}"

    pages.append(current)

    if len(pages) > 1:
        pages = [f"{page}\n-# Page {index}/{len(pages)}" for index, page in enumerate(pages, start=1)]

    return pages


class CataloguePager(discord.ui.View):
    def __init__(self, pages: list[str], owner_id: int) -> None:
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
        await interaction.response.edit_message(content=self.pages[self.index], view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index = min(len(self.pages) - 1, self.index + 1)
        self.update_buttons()
        await interaction.response.edit_message(content=self.pages[self.index], view=self)



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
    kwargs: dict[str, Any] = {"content": pages[0], "ephemeral": True}

    if len(pages) > 1:
        kwargs["view"] = CataloguePager(pages, interaction.user.id)

    await interaction.followup.send(**kwargs)

