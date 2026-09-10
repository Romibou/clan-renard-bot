from __future__ import annotations

import logging
import math
import re
from typing import Any, Literal

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)

SHOP_COLOR = discord.Color.from_rgb(115, 92, 255)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
WARNING_COLOR = discord.Color.from_rgb(235, 174, 65)

IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9_-]{1,50}$")

ShopItemType = Literal["role", "cosmetic"]


# ============================================================
# OUTILS
# ============================================================


def success_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=SUCCESS_COLOR,
    )


def error_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=ERROR_COLOR,
    )


def warning_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=WARNING_COLOR,
    )


def format_coins(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def level_from_xp(total_xp: int) -> int:
    """
    Doit correspondre à la formule utilisée par progression.py.
    """
    return math.isqrt(max(0, total_xp) // 100)


async def send_ephemeral(
    interaction: discord.Interaction,
    *,
    embed: discord.Embed,
    view: discord.ui.View | None = None,
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(
            embed=embed,
            view=view,
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )


# ============================================================
# BOUTIQUE MEMBRE
# ============================================================


class ShopItemSelect(discord.ui.Select):
    def __init__(self, shop_view: PermanentShopView) -> None:
        self.shop_view = shop_view

        super().__init__(
            placeholder="Choisis un article…",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Chargement…",
                    value="loading",
                )
            ],
            row=0,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.values:
            return

        self.shop_view.selected_identifier = self.values[0]

        try:
            (
                embed,
                items,
                purchased_item_ids,
                wallet,
                level,
            ) = await self.shop_view.cog.build_shop(
                guild_id=self.shop_view.guild_id,
                user_id=self.shop_view.owner_id,
                selected_identifier=self.shop_view.selected_identifier,
            )

            self.shop_view.update_components(
                items=items,
                purchased_item_ids=purchased_item_ids,
                wallet=wallet,
                level=level,
            )

            await interaction.response.edit_message(
                embed=embed,
                view=self.shop_view,
            )
        except Exception:
            LOGGER.exception(
                "Impossible d'actualiser la sélection de la boutique"
            )

            await send_ephemeral(
                interaction,
                embed=error_embed(
                    "Boutique indisponible",
                    "Impossible d'afficher cet article.",
                ),
            )


class ShopBuyButton(discord.ui.Button):
    def __init__(self, shop_view: PermanentShopView) -> None:
        self.shop_view = shop_view

        super().__init__(
            label="Acheter",
            emoji="🛒",
            style=discord.ButtonStyle.success,
            row=1,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await self.shop_view.buy(interaction)


class ShopRefreshButton(discord.ui.Button):
    def __init__(self, shop_view: PermanentShopView) -> None:
        self.shop_view = shop_view

        super().__init__(
            label="Actualiser",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await self.shop_view.refresh(interaction)


class PermanentShopView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: PermanentShop,
        owner_id: int,
        guild_id: int,
        selected_identifier: str | None = None,
    ) -> None:
        super().__init__(timeout=600)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.selected_identifier = selected_identifier

        self.item_select = ShopItemSelect(self)
        self.buy_button = ShopBuyButton(self)
        self.refresh_button = ShopRefreshButton(self)

        self.add_item(self.item_select)
        self.add_item(self.buy_button)
        self.add_item(self.refresh_button)

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Boutique personnelle",
                (
                    "Cette boutique appartient à un autre membre.\n"
                    "Utilise `/boutique` pour ouvrir la tienne."
                ),
            ),
            ephemeral=True,
        )
        return False

    def update_components(
        self,
        *,
        items: list[Any],
        purchased_item_ids: set[int],
        wallet: int,
        level: int,
    ) -> None:
        if not items:
            self.item_select.options = [
                discord.SelectOption(
                    label="Boutique vide",
                    value="none",
                    description="Aucun article disponible.",
                )
            ]
            self.item_select.disabled = True
            self.buy_button.disabled = True
            return

        identifiers = {
            str(item["identifier"])
            for item in items
        }

        if self.selected_identifier not in identifiers:
            self.selected_identifier = str(
                items[0]["identifier"]
            )

        options: list[discord.SelectOption] = []

        for item in items[:25]:
            item_id = int(item["id"])
            price = int(item["price"])
            minimum_level = int(item["minimum_level"])
            item_type = str(item["item_type"])

            if item_id in purchased_item_ids:
                status = "✅ Possédé"
            elif level < minimum_level:
                status = f"🔒 Niveau {minimum_level}"
            elif wallet < price:
                status = "❌ Pièces insuffisantes"
            else:
                status = "✨ Disponible"

            emoji = "🎭" if item_type == "role" else "🎨"

            options.append(
                discord.SelectOption(
                    label=str(item["display_name"])[:100],
                    value=str(item["identifier"])[:100],
                    description=(
                        f"{format_coins(price)} pièces • "
                        f"{status}"
                    )[:100],
                    emoji=emoji,
                    default=(
                        str(item["identifier"])
                        == self.selected_identifier
                    ),
                )
            )

        self.item_select.options = options
        self.item_select.disabled = False

        selected_item = next(
            (
                item
                for item in items
                if str(item["identifier"])
                == self.selected_identifier
            ),
            None,
        )

        if selected_item is None:
            self.buy_button.disabled = True
            return

        item_id = int(selected_item["id"])
        price = int(selected_item["price"])
        minimum_level = int(
            selected_item["minimum_level"]
        )

        already_purchased = item_id in purchased_item_ids

        self.buy_button.disabled = (
            already_purchased
            or wallet < price
            or level < minimum_level
        )

        if already_purchased:
            self.buy_button.label = "Déjà possédé"
            self.buy_button.emoji = "✅"
        elif level < minimum_level:
            self.buy_button.label = "Niveau insuffisant"
            self.buy_button.emoji = "🔒"
        elif wallet < price:
            self.buy_button.label = "Solde insuffisant"
            self.buy_button.emoji = "❌"
        else:
            self.buy_button.label = "Acheter"
            self.buy_button.emoji = "🛒"

    async def refresh(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer()

        try:
            (
                embed,
                items,
                purchased_item_ids,
                wallet,
                level,
            ) = await self.cog.build_shop(
                guild_id=self.guild_id,
                user_id=self.owner_id,
                selected_identifier=self.selected_identifier,
            )

            self.update_components(
                items=items,
                purchased_item_ids=purchased_item_ids,
                wallet=wallet,
                level=level,
            )

            await interaction.edit_original_response(
                embed=embed,
                view=self,
            )
        except Exception:
            LOGGER.exception(
                "Impossible d'actualiser la boutique"
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Boutique indisponible",
                    "Impossible d'actualiser la boutique.",
                ),
                ephemeral=True,
            )

    async def buy(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.selected_identifier:
            await interaction.response.send_message(
                embed=error_embed(
                    "Aucun article",
                    "Choisis d'abord un article.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        try:
            result = await self.cog.purchase_item(
                interaction=interaction,
                identifier=self.selected_identifier,
            )

            (
                shop_embed,
                items,
                purchased_item_ids,
                wallet,
                level,
            ) = await self.cog.build_shop(
                guild_id=self.guild_id,
                user_id=self.owner_id,
                selected_identifier=self.selected_identifier,
            )

            self.update_components(
                items=items,
                purchased_item_ids=purchased_item_ids,
                wallet=wallet,
                level=level,
            )

            if interaction.message is not None:
                await interaction.message.edit(
                    embed=shop_embed,
                    view=self,
                )

            await interaction.followup.send(
                embed=result,
                ephemeral=True,
            )
        except Exception:
            LOGGER.exception(
                "Erreur pendant un achat"
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Achat impossible",
                    "Une erreur inattendue s'est produite.",
                ),
                ephemeral=True,
            )


# ============================================================
# MODAL DE CONFIGURATION
# ============================================================


class ShopItemModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        cog: PermanentShop,
        item_type: ShopItemType,
        role_id: int | None = None,
        cosmetic_id: int | None = None,
        default_identifier: str = "",
        default_name: str = "",
        default_description: str = "",
    ) -> None:
        title = (
            "Ajouter un rôle"
            if item_type == "role"
            else "Ajouter un cosmétique"
        )

        super().__init__(
            title=title,
            timeout=300,
        )

        self.cog = cog
        self.item_type = item_type
        self.role_id = role_id
        self.cosmetic_id = cosmetic_id

        self.identifier_input = discord.ui.TextInput(
            label="Identifiant",
            placeholder="exemple: role-vip",
            default=default_identifier[:50] or None,
            min_length=1,
            max_length=50,
        )

        self.name_input = discord.ui.TextInput(
            label="Nom affiché",
            placeholder="Exemple : Rôle VIP",
            default=default_name[:100] or None,
            min_length=1,
            max_length=100,
        )

        self.price_input = discord.ui.TextInput(
            label="Prix en pièces",
            placeholder="Exemple : 500",
            default="500",
            min_length=1,
            max_length=10,
        )

        self.level_input = discord.ui.TextInput(
            label="Niveau minimum",
            placeholder="Exemple : 5",
            default="0",
            min_length=1,
            max_length=5,
        )

        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Description affichée dans la boutique",
            default=default_description[:1000] or None,
            required=False,
            max_length=1000,
            style=discord.TextStyle.paragraph,
        )

        self.add_item(self.identifier_input)
        self.add_item(self.name_input)
        self.add_item(self.price_input)
        self.add_item(self.level_input)
        self.add_item(self.description_input)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            price = int(self.price_input.value)
            minimum_level = int(self.level_input.value)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    (
                        "Le prix et le niveau minimum doivent "
                        "être des nombres entiers."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        result = await self.cog.configure_item(
            interaction=interaction,
            identifier=self.identifier_input.value,
            display_name=self.name_input.value,
            description=self.description_input.value,
            price=price,
            minimum_level=minimum_level,
            item_type=self.item_type,
            role_id=self.role_id,
            cosmetic_id=self.cosmetic_id,
        )

        await interaction.followup.send(
            embed=result,
            ephemeral=True,
        )


class DeleteShopItemModal(discord.ui.Modal):
    identifier_input = discord.ui.TextInput(
        label="Identifiant de l'article",
        placeholder="Exemple : role-vip",
        min_length=1,
        max_length=50,
    )

    def __init__(
        self,
        *,
        cog: PermanentShop,
    ) -> None:
        super().__init__(
            title="Supprimer un article",
            timeout=300,
        )
        self.cog = cog

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        result = await self.cog.delete_item(
            guild_id=interaction.guild_id,
            identifier=self.identifier_input.value,
        )

        await interaction.followup.send(
            embed=result,
            ephemeral=True,
        )


# ============================================================
# SÉLECTEUR DE RÔLE ADMIN
# ============================================================


class ShopRoleSelect(discord.ui.RoleSelect):
    def __init__(
        self,
        *,
        cog: PermanentShop,
    ) -> None:
        super().__init__(
            placeholder="Choisis le rôle à vendre…",
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None or not self.values:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur introuvable",
                    "Impossible de retrouver le serveur.",
                ),
                ephemeral=True,
            )
            return

        selected = self.values[0]
        role = guild.get_role(selected.id)

        if role is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Rôle introuvable",
                    "Le rôle sélectionné n'existe plus.",
                ),
                ephemeral=True,
            )
            return

        if role.is_default() or role.managed:
            await interaction.response.send_message(
                embed=error_embed(
                    "Rôle invalide",
                    "Ce rôle ne peut pas être attribué par le bot.",
                ),
                ephemeral=True,
            )
            return

        bot_member = guild.me

        if bot_member is None or role >= bot_member.top_role:
            await interaction.response.send_message(
                embed=error_embed(
                    "Hiérarchie incorrecte",
                    (
                        f"Place le rôle principal du bot "
                        f"au-dessus de {role.mention}."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            ShopItemModal(
                cog=self.cog,
                item_type="role",
                role_id=role.id,
                default_name=role.name,
                default_description=(
                    f"Débloque le rôle {role.name}."
                ),
            )
        )


class ShopRoleSelectView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: PermanentShop,
        owner_id: int,
    ) -> None:
        super().__init__(timeout=300)
        self.owner_id = owner_id

        self.add_item(
            ShopRoleSelect(cog=cog)
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        return interaction.user.id == self.owner_id


# ============================================================
# SÉLECTEUR DE COSMÉTIQUE ADMIN
# ============================================================


class ShopCosmeticSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        cog: PermanentShop,
        cosmetics: list[Any],
    ) -> None:
        self.cog = cog
        self.cosmetics = cosmetics

        options: list[discord.SelectOption] = []

        emoji_by_type = {
            "title": "🏷️",
            "badge": "🎖️",
            "background": "🖼️",
            "frame": "🪞",
            "effect": "✨",
        }

        for cosmetic in cosmetics[:25]:
            cosmetic_type = str(
                cosmetic["cosmetic_type"]
            )

            options.append(
                discord.SelectOption(
                    label=str(
                        cosmetic["display_name"]
                    )[:100],
                    value=str(cosmetic["id"]),
                    description=(
                        f"{cosmetic_type} • "
                        f"{cosmetic['identifier']}"
                    )[:100],
                    emoji=emoji_by_type.get(
                        cosmetic_type,
                        "🎨",
                    ),
                )
            )

        super().__init__(
            placeholder="Choisis le cosmétique à vendre…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            cosmetic_id = int(self.values[0])
        except (ValueError, IndexError):
            await interaction.response.send_message(
                embed=error_embed(
                    "Cosmétique invalide",
                    "La sélection est invalide.",
                ),
                ephemeral=True,
            )
            return

        cosmetic = next(
            (
                item
                for item in self.cosmetics
                if int(item["id"]) == cosmetic_id
            ),
            None,
        )

        if cosmetic is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Cosmétique introuvable",
                    "Ce cosmétique n'existe plus.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            ShopItemModal(
                cog=self.cog,
                item_type="cosmetic",
                cosmetic_id=cosmetic_id,
                default_identifier=str(
                    cosmetic["identifier"]
                ),
                default_name=str(
                    cosmetic["display_name"]
                ),
                default_description=str(
                    cosmetic["description"] or ""
                ),
            )
        )


class ShopCosmeticSelectView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: PermanentShop,
        owner_id: int,
        cosmetics: list[Any],
    ) -> None:
        super().__init__(timeout=300)
        self.owner_id = owner_id

        self.add_item(
            ShopCosmeticSelect(
                cog=cog,
                cosmetics=cosmetics,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        return interaction.user.id == self.owner_id


# ============================================================
# PANNEAU ADMINISTRATIF
# ============================================================


class ShopAdminView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: PermanentShop,
        owner_id: int,
    ) -> None:
        super().__init__(timeout=600)

        self.cog = cog
        self.owner_id = owner_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Panneau personnel",
                "Ce panneau appartient à un autre administrateur.",
            ),
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="Ajouter un rôle",
        emoji="🎭",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def add_role(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎭 Ajouter un rôle",
                description=(
                    "Choisis le rôle qui sera vendu "
                    "dans la boutique."
                ),
                color=SHOP_COLOR,
            ),
            view=ShopRoleSelectView(
                cog=self.cog,
                owner_id=interaction.user.id,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Ajouter un cosmétique",
        emoji="🎨",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def add_cosmetic(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur introuvable",
                    "Cette action nécessite un serveur.",
                ),
                ephemeral=True,
            )
            return

        cosmetics = await self.cog.get_cosmetics(
            interaction.guild_id
        )

        if not cosmetics:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Aucun cosmétique",
                    (
                        "Crée d'abord un cosmétique depuis "
                        "le panneau administratif du profil."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎨 Ajouter un cosmétique",
                description=(
                    "Choisis un cosmétique déjà enregistré "
                    "dans le système de profil."
                ),
                color=SHOP_COLOR,
            ),
            view=ShopCosmeticSelectView(
                cog=self.cog,
                owner_id=interaction.user.id,
                cosmetics=cosmetics,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Liste",
        emoji="📋",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def list_items(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild_id is None:
            return

        embed = await self.cog.build_admin_list(
            interaction.guild_id
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Supprimer",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=1,
    )
    async def delete_item(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            DeleteShopItemModal(
                cog=self.cog,
            )
        )


# ============================================================
# COG PRINCIPAL
# ============================================================


class PermanentShop(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    def get_pool(self):
        database = getattr(
            self.bot,
            "database",
            None,
        )

        if database is None:
            raise RuntimeError(
                "La base de données est indisponible."
            )

        return database.require_pool()

    async def initialize_database(self) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS permanent_shop_items (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                identifier VARCHAR(50) NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                description VARCHAR(1000) NOT NULL DEFAULT '',
                item_type VARCHAR(20) NOT NULL
                    CHECK (
                        item_type IN (
                            'role',
                            'cosmetic'
                        )
                    ),
                role_id BIGINT,
                cosmetic_id BIGINT,
                price INTEGER NOT NULL
                    CHECK (price >= 0),
                minimum_level INTEGER NOT NULL DEFAULT 0
                    CHECK (minimum_level >= 0),
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                UNIQUE (guild_id, identifier),

                CHECK (
                    (
                        item_type = 'role'
                        AND role_id IS NOT NULL
                        AND cosmetic_id IS NULL
                    )
                    OR
                    (
                        item_type = 'cosmetic'
                        AND cosmetic_id IS NOT NULL
                        AND role_id IS NULL
                    )
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS permanent_shop_purchases (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                item_id BIGINT NOT NULL
                    REFERENCES permanent_shop_items(id)
                    ON DELETE RESTRICT,
                identifier VARCHAR(50) NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                item_type VARCHAR(20) NOT NULL,
                price INTEGER NOT NULL
                    CHECK (price >= 0),
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (
                        status IN (
                            'pending',
                            'completed',
                            'failed'
                        )
                    ),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ,

                UNIQUE (item_id, user_id)
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS
                permanent_shop_items_guild_idx
            ON permanent_shop_items (
                guild_id,
                enabled
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS
                permanent_shop_purchases_user_idx
            ON permanent_shop_purchases (
                guild_id,
                user_id,
                status
            )
            """
        )

        LOGGER.info(
            "Tables de la boutique permanente vérifiées"
        )

    async def get_member_progression(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> tuple[int, int]:
        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                total_xp,
                wallet
            FROM progression_members
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )

        if record is None:
            return 0, 0

        total_xp = int(record["total_xp"] or 0)
        wallet = int(record["wallet"] or 0)

        return level_from_xp(total_xp), wallet

    async def get_items(
        self,
        guild_id: int,
    ) -> list[Any]:
        pool = self.get_pool()

        records = await pool.fetch(
            """
            SELECT
                id,
                guild_id,
                identifier,
                display_name,
                description,
                item_type,
                role_id,
                cosmetic_id,
                price,
                minimum_level,
                enabled
            FROM permanent_shop_items
            WHERE guild_id = $1
              AND enabled = TRUE
            ORDER BY
                price ASC,
                display_name ASC
            LIMIT 25
            """,
            guild_id,
        )

        return list(records)

    async def get_purchased_item_ids(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> set[int]:
        pool = self.get_pool()

        records = await pool.fetch(
            """
            SELECT item_id
            FROM permanent_shop_purchases
            WHERE guild_id = $1
              AND user_id = $2
              AND status = 'completed'
            """,
            guild_id,
            user_id,
        )

        return {
            int(record["item_id"])
            for record in records
        }

    async def get_cosmetics(
        self,
        guild_id: int,
    ) -> list[Any]:
        pool = self.get_pool()

        records = await pool.fetch(
            """
            SELECT
                id,
                identifier,
                cosmetic_type,
                display_name,
                description,
                asset_path,
                value
            FROM profile_cosmetics
            WHERE guild_id = $1
              AND enabled = TRUE
            ORDER BY
                cosmetic_type,
                display_name
            LIMIT 25
            """,
            guild_id,
        )

        return list(records)

    async def build_shop(
        self,
        *,
        guild_id: int,
        user_id: int,
        selected_identifier: str | None,
    ) -> tuple[
        discord.Embed,
        list[Any],
        set[int],
        int,
        int,
    ]:
        items = await self.get_items(guild_id)

        purchased_item_ids = await self.get_purchased_item_ids(
            guild_id=guild_id,
            user_id=user_id,
        )

        level, wallet = await self.get_member_progression(
            guild_id=guild_id,
            user_id=user_id,
        )

        selected_item = None

        if selected_identifier:
            selected_item = next(
                (
                    item
                    for item in items
                    if str(item["identifier"])
                    == selected_identifier
                ),
                None,
            )

        if selected_item is None and items:
            selected_item = items[0]

        embed = discord.Embed(
            title="🛍️ Boutique du serveur",
            description=(
                "Dépense tes pièces pour obtenir des rôles "
                "et des cosmétiques permanents.\n\n"
                "Les achats de cette boutique ne sont pas "
                "limités au calendrier de l'Avent."
            ),
            color=SHOP_COLOR,
        )

        embed.add_field(
            name="🪙 Ton solde",
            value=f"**{format_coins(wallet)} pièces**",
            inline=True,
        )
        embed.add_field(
            name="⭐ Ton niveau",
            value=f"**Niveau {level}**",
            inline=True,
        )
        embed.add_field(
            name="🛒 Achats",
            value=f"**{len(purchased_item_ids)}**",
            inline=True,
        )

        if not items:
            embed.add_field(
                name="Boutique vide",
                value=(
                    "Aucun article n'est actuellement disponible."
                ),
                inline=False,
            )

        elif selected_item is not None:
            item_id = int(selected_item["id"])
            price = int(selected_item["price"])
            minimum_level = int(
                selected_item["minimum_level"]
            )
            item_type = str(
                selected_item["item_type"]
            )

            if item_id in purchased_item_ids:
                status = "✅ Tu possèdes déjà cet article."
            elif level < minimum_level:
                status = (
                    f"🔒 Niveau **{minimum_level}** requis."
                )
            elif wallet < price:
                missing = price - wallet
                status = (
                    f"❌ Il te manque "
                    f"**{format_coins(missing)} pièce(s)**."
                )
            else:
                status = "✨ Cet article peut être acheté."

            type_text = (
                "Rôle Discord"
                if item_type == "role"
                else "Cosmétique de profil"
            )

            target_text = "Indisponible"

            if item_type == "role":
                target_text = (
                    f"<@&{selected_item['role_id']}>"
                )
            else:
                pool = self.get_pool()

                cosmetic = await pool.fetchrow(
                    """
                    SELECT
                        display_name,
                        cosmetic_type
                    FROM profile_cosmetics
                    WHERE id = $1
                      AND guild_id = $2
                    """,
                    int(selected_item["cosmetic_id"]),
                    guild_id,
                )

                if cosmetic is not None:
                    target_text = (
                        f"**{cosmetic['display_name']}** "
                        f"(`{cosmetic['cosmetic_type']}`)"
                    )

            embed.add_field(
                name=str(
                    selected_item["display_name"]
                )[:256],
                value=(
                    str(selected_item["description"]).strip()
                    or "Aucune description."
                ),
                inline=False,
            )
            embed.add_field(
                name="Type",
                value=type_text,
                inline=True,
            )
            embed.add_field(
                name="Prix",
                value=(
                    f"**{format_coins(price)} pièces**"
                ),
                inline=True,
            )
            embed.add_field(
                name="Niveau minimum",
                value=f"**{minimum_level}**",
                inline=True,
            )
            embed.add_field(
                name="Récompense",
                value=target_text,
                inline=False,
            )
            embed.add_field(
                name="État",
                value=status,
                inline=False,
            )

        embed.set_footer(
            text="Les achats validés sont définitifs."
        )

        return (
            embed,
            items,
            purchased_item_ids,
            wallet,
            level,
        )

    async def configure_item(
        self,
        *,
        interaction: discord.Interaction,
        identifier: str,
        display_name: str,
        description: str,
        price: int,
        minimum_level: int,
        item_type: ShopItemType,
        role_id: int | None,
        cosmetic_id: int | None,
    ) -> discord.Embed:
        guild = interaction.guild

        if guild is None:
            return error_embed(
                "Serveur introuvable",
                "Cette action nécessite un serveur.",
            )

        normalized_identifier = (
            identifier.strip().lower()
        )
        normalized_name = display_name.strip()
        normalized_description = description.strip()

        if not IDENTIFIER_PATTERN.fullmatch(
            normalized_identifier
        ):
            return error_embed(
                "Identifiant invalide",
                (
                    "Utilise uniquement des lettres minuscules, "
                    "des chiffres, `_` ou `-`."
                ),
            )

        if not normalized_name:
            return error_embed(
                "Nom invalide",
                "Le nom ne peut pas être vide.",
            )

        if price < 0 or price > 1_000_000_000:
            return error_embed(
                "Prix invalide",
                "Le prix doit être compris entre 0 et 1 milliard.",
            )

        if minimum_level < 0 or minimum_level > 100_000:
            return error_embed(
                "Niveau invalide",
                "Le niveau minimum est invalide.",
            )

        pool = self.get_pool()

        if item_type == "role":
            if role_id is None:
                return error_embed(
                    "Rôle invalide",
                    "Aucun rôle n'a été sélectionné.",
                )

            role = guild.get_role(role_id)

            if (
                role is None
                or role.is_default()
                or role.managed
            ):
                return error_embed(
                    "Rôle invalide",
                    "Ce rôle ne peut pas être distribué.",
                )

            bot_member = guild.me

            if (
                bot_member is None
                or role >= bot_member.top_role
            ):
                return error_embed(
                    "Hiérarchie incorrecte",
                    (
                        "Le rôle du bot doit être placé "
                        "au-dessus du rôle vendu."
                    ),
                )

            cosmetic_id = None

        else:
            if cosmetic_id is None:
                return error_embed(
                    "Cosmétique invalide",
                    "Aucun cosmétique n'a été sélectionné.",
                )

            cosmetic_exists = await pool.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM profile_cosmetics
                    WHERE id = $1
                      AND guild_id = $2
                      AND enabled = TRUE
                )
                """,
                cosmetic_id,
                guild.id,
            )

            if not cosmetic_exists:
                return error_embed(
                    "Cosmétique introuvable",
                    (
                        "Ce cosmétique n'existe plus ou "
                        "est désactivé."
                    ),
                )

            role_id = None

        await pool.execute(
            """
            INSERT INTO permanent_shop_items (
                guild_id,
                identifier,
                display_name,
                description,
                item_type,
                role_id,
                cosmetic_id,
                price,
                minimum_level,
                enabled,
                updated_at
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9,
                TRUE,
                NOW()
            )
            ON CONFLICT (
                guild_id,
                identifier
            )
            DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                item_type = EXCLUDED.item_type,
                role_id = EXCLUDED.role_id,
                cosmetic_id = EXCLUDED.cosmetic_id,
                price = EXCLUDED.price,
                minimum_level = EXCLUDED.minimum_level,
                enabled = TRUE,
                updated_at = NOW()
            """,
            guild.id,
            normalized_identifier,
            normalized_name,
            normalized_description,
            item_type,
            role_id,
            cosmetic_id,
            price,
            minimum_level,
        )

        return success_embed(
            "Article configuré",
            (
                f"**{normalized_name}** est maintenant disponible "
                "dans `/boutique`.\n\n"
                f"Identifiant : `{normalized_identifier}`\n"
                f"Prix : **{format_coins(price)} pièces**\n"
                f"Niveau minimum : **{minimum_level}**"
            ),
        )

    async def delete_item(
        self,
        *,
        guild_id: int | None,
        identifier: str,
    ) -> discord.Embed:
        if guild_id is None:
            return error_embed(
                "Serveur introuvable",
                "Cette action nécessite un serveur.",
            )

        normalized = identifier.strip().lower()
        pool = self.get_pool()

        deleted = await pool.fetchrow(
            """
            UPDATE permanent_shop_items
            SET
                enabled = FALSE,
                updated_at = NOW()
            WHERE guild_id = $1
              AND identifier = $2
              AND enabled = TRUE
            RETURNING display_name
            """,
            guild_id,
            normalized,
        )

        if deleted is None:
            return error_embed(
                "Article introuvable",
                (
                    f"Aucun article actif ne possède "
                    f"l'identifiant `{normalized}`."
                ),
            )

        return success_embed(
            "Article supprimé",
            (
                f"**{deleted['display_name']}** a été retiré "
                "de la boutique.\n\n"
                "Les membres qui l'avaient acheté conservent "
                "leur récompense."
            ),
        )

    async def build_admin_list(
        self,
        guild_id: int,
    ) -> discord.Embed:
        items = await self.get_items(guild_id)

        embed = discord.Embed(
            title="📋 Articles de la boutique",
            description=(
                f"**{len(items)} article(s)** actif(s)."
            ),
            color=SHOP_COLOR,
        )

        if not items:
            embed.add_field(
                name="Boutique vide",
                value="Aucun article configuré.",
                inline=False,
            )
            return embed

        lines: list[str] = []

        for item in items:
            emoji = (
                "🎭"
                if item["item_type"] == "role"
                else "🎨"
            )

            lines.append(
                f"{emoji} **{item['display_name']}**\n"
                f"`{item['identifier']}` • "
                f"{format_coins(int(item['price']))} pièces • "
                f"Niveau {int(item['minimum_level'])}"
            )

        embed.description = "\n\n".join(lines)[:4096]

        return embed

    async def purchase_item(
        self,
        *,
        interaction: discord.Interaction,
        identifier: str,
    ) -> discord.Embed:
        guild = interaction.guild

        if guild is None:
            return error_embed(
                "Serveur introuvable",
                "Cette action nécessite un serveur.",
            )

        if isinstance(interaction.user, discord.Member):
            member = interaction.user
        else:
            try:
                member = await guild.fetch_member(
                    interaction.user.id
                )
            except discord.HTTPException:
                return error_embed(
                    "Membre introuvable",
                    "Impossible de retrouver ton compte.",
                )

        pool = self.get_pool()
        normalized = identifier.strip().lower()

        item = await pool.fetchrow(
            """
            SELECT
                id,
                identifier,
                display_name,
                item_type,
                role_id,
                cosmetic_id,
                price,
                minimum_level
            FROM permanent_shop_items
            WHERE guild_id = $1
              AND identifier = $2
              AND enabled = TRUE
            """,
            guild.id,
            normalized,
        )

        if item is None:
            return error_embed(
                "Article introuvable",
                "Cet article n'est plus disponible.",
            )

        item_type = str(item["item_type"])
        item_id = int(item["id"])
        price = int(item["price"])
        minimum_level = int(item["minimum_level"])

        role: discord.Role | None = None

        if item_type == "role":
            role = guild.get_role(int(item["role_id"]))

            if role is None:
                return error_embed(
                    "Rôle introuvable",
                    "Le rôle associé a été supprimé.",
                )

            if role in member.roles:
                return warning_embed(
                    "Rôle déjà possédé",
                    (
                        f"Tu possèdes déjà {role.mention}.\n"
                        "Aucune pièce n'a été retirée."
                    ),
                )

            bot_member = guild.me

            if (
                bot_member is None
                or role.is_default()
                or role.managed
                or role >= bot_member.top_role
            ):
                return error_embed(
                    "Rôle indisponible",
                    "Le bot ne peut pas attribuer ce rôle.",
                )


        # Si l'achat est déjà terminé, on ne débite pas une
        # seconde fois. Pour un rôle retiré, on le restaure.
        existing_purchase = await pool.fetchrow(
            """
            SELECT
                id,
                status
            FROM permanent_shop_items
            WHERE item_id = $1
              AND user_id = $2
            """,
            int(item["id"]),
            member.id,
        )

        if (
            existing_purchase is not None
            and existing_purchase["status"] == "completed"
        ):
            if item_type == "role" and role is not None:
                if role in member.roles:
                    return warning_embed(
                        "Déjà acheté",
                        f"Tu possèdes déjà le rôle {role.mention}.",
                    )

                try:
                    await member.add_roles(
                        role,
                        reason=(
                            "Restauration d'un rôle acheté "
                            "dans la boutique"
                        ),
                    )
                except discord.HTTPException:
                    LOGGER.exception(
                        "Impossible de restaurer le rôle %s à %s",
                        role.id,
                        member.id,
                    )

                    return error_embed(
                        "Restauration impossible",
                        (
                            "Tu as déjà acheté cette récompense, "
                            "mais le bot ne parvient pas à te "
                            "rendre le rôle.\n\n"
                            "**Aucun point n'a été retiré.**"
                        ),
                    )

                return success_embed(
                    "Rôle restauré",
                    (
                        f"Ton rôle {role.mention} a été restauré.\n\n"
                        "**Aucun point supplémentaire n'a été "
                        "retiré.**"
                    ),
                )

            return warning_embed(
                "Déjà acheté",
                "Tu possèdes déjà cette récompense.",
            )

        

        
        purchase_id: int | None = None

        async with pool.acquire() as connection:
            async with connection.transaction():
                lock_key = (
                    f"permanent-shop:{guild.id}:{member.id}"
                )

                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1, 0)
                    )
                    """,
                    lock_key,
                )

                locked_item = await connection.fetchrow(
                    """
                    SELECT
                        id,
                        identifier,
                        display_name,
                        item_type,
                        role_id,
                        cosmetic_id,
                        price,
                        minimum_level
                    FROM permanent_shop_items
                    WHERE id = $1
                      AND guild_id = $2
                      AND enabled = TRUE
                    """,
                    item_id,
                    guild.id,
                )

                if locked_item is None:
                    return error_embed(
                        "Article indisponible",
                        "Cet article vient d'être retiré.",
                    )

                existing_purchase = await connection.fetchrow(
                    """
                    SELECT
                        id,
                        status
                    FROM permanent_shop_purchases
                    WHERE item_id = $1
                      AND user_id = $2
                    """,
                    item_id,
                    member.id,
                )

                if (
                    existing_purchase is not None
                    and existing_purchase["status"] in (
                        "pending",
                        "completed",
                    )
                ):
                    return warning_embed(
                        "Déjà acheté",
                        "Tu as déjà acheté cet article.",
                    )

                progression = await connection.fetchrow(
                    """
                    SELECT
                        total_xp,
                        wallet
                    FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    guild.id,
                    member.id,
                )

                total_xp = (
                    int(progression["total_xp"] or 0)
                    if progression is not None
                    else 0
                )
                wallet = (
                    int(progression["wallet"] or 0)
                    if progression is not None
                    else 0
                )
                level = level_from_xp(total_xp)

                if level < minimum_level:
                    return error_embed(
                        "Niveau insuffisant",
                        (
                            f"Cet article demande le niveau "
                            f"**{minimum_level}**.\n"
                            f"Tu es actuellement niveau **{level}**."
                        ),
                    )

                if wallet < price:
                    return error_embed(
                        "Solde insuffisant",
                        (
                            f"Cet article coûte "
                            f"**{format_coins(price)} pièces**.\n"
                            f"Ton solde est de "
                            f"**{format_coins(wallet)} pièces**."
                        ),
                    )

                if item_type == "cosmetic":
                    cosmetic_id = int(
                        locked_item["cosmetic_id"]
                    )

                    cosmetic = await connection.fetchrow(
                        """
                        SELECT
                            id,
                            display_name,
                            cosmetic_type
                        FROM profile_cosmetics
                        WHERE id = $1
                          AND guild_id = $2
                          AND enabled = TRUE
                        """,
                        cosmetic_id,
                        guild.id,
                    )

                    if cosmetic is None:
                        return error_embed(
                            "Cosmétique indisponible",
                            (
                                "Le cosmétique associé "
                                "n'existe plus."
                            ),
                        )

                    already_owned = await connection.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM profile_inventory
                            WHERE guild_id = $1
                              AND user_id = $2
                              AND cosmetic_id = $3
                        )
                        """,
                        guild.id,
                        member.id,
                        cosmetic_id,
                    )

                    if already_owned:
                        return warning_embed(
                            "Déjà possédé",
                            (
                                "Tu possèdes déjà ce cosmétique.\n"
                                "Aucune pièce n'a été retirée."
                            ),
                        )

                updated = await connection.execute(
                    """
                    UPDATE progression_members
                    SET
                        wallet = wallet - $3,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                      AND wallet >= $3
                    """,
                    guild.id,
                    member.id,
                    price,
                )

                if updated == "UPDATE 0":
                    return error_embed(
                        "Solde insuffisant",
                        "Ton solde vient de changer.",
                    )

                if existing_purchase is None:
                    purchase = await connection.fetchrow(
                        """
                        INSERT INTO permanent_shop_purchases (
                            guild_id,
                            user_id,
                            item_id,
                            identifier,
                            display_name,
                            item_type,
                            price,
                            status
                        )
                        VALUES (
                            $1,
                            $2,
                            $3,
                            $4,
                            $5,
                            $6,
                            $7,
                            $8
                        )
                        RETURNING id
                        """,
                        guild.id,
                        member.id,
                        item_id,
                        str(locked_item["identifier"]),
                        str(locked_item["display_name"]),
                        item_type,
                        price,
                        (
                            "completed"
                            if item_type == "cosmetic"
                            else "pending"
                        ),
                    )
                else:
                    purchase = await connection.fetchrow(
                        """
                        UPDATE permanent_shop_purchases
                        SET
                            identifier = $2,
                            display_name = $3,
                            item_type = $4,
                            price = $5,
                            status = $6,
                            created_at = NOW(),
                            completed_at = NULL
                        WHERE id = $1
                        RETURNING id
                        """,
                        int(existing_purchase["id"]),
                        str(locked_item["identifier"]),
                        str(locked_item["display_name"]),
                        item_type,
                        price,
                        (
                            "completed"
                            if item_type == "cosmetic"
                            else "pending"
                        ),
                    )

                purchase_id = int(purchase["id"])

                await connection.execute(
                    """
                    INSERT INTO progression_transactions (
                        guild_id,
                        user_id,
                        actor_id,
                        amount,
                        transaction_type,
                        reason
                    )
                    VALUES (
                        $1,
                        $2,
                        $2,
                        $3,
                        'shop_purchase',
                        $4
                    )
                    """,
                    guild.id,
                    member.id,
                    -price,
                    (
                        f"Achat boutique : "
                        f"{locked_item['display_name']}"
                    ),
                )

                if item_type == "cosmetic":
                    await connection.execute(
                        """
                        INSERT INTO profile_inventory (
                            guild_id,
                            user_id,
                            cosmetic_id,
                            source
                        )
                        VALUES (
                            $1,
                            $2,
                            $3,
                            'shop'
                        )
                        ON CONFLICT (
                            guild_id,
                            user_id,
                            cosmetic_id
                        )
                        DO NOTHING
                        """,
                        guild.id,
                        member.id,
                        int(locked_item["cosmetic_id"]),
                    )

                    await connection.execute(
                        """
                        UPDATE permanent_shop_purchases
                        SET
                            status = 'completed',
                            completed_at = NOW()
                        WHERE id = $1
                        """,
                        purchase_id,
                    )

        if item_type == "cosmetic":
            return success_embed(
                "Cosmétique acheté",
                (
                    f"Tu as obtenu **{item['display_name']}** !\n\n"
                    f"🪙 Prix : **{format_coins(price)} pièces**\n"
                    "Utilise `/profil` pour l'équiper."
                ),
            )

        if role is None or purchase_id is None:
            return error_embed(
                "Achat impossible",
                "La récompense est invalide.",
            )

        try:
            await member.add_roles(
                role,
                reason=(
                    f"Achat dans la boutique permanente : "
                    f"{item['display_name']}"
                ),
            )
        except discord.HTTPException:
            async with pool.acquire() as connection:
                async with connection.transaction():
                    refunded = await connection.fetchval(
                        """
                        UPDATE permanent_shop_purchases
                        SET status = 'failed'
                        WHERE id = $1
                          AND status = 'pending'
                        RETURNING price
                        """,
                        purchase_id,
                    )

                    if refunded is not None:
                        refund_amount = int(refunded)

                        await connection.execute(
                            """
                            UPDATE progression_members
                            SET
                                wallet = wallet + $3,
                                updated_at = NOW()
                            WHERE guild_id = $1
                              AND user_id = $2
                            """,
                            guild.id,
                            member.id,
                            refund_amount,
                        )

                        await connection.execute(
                            """
                            INSERT INTO progression_transactions (
                                guild_id,
                                user_id,
                                actor_id,
                                amount,
                                transaction_type,
                                reason
                            )
                            VALUES (
                                $1,
                                $2,
                                NULL,
                                $3,
                                'shop_refund',
                                $4
                            )
                            """,
                            guild.id,
                            member.id,
                            refund_amount,
                            (
                                f"Remboursement boutique : "
                                f"{item['display_name']}"
                            ),
                        )

            return error_embed(
                "Attribution impossible",
                (
                    "Le bot n'a pas réussi à attribuer le rôle.\n"
                    "**Tes pièces ont été remboursées.**"
                ),
            )

        await pool.execute(
            """
            UPDATE permanent_shop_purchases
            SET
                status = 'completed',
                completed_at = NOW()
            WHERE id = $1
              AND status = 'pending'
            """,
            purchase_id,
        )

        return success_embed(
            "Rôle acheté",
            (
                f"Tu as obtenu {role.mention} !\n\n"
                f"🪙 Prix : **{format_coins(price)} pièces**"
            ),
        )

    # ========================================================
    # COMMANDES
    # ========================================================

    @app_commands.command(
        name="boutique",
        description=(
            "Ouvre la boutique permanente du serveur."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        3.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def shop(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Serveur introuvable",
                    "Cette commande nécessite un serveur.",
                ),
                ephemeral=True,
            )
            return

        try:
            (
                embed,
                items,
                purchased_item_ids,
                wallet,
                level,
            ) = await self.build_shop(
                guild_id=guild.id,
                user_id=interaction.user.id,
                selected_identifier=None,
            )

            selected_identifier = (
                str(items[0]["identifier"])
                if items
                else None
            )

            view = PermanentShopView(
                cog=self,
                owner_id=interaction.user.id,
                guild_id=guild.id,
                selected_identifier=selected_identifier,
            )

            view.update_components(
                items=items,
                purchased_item_ids=purchased_item_ids,
                wallet=wallet,
                level=level,
            )

            await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True,
            )
        except Exception:
            LOGGER.exception(
                "Impossible d'ouvrir la boutique permanente"
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Boutique indisponible",
                    (
                        "Une erreur est survenue pendant "
                        "l'ouverture de la boutique."
                    ),
                ),
                ephemeral=True,
            )

    @app_commands.command(
        name="boutique-admin",
        description=(
            "Ouvre le panneau administratif de la boutique."
        ),
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def shop_admin(
        self,
        interaction: discord.Interaction,
    ) -> None:
        embed = discord.Embed(
            title="⚙️ Administration de la boutique",
            description=(
                "Configure les articles disponibles dans "
                "la boutique permanente.\n\n"
                "• **Ajouter un rôle** : vend un rôle Discord\n"
                "• **Ajouter un cosmétique** : vend un élément "
                "du profil\n"
                "• **Liste** : affiche les identifiants\n"
                "• **Supprimer** : retire un article de la boutique"
            ),
            color=SHOP_COLOR,
        )

        await interaction.response.send_message(
            embed=embed,
            view=ShopAdminView(
                cog=self,
                owner_id=interaction.user.id,
            ),
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    cog = PermanentShop(bot)

    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info(
        "Boutique permanente initialisée"
    )


async def teardown(
    bot: commands.Bot,
) -> None:
    await bot.remove_cog(
        "PermanentShop"
    )
