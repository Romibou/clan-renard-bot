from __future__ import annotations

import logging
import os
import re
from datetime import date
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands


LOGGER = logging.getLogger(__name__)

SHOP_COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
WARNING_COLOR = discord.Color.from_rgb(235, 174, 65)

IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9_-]{1,50}$")


def success_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=SUCCESS_COLOR,
    )


def error_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=ERROR_COLOR,
    )


def warning_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=WARNING_COLOR,
    )


def format_points(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def get_current_year() -> int:
    test_date = os.getenv("ADVENT_TEST_DATE", "").strip()

    if test_date:
        try:
            return date.fromisoformat(test_date).year
        except ValueError:
            LOGGER.warning(
                "ADVENT_TEST_DATE est invalide : %s",
                test_date,
            )

    return date.today().year


def make_select_option(
    *,
    label: str,
    value: str,
    description: str,
    emoji: str | None,
    default: bool,
) -> discord.SelectOption:
    kwargs: dict[str, Any] = {
        "label": label[:100],
        "value": value[:100],
        "description": description[:100],
        "default": default,
    }

    if emoji:
        kwargs["emoji"] = emoji

    try:
        return discord.SelectOption(**kwargs)
    except (TypeError, ValueError):
        kwargs.pop("emoji", None)
        return discord.SelectOption(**kwargs)


class ShopProductSelect(discord.ui.Select):
    def __init__(self, shop_view: AdventShopView) -> None:
        self.shop_view = shop_view

        super().__init__(
            placeholder="Choisis une récompense…",
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

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.values:
            return

        self.shop_view.selected_identifier = self.values[0]
        await self.shop_view.refresh(interaction)


class ShopBuyButton(discord.ui.Button):
    def __init__(self, shop_view: AdventShopView) -> None:
        self.shop_view = shop_view

        super().__init__(
            label="Acheter",
            style=discord.ButtonStyle.success,
            emoji="🛒",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.shop_view.buy(interaction)


class ShopRefreshButton(discord.ui.Button):
    def __init__(self, shop_view: AdventShopView) -> None:
        self.shop_view = shop_view

        super().__init__(
            label="Actualiser",
            style=discord.ButtonStyle.secondary,
            emoji="🔄",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.shop_view.refresh(interaction)


class AdventShopView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: AdventShop,
        owner_id: int,
        guild_id: int,
        campaign_id: int,
        selected_identifier: str | None = None,
    ) -> None:
        super().__init__(timeout=600)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.campaign_id = campaign_id
        self.selected_identifier = selected_identifier

        self.product_select = ShopProductSelect(self)
        self.buy_button = ShopBuyButton(self)
        self.refresh_button = ShopRefreshButton(self)

        self.add_item(self.product_select)
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
                "Cette boutique appartient à un autre membre.\n"
                "Utilise `/avent-boutique` pour ouvrir la tienne.",
            ),
            ephemeral=True,
        )
        return False

    def update_components(
        self,
        *,
        items: list[Any],
        purchased_item_ids: set[int],
        balance: int,
        openings: int,
    ) -> None:
        if not items:
            self.product_select.options = [
                discord.SelectOption(
                    label="Aucune récompense",
                    value="none",
                    description="La boutique est vide.",
                )
            ]
            self.product_select.disabled = True
            self.buy_button.disabled = True
            return

        identifiers = {
            str(item["identifier"])
            for item in items
        }

        if self.selected_identifier not in identifiers:
            self.selected_identifier = str(items[0]["identifier"])

        options: list[discord.SelectOption] = []

        for item in items[:25]:
            item_id = int(item["id"])
            price = int(item["price"])
            minimum = int(item["min_openings"])

            if item_id in purchased_item_ids:
                status = "✅ Acheté"
            elif openings < minimum:
                status = f"🔒 {minimum} cases requises"
            elif balance < price:
                status = "❌ Solde insuffisant"
            else:
                status = "✨ Disponible"

            description = (
                f"{format_points(price)} pts • "
                f"{minimum} cases • {status}"
            )

            options.append(
                make_select_option(
                    label=str(item["display_name"]),
                    value=str(item["identifier"]),
                    description=description,
                    emoji=str(item["emoji"] or "🎁"),
                    default=(
                        str(item["identifier"])
                        == self.selected_identifier
                    ),
                )
            )

        self.product_select.options = options
        self.product_select.disabled = False

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

        already_purchased = (
            int(selected_item["id"]) in purchased_item_ids
        )

        can_afford = balance >= int(selected_item["price"])
        enough_openings = (
            openings >= int(selected_item["min_openings"])
        )

        self.buy_button.disabled = (
            already_purchased
            or not can_afford
            or not enough_openings
        )

        if already_purchased:
            self.buy_button.label = "Déjà acheté"
            self.buy_button.emoji = "✅"
        elif not enough_openings:
            self.buy_button.label = "Cases insuffisantes"
            self.buy_button.emoji = "🔒"
        elif not can_afford:
            self.buy_button.label = "Solde insuffisant"
            self.buy_button.emoji = "❌"
        else:
            self.buy_button.label = "Acheter"
            self.buy_button.emoji = "🛒"

    async def refresh(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            await interaction.response.defer()

            guild = interaction.guild

            if guild is None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Serveur introuvable",
                        "Cette action doit être utilisée dans un serveur.",
                    ),
                    ephemeral=True,
                )
                return

            (
                embed,
                items,
                purchased_item_ids,
                balance,
                openings,
            ) = await self.cog.build_shop(
                guild=guild,
                user_id=self.owner_id,
                campaign_id=self.campaign_id,
                selected_identifier=self.selected_identifier,
            )

            self.update_components(
                items=items,
                purchased_item_ids=purchased_item_ids,
                balance=balance,
                openings=openings,
            )

            await interaction.edit_original_response(
                embed=embed,
                view=self,
            )

        except Exception:
            LOGGER.exception(
                "Erreur pendant l'actualisation de la boutique"
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Erreur",
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
                    "Aucune récompense",
                    "Choisis d'abord une récompense.",
                ),
                ephemeral=True,
            )
            return

        try:
            await interaction.response.defer()

            result = await self.cog.purchase_item(
                interaction=interaction,
                campaign_id=self.campaign_id,
                identifier=self.selected_identifier,
            )

            guild = interaction.guild

            if guild is not None:
                (
                    shop_embed,
                    items,
                    purchased_item_ids,
                    balance,
                    openings,
                ) = await self.cog.build_shop(
                    guild=guild,
                    user_id=self.owner_id,
                    campaign_id=self.campaign_id,
                    selected_identifier=self.selected_identifier,
                )

                self.update_components(
                    items=items,
                    purchased_item_ids=purchased_item_ids,
                    balance=balance,
                    openings=openings,
                )

                await interaction.edit_original_response(
                    embed=shop_embed,
                    view=self,
                )

            await interaction.followup.send(
                embed=result,
                ephemeral=True,
            )

        except Exception:
            LOGGER.exception(
                "Erreur pendant un achat dans la boutique"
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Achat impossible",
                    "Une erreur inattendue s'est produite.",
                ),
                ephemeral=True,
            )


class AdventShop(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def get_pool(self):
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError(
                "Le gestionnaire de base de données est indisponible."
            )

        return database.require_pool()

    async def initialize_database(self) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS advent_shop_items_v2 (
                id BIGSERIAL PRIMARY KEY,
                campaign_id BIGINT NOT NULL
                    REFERENCES advent_campaigns(id)
                    ON DELETE CASCADE,
                guild_id BIGINT NOT NULL,
                identifier VARCHAR(50) NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                description VARCHAR(1000) NOT NULL DEFAULT '',
                emoji VARCHAR(100) NOT NULL DEFAULT '🎁',
                role_id BIGINT NOT NULL,
                price INTEGER NOT NULL CHECK (price >= 0),
                min_openings SMALLINT NOT NULL DEFAULT 0
                    CHECK (
                        min_openings >= 0
                        AND min_openings <= 24
                    ),
                success_message VARCHAR(1000) NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (campaign_id, identifier)
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS advent_shop_purchases_v2 (
                id BIGSERIAL PRIMARY KEY,
                campaign_id BIGINT NOT NULL
                    REFERENCES advent_campaigns(id)
                    ON DELETE CASCADE,
                item_id BIGINT NOT NULL
                    REFERENCES advent_shop_items_v2(id)
                    ON DELETE RESTRICT,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                item_name VARCHAR(100) NOT NULL,
                points_spent INTEGER NOT NULL
                    CHECK (points_spent >= 0),
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
                advent_shop_items_v2_campaign_idx
            ON advent_shop_items_v2 (
                campaign_id,
                enabled
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS
                advent_shop_purchases_v2_user_idx
            ON advent_shop_purchases_v2 (
                campaign_id,
                user_id,
                status
            )
            """
        )

        LOGGER.info("Tables de la boutique de l'Avent vérifiées")

    async def get_campaign(
        self,
        *,
        guild_id: int,
        year: int | None = None,
    ):
        pool = self.get_pool()

        requested_year = (
            year
            if year is not None
            else get_current_year()
        )

        campaign = await pool.fetchrow(
            """
            SELECT
                id,
                guild_id,
                year,
                title,
                enabled
            FROM advent_campaigns
            WHERE guild_id = $1
              AND year = $2
            ORDER BY id DESC
            LIMIT 1
            """,
            guild_id,
            requested_year,
        )

        if campaign is not None:
            return campaign

        return await pool.fetchrow(
            """
            SELECT
                id,
                guild_id,
                year,
                title,
                enabled
            FROM advent_campaigns
            WHERE guild_id = $1
            ORDER BY year DESC, id DESC
            LIMIT 1
            """,
            guild_id,
        )

    async def get_member_stats(
        self,
        *,
        campaign_id: int,
        user_id: int,
    ) -> tuple[int, int, int]:
        pool = self.get_pool()

        rewards = await pool.fetchrow(
            """
            SELECT
                COUNT(*)::INTEGER AS openings,
                COALESCE(
                    SUM(points_awarded),
                    0
                )::BIGINT AS total_points
            FROM advent_openings
            WHERE campaign_id = $1
              AND user_id = $2
            """,
            campaign_id,
            user_id,
        )

        spent = await pool.fetchval(
            """
            SELECT COALESCE(
                SUM(points_spent),
                0
            )::BIGINT
            FROM advent_shop_purchases_v2
            WHERE campaign_id = $1
              AND user_id = $2
              AND status IN ('pending', 'completed')
            """,
            campaign_id,
            user_id,
        )

        openings = int(rewards["openings"] or 0)
        total_points = int(rewards["total_points"] or 0)
        spent_points = int(spent or 0)

        balance = max(0, total_points - spent_points)

        return openings, total_points, balance

    async def get_shop_items(
        self,
        *,
        campaign_id: int,
    ) -> list[Any]:
        pool = self.get_pool()

        records = await pool.fetch(
            """
            SELECT
                id,
                campaign_id,
                guild_id,
                identifier,
                display_name,
                description,
                emoji,
                role_id,
                price,
                min_openings,
                success_message,
                enabled
            FROM advent_shop_items_v2
            WHERE campaign_id = $1
              AND enabled = TRUE
            ORDER BY price ASC, id ASC
            LIMIT 25
            """,
            campaign_id,
        )

        return list(records)

    async def get_purchased_item_ids(
        self,
        *,
        campaign_id: int,
        user_id: int,
    ) -> set[int]:
        pool = self.get_pool()

        records = await pool.fetch(
            """
            SELECT item_id
            FROM advent_shop_purchases_v2
            WHERE campaign_id = $1
              AND user_id = $2
              AND status = 'completed'
            """,
            campaign_id,
            user_id,
        )

        return {
            int(record["item_id"])
            for record in records
        }

    async def build_shop(
        self,
        *,
        guild: discord.Guild,
        user_id: int,
        campaign_id: int,
        selected_identifier: str | None,
    ) -> tuple[
        discord.Embed,
        list[Any],
        set[int],
        int,
        int,
    ]:
        pool = self.get_pool()

        campaign = await pool.fetchrow(
            """
            SELECT
                id,
                guild_id,
                year,
                title,
                enabled
            FROM advent_campaigns
            WHERE id = $1
              AND guild_id = $2
            """,
            campaign_id,
            guild.id,
        )

        if campaign is None:
            raise RuntimeError(
                "La campagne de l'Avent n'existe plus."
            )

        items = await self.get_shop_items(
            campaign_id=campaign_id,
        )

        purchased_item_ids = await self.get_purchased_item_ids(
            campaign_id=campaign_id,
            user_id=user_id,
        )

        openings, total_points, balance = (
            await self.get_member_stats(
                campaign_id=campaign_id,
                user_id=user_id,
            )
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
            title="🛍️ Boutique de l'Avent",
            description=(
                f"Bienvenue dans la boutique du **Clan Renard**.\n"
                f"Utilise le menu déroulant pour choisir une récompense."
            ),
            color=SHOP_COLOR,
        )

        embed.add_field(
            name="💰 Ton solde",
            value=f"**{format_points(balance)} points**",
            inline=True,
        )

        embed.add_field(
            name="🎁 Cases ouvertes",
            value=f"**{openings}/24**",
            inline=True,
        )

        embed.add_field(
            name="📊 Points gagnés",
            value=f"**{format_points(total_points)} points**",
            inline=True,
        )

        if not items:
            embed.add_field(
                name="Boutique vide",
                value=(
                    "Aucune récompense n'est actuellement "
                    "disponible."
                ),
                inline=False,
            )
        elif selected_item is not None:
            item_id = int(selected_item["id"])
            price = int(selected_item["price"])
            minimum = int(selected_item["min_openings"])
            role_id = int(selected_item["role_id"])

            description = (
                str(selected_item["description"]).strip()
                or "Aucune description."
            )

            if item_id in purchased_item_ids:
                status = "✅ Tu possèdes déjà cette récompense."
            elif openings < minimum:
                missing = minimum - openings
                status = (
                    f"🔒 Il te manque **{missing} case(s)** ouverte(s)."
                )
            elif balance < price:
                missing = price - balance
                status = (
                    f"❌ Il te manque **{format_points(missing)} "
                    f"point(s)**."
                )
            else:
                status = "✨ Cette récompense peut être achetée."

            embed.add_field(
                name=(
                    f"{selected_item['emoji']} "
                    f"{selected_item['display_name']}"
                ),
                value=description,
                inline=False,
            )

            embed.add_field(
                name="Prix",
                value=f"**{format_points(price)} points**",
                inline=True,
            )

            embed.add_field(
                name="Condition",
                value=f"**{minimum} cases ouvertes**",
                inline=True,
            )

            embed.add_field(
                name="Rôle obtenu",
                value=f"<@&{role_id}>",
                inline=True,
            )

            embed.add_field(
                name="État",
                value=status,
                inline=False,
            )

        embed.set_footer(
            text=(
                f"Calendrier {campaign['year']} • "
                "Les achats sont définitifs"
            )
        )

        return (
            embed,
            items,
            purchased_item_ids,
            balance,
            openings,
        )

    async def purchase_item(
        self,
        *,
        interaction: discord.Interaction,
        campaign_id: int,
        identifier: str,
    ) -> discord.Embed:
        guild = interaction.guild

        if guild is None:
            return error_embed(
                "Achat impossible",
                "Cette commande doit être utilisée dans un serveur.",
            )

        if not isinstance(interaction.user, discord.Member):
            try:
                member = await guild.fetch_member(
                    interaction.user.id
                )
            except discord.HTTPException:
                return error_embed(
                    "Membre introuvable",
                    "Impossible de retrouver ton compte sur le serveur.",
                )
        else:
            member = interaction.user

        pool = self.get_pool()

        item = await pool.fetchrow(
            """
            SELECT
                id,
                campaign_id,
                identifier,
                display_name,
                role_id,
                price,
                min_openings,
                success_message,
                enabled
            FROM advent_shop_items_v2
            WHERE campaign_id = $1
              AND identifier = $2
              AND enabled = TRUE
            """,
            campaign_id,
            identifier,
        )

        if item is None:
            return error_embed(
                "Récompense introuvable",
                "Cette récompense n'existe plus dans la boutique.",
            )

        role = guild.get_role(int(item["role_id"]))

        if role is None:
            return error_embed(
                "Rôle introuvable",
                "Le rôle associé à cette récompense a été supprimé.",
            )

        if role.is_default() or role.managed:
            return error_embed(
                "Rôle invalide",
                "Le bot ne peut pas attribuer ce rôle.",
            )

        bot_member = guild.me

        if bot_member is None:
            return error_embed(
                "Bot introuvable",
                "Impossible de vérifier les permissions du bot.",
            )

        if role >= bot_member.top_role:
            return error_embed(
                "Permissions insuffisantes",
                (
                    f"Le rôle {role.mention} se trouve au-dessus "
                    "du rôle principal du bot."
                ),
            )

        existing_purchase = await pool.fetchrow(
            """
            SELECT
                id,
                status
            FROM advent_shop_purchases_v2
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
            if role not in member.roles:
                try:
                    await member.add_roles(
                        role,
                        reason=(
                            "Restauration d'un achat de la "
                            "boutique de l'Avent"
                        ),
                    )
                except discord.HTTPException:
                    return error_embed(
                        "Rôle impossible à restaurer",
                        (
                            "Tu as déjà acheté cette récompense, "
                            "mais le bot ne parvient pas à te rendre "
                            "le rôle."
                        ),
                    )

                return success_embed(
                    "Rôle restauré",
                    (
                        f"Ton rôle {role.mention} a été restauré.\n"
                        "Aucun point supplémentaire n'a été retiré."
                    ),
                )

            return warning_embed(
                "Déjà acheté",
                f"Tu possèdes déjà {role.mention}.",
            )

        if role in member.roles:
            return warning_embed(
                "Rôle déjà possédé",
                (
                    f"Tu possèdes déjà {role.mention}.\n"
                    "Aucun point n'a été retiré."
                ),
            )

        purchase_id: int | None = None

        async with pool.acquire() as connection:
            async with connection.transaction():
                lock_key = f"advent-shop:{campaign_id}:{member.id}"

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
                        display_name,
                        role_id,
                        price,
                        min_openings,
                        success_message,
                        enabled
                    FROM advent_shop_items_v2
                    WHERE campaign_id = $1
                      AND identifier = $2
                      AND enabled = TRUE
                    """,
                    campaign_id,
                    identifier,
                )

                if locked_item is None:
                    return error_embed(
                        "Récompense indisponible",
                        "Cette récompense vient d'être retirée.",
                    )

                existing = await connection.fetchrow(
                    """
                    SELECT id, status
                    FROM advent_shop_purchases_v2
                    WHERE item_id = $1
                      AND user_id = $2
                    """,
                    int(locked_item["id"]),
                    member.id,
                )

                if (
                    existing is not None
                    and existing["status"] in (
                        "pending",
                        "completed",
                    )
                ):
                    return warning_embed(
                        "Déjà acheté",
                        "Cette récompense a déjà été achetée.",
                    )

                rewards = await connection.fetchrow(
                    """
                    SELECT
                        COUNT(*)::INTEGER AS openings,
                        COALESCE(
                            SUM(points_awarded),
                            0
                        )::BIGINT AS total_points
                    FROM advent_openings
                    WHERE campaign_id = $1
                      AND user_id = $2
                    """,
                    campaign_id,
                    member.id,
                )

                spent = await connection.fetchval(
                    """
                    SELECT COALESCE(
                        SUM(points_spent),
                        0
                    )::BIGINT
                    FROM advent_shop_purchases_v2
                    WHERE campaign_id = $1
                      AND user_id = $2
                      AND status IN (
                          'pending',
                          'completed'
                      )
                    """,
                    campaign_id,
                    member.id,
                )

                openings = int(rewards["openings"] or 0)
                total_points = int(
                    rewards["total_points"] or 0
                )
                spent_points = int(spent or 0)
                balance = max(
                    0,
                    total_points - spent_points,
                )

                price = int(locked_item["price"])
                minimum = int(
                    locked_item["min_openings"]
                )

                if openings < minimum:
                    return error_embed(
                        "Cases insuffisantes",
                        (
                            f"Cette récompense demande "
                            f"**{minimum} cases ouvertes**.\n"
                            f"Tu en as actuellement **{openings}**."
                        ),
                    )

                if balance < price:
                    return error_embed(
                        "Solde insuffisant",
                        (
                            f"Cette récompense coûte "
                            f"**{format_points(price)} points**.\n"
                            f"Ton solde est de "
                            f"**{format_points(balance)} points**."
                        ),
                    )

                if existing is not None:
                    purchase = await connection.fetchrow(
                        """
                        UPDATE advent_shop_purchases_v2
                        SET
                            campaign_id = $1,
                            guild_id = $2,
                            role_id = $3,
                            item_name = $4,
                            points_spent = $5,
                            status = 'pending',
                            created_at = NOW(),
                            completed_at = NULL
                        WHERE id = $6
                        RETURNING id
                        """,
                        campaign_id,
                        guild.id,
                        int(locked_item["role_id"]),
                        str(locked_item["display_name"]),
                        price,
                        int(existing["id"]),
                    )
                else:
                    purchase = await connection.fetchrow(
                        """
                        INSERT INTO advent_shop_purchases_v2 (
                            campaign_id,
                            item_id,
                            guild_id,
                            user_id,
                            role_id,
                            item_name,
                            points_spent,
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
                            'pending'
                        )
                        RETURNING id
                        """,
                        campaign_id,
                        int(locked_item["id"]),
                        guild.id,
                        member.id,
                        int(locked_item["role_id"]),
                        str(locked_item["display_name"]),
                        price,
                    )

                purchase_id = int(purchase["id"])

        try:
            await member.add_roles(
                role,
                reason=(
                    f"Achat boutique Avent : "
                    f"{item['display_name']}"
                ),
            )
        except discord.HTTPException:
            if purchase_id is not None:
                await pool.execute(
                    """
                    UPDATE advent_shop_purchases_v2
                    SET status = 'failed'
                    WHERE id = $1
                    """,
                    purchase_id,
                )

            return error_embed(
                "Attribution impossible",
                (
                    "Le bot n'a pas réussi à attribuer le rôle.\n"
                    "**Tes points n'ont pas été dépensés.**"
                ),
            )

        if purchase_id is not None:
            await pool.execute(
                """
                UPDATE advent_shop_purchases_v2
                SET
                    status = 'completed',
                    completed_at = NOW()
                WHERE id = $1
                """,
                purchase_id,
            )

        message = str(item["success_message"]).strip()

        if not message:
            message = (
                f"Tu as obtenu le rôle {role.mention} !"
            )

        return success_embed(
            "Achat effectué",
            (
                f"{message}\n\n"
                f"💸 Prix : **{format_points(int(item['price']))} "
                f"points**\n"
                f"🎭 Rôle : {role.mention}"
            ),
        )

    @app_commands.command(
        name="avent-boutique",
        description="Ouvre la boutique du calendrier de l'Avent.",
    )
    @app_commands.guild_only()
    async def shop(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        try:
            guild = interaction.guild

            if guild is None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Serveur introuvable",
                        "Cette commande doit être utilisée sur un serveur.",
                    ),
                    ephemeral=True,
                )
                return

            campaign = await self.get_campaign(
                guild_id=guild.id,
            )

            if campaign is None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Calendrier introuvable",
                        (
                            "Aucune campagne de l'Avent n'est "
                            "configurée sur ce serveur."
                        ),
                    ),
                    ephemeral=True,
                )
                return

            campaign_id = int(campaign["id"])

            (
                embed,
                items,
                purchased_item_ids,
                balance,
                openings,
            ) = await self.build_shop(
                guild=guild,
                user_id=interaction.user.id,
                campaign_id=campaign_id,
                selected_identifier=None,
            )

            selected_identifier = (
                str(items[0]["identifier"])
                if items
                else None
            )

            view = AdventShopView(
                cog=self,
                owner_id=interaction.user.id,
                guild_id=guild.id,
                campaign_id=campaign_id,
                selected_identifier=selected_identifier,
            )

            view.update_components(
                items=items,
                purchased_item_ids=purchased_item_ids,
                balance=balance,
                openings=openings,
            )

            await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True,
            )

        except Exception:
            LOGGER.exception(
                "Impossible d'ouvrir la boutique de l'Avent"
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
        name="avent-boutique-configurer",
        description="Crée ou modifie une récompense de la boutique.",
    )
    @app_commands.describe(
        identifiant=(
            "Identifiant unique, par exemple noel-2026"
        ),
        nom="Nom affiché dans la boutique",
        role="Rôle remis après l'achat",
        prix="Prix de la récompense en points",
        cases_minimum="Nombre minimum de cases ouvertes",
        message="Message envoyé après l'achat",
        description="Description affichée dans la boutique",
        emoji="Emoji affiché dans le menu",
        annee="Année de la campagne à modifier",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def configure_shop_item(
        self,
        interaction: discord.Interaction,
        identifiant: str,
        nom: str,
        role: discord.Role,
        prix: app_commands.Range[int, 0, 1_000_000],
        cases_minimum: app_commands.Range[int, 0, 24] = 0,
        message: str = "",
        description: str = "",
        emoji: str = "🎁",
        annee: app_commands.Range[int, 2024, 2100] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        try:
            guild = interaction.guild

            if guild is None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Serveur introuvable",
                        "Cette commande doit être utilisée sur un serveur.",
                    ),
                    ephemeral=True,
                )
                return

            identifier = identifiant.strip().lower()
            display_name = nom.strip()
            product_description = description.strip()
            success_message = message.strip()
            product_emoji = emoji.strip() or "🎁"

            if not IDENTIFIER_PATTERN.fullmatch(identifier):
                await interaction.followup.send(
                    embed=error_embed(
                        "Identifiant invalide",
                        (
                            "Utilise uniquement des lettres minuscules, "
                            "des chiffres, `_` ou `-`.\n"
                            "Exemple : `role-noel-2026`"
                        ),
                    ),
                    ephemeral=True,
                )
                return

            if not display_name:
                await interaction.followup.send(
                    embed=error_embed(
                        "Nom invalide",
                        "Le nom de la récompense ne peut pas être vide.",
                    ),
                    ephemeral=True,
                )
                return

            if len(display_name) > 100:
                await interaction.followup.send(
                    embed=error_embed(
                        "Nom trop long",
                        "Le nom doit contenir 100 caractères maximum.",
                    ),
                    ephemeral=True,
                )
                return

            if len(product_description) > 1000:
                await interaction.followup.send(
                    embed=error_embed(
                        "Description trop longue",
                        "La description doit faire 1 000 caractères maximum.",
                    ),
                    ephemeral=True,
                )
                return

            if len(success_message) > 1000:
                await interaction.followup.send(
                    embed=error_embed(
                        "Message trop long",
                        "Le message doit faire 1 000 caractères maximum.",
                    ),
                    ephemeral=True,
                )
                return

            if role.is_default() or role.managed:
                await interaction.followup.send(
                    embed=error_embed(
                        "Rôle invalide",
                        "Ce rôle ne peut pas être attribué par le bot.",
                    ),
                    ephemeral=True,
                )
                return

            bot_member = guild.me

            if bot_member is None or role >= bot_member.top_role:
                await interaction.followup.send(
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

            campaign = await self.get_campaign(
                guild_id=guild.id,
                year=annee,
            )

            if campaign is None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Campagne introuvable",
                        (
                            "Crée d'abord une campagne du "
                            "calendrier de l'Avent."
                        ),
                    ),
                    ephemeral=True,
                )
                return

            if not success_message:
                success_message = (
                    f"Félicitations ! Tu as débloqué "
                    f"**{display_name}**."
                )

            pool = self.get_pool()

            item = await pool.fetchrow(
                """
                INSERT INTO advent_shop_items_v2 (
                    campaign_id,
                    guild_id,
                    identifier,
                    display_name,
                    description,
                    emoji,
                    role_id,
                    price,
                    min_openings,
                    success_message,
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
                    $10,
                    TRUE,
                    NOW()
                )
                ON CONFLICT (
                    campaign_id,
                    identifier
                )
                DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    description = EXCLUDED.description,
                    emoji = EXCLUDED.emoji,
                    role_id = EXCLUDED.role_id,
                    price = EXCLUDED.price,
                    min_openings = EXCLUDED.min_openings,
                    success_message = EXCLUDED.success_message,
                    enabled = TRUE,
                    updated_at = NOW()
                RETURNING id
                """,
                int(campaign["id"]),
                guild.id,
                identifier,
                display_name,
                product_description,
                product_emoji,
                role.id,
                int(prix),
                int(cases_minimum),
                success_message,
            )

            embed = success_embed(
                "Récompense configurée",
                (
                    f"La récompense **{display_name}** est prête "
                    "dans la boutique."
                ),
            )

            embed.add_field(
                name="Identifiant",
                value=f"`{identifier}`",
                inline=True,
            )
            embed.add_field(
                name="Prix",
                value=f"**{format_points(int(prix))} points**",
                inline=True,
            )
            embed.add_field(
                name="Cases minimum",
                value=f"**{int(cases_minimum)}/24**",
                inline=True,
            )
            embed.add_field(
                name="Rôle",
                value=role.mention,
                inline=True,
            )
            embed.add_field(
                name="Campagne",
                value=str(campaign["year"]),
                inline=True,
            )
            embed.add_field(
                name="Numéro interne",
                value=str(item["id"]),
                inline=True,
            )

            await interaction.followup.send(
                embed=embed,
                ephemeral=True,
            )

        except Exception:
            LOGGER.exception(
                "Impossible de configurer la boutique"
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Configuration impossible",
                    "Une erreur inattendue s'est produite.",
                ),
                ephemeral=True,
            )

    @app_commands.command(
        name="avent-boutique-supprimer",
        description="Retire une récompense de la boutique.",
    )
    @app_commands.describe(
        identifiant=(
            "Identifiant de la récompense à supprimer"
        ),
        annee="Année de la campagne concernée",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def delete_shop_item(
        self,
        interaction: discord.Interaction,
        identifiant: str,
        annee: app_commands.Range[int, 2024, 2100] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        try:
            guild = interaction.guild

            if guild is None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Serveur introuvable",
                        "Cette commande doit être utilisée sur un serveur.",
                    ),
                    ephemeral=True,
                )
                return

            identifier = identifiant.strip().lower()

            campaign = await self.get_campaign(
                guild_id=guild.id,
                year=annee,
            )

            if campaign is None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Campagne introuvable",
                        "Aucune campagne ne correspond.",
                    ),
                    ephemeral=True,
                )
                return

            pool = self.get_pool()

            deleted_item = await pool.fetchrow(
                """
                UPDATE advent_shop_items_v2
                SET
                    enabled = FALSE,
                    updated_at = NOW()
                WHERE campaign_id = $1
                  AND identifier = $2
                  AND enabled = TRUE
                RETURNING
                    display_name,
                    identifier
                """,
                int(campaign["id"]),
                identifier,
            )

            if deleted_item is None:
                await interaction.followup.send(
                    embed=error_embed(
                        "Récompense introuvable",
                        (
                            f"Aucune récompense active ne possède "
                            f"l'identifiant `{identifier}`."
                        ),
                    ),
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                embed=success_embed(
                    "Récompense supprimée",
                    (
                        f"**{deleted_item['display_name']}** a été "
                        "retirée de la boutique.\n\n"
                        "Les membres qui l'avaient déjà achetée "
                        "conservent leur rôle."
                    ),
                ),
                ephemeral=True,
            )

        except Exception:
            LOGGER.exception(
                "Impossible de supprimer la récompense"
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Suppression impossible",
                    "Une erreur inattendue s'est produite.",
                ),
                ephemeral=True,
            )


async def setup(
    bot: commands.Bot,
) -> None:
    cog = AdventShop(bot)

    await cog.initialize_database()
    await bot.add_cog(cog)

    # La boutique restera accessible depuis les boutons/panneaux,
    # mais ces commandes ne seront plus visibles dans Discord.
    for command_name in (
        "avent-boutique",
        "avent-boutique-configurer",
        "avent-boutique-supprimer",
    ):
        bot.tree.remove_command(
            command_name
        )
