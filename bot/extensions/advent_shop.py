from __future__ import annotations

import os
from datetime import date, datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands


SHOP_PRICE = 444
SHOP_MIN_OPENINGS = 14


class AdventShop(commands.Cog):
    """Boutique du calendrier de l'Avent."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def initialize(self) -> None:
        """Crée automatiquement les tables PostgreSQL de la boutique."""
        pool = self.bot.database.require_pool()

        async with pool.acquire() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS advent_shop_config (
                    campaign_id BIGINT PRIMARY KEY
                        REFERENCES advent_campaigns(id)
                        ON DELETE CASCADE,

                    guild_id BIGINT NOT NULL,
                    role_id BIGINT NOT NULL,
                    item_name TEXT NOT NULL,
                    price INTEGER NOT NULL DEFAULT 444,
                    min_openings INTEGER NOT NULL DEFAULT 14,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS advent_shop_purchases (
                    id BIGSERIAL PRIMARY KEY,

                    campaign_id BIGINT NOT NULL
                        REFERENCES advent_campaigns(id)
                        ON DELETE CASCADE,

                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    role_id BIGINT NOT NULL,
                    item_name TEXT NOT NULL,
                    points_spent INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                    UNIQUE (campaign_id, user_id)
                )
                """
            )

    @staticmethod
    def _current_year() -> int:
        """
        Utilise ADVENT_TEST_DATE si elle existe.

        Exemple :
        ADVENT_TEST_DATE=2026-12-15
        """
        test_date = os.getenv("ADVENT_TEST_DATE", "").strip()

        if test_date:
            try:
                return date.fromisoformat(test_date).year
            except ValueError:
                pass

        return datetime.now(timezone.utc).year

    async def _get_campaign(
        self,
        guild_id: int,
        *,
        year: int | None = None,
    ):
        pool = self.bot.database.require_pool()
        selected_year = year or self._current_year()

        campaign = await pool.fetchrow(
            """
            SELECT id, guild_id, year, title, enabled
            FROM advent_campaigns
            WHERE guild_id = $1
              AND year = $2
            ORDER BY id DESC
            LIMIT 1
            """,
            guild_id,
            selected_year,
        )

        if campaign is not None:
            return campaign

        return await pool.fetchrow(
            """
            SELECT id, guild_id, year, title, enabled
            FROM advent_campaigns
            WHERE guild_id = $1
            ORDER BY year DESC, id DESC
            LIMIT 1
            """,
            guild_id,
        )

    async def _get_config(self, campaign_id: int):
        pool = self.bot.database.require_pool()

        return await pool.fetchrow(
            """
            SELECT
                campaign_id,
                guild_id,
                role_id,
                item_name,
                price,
                min_openings,
                enabled
            FROM advent_shop_config
            WHERE campaign_id = $1
            """,
            campaign_id,
        )

    async def _get_stats(
        self,
        campaign_id: int,
        user_id: int,
    ) -> tuple[int, int, int]:
        """
        Retourne :
        - nombre de cases ouvertes
        - total de points gagnés
        - solde actuellement disponible
        """
        pool = self.bot.database.require_pool()

        statistics = await pool.fetchrow(
            """
            SELECT
                COUNT(*)::INTEGER AS opened_count,
                COALESCE(SUM(points_awarded), 0)::INTEGER AS total_points
            FROM advent_openings
            WHERE campaign_id = $1
              AND user_id = $2
            """,
            campaign_id,
            user_id,
        )

        spent_points = await pool.fetchval(
            """
            SELECT COALESCE(SUM(points_spent), 0)::INTEGER
            FROM advent_shop_purchases
            WHERE campaign_id = $1
              AND user_id = $2
              AND status IN ('pending', 'completed')
            """,
            campaign_id,
            user_id,
        )

        opened_count = int(statistics["opened_count"])
        total_points = int(statistics["total_points"])
        available_points = max(0, total_points - int(spent_points or 0))

        return opened_count, total_points, available_points

    @staticmethod
    def _check_role(
        guild: discord.Guild,
        role: discord.Role,
    ) -> str | None:
        if role.is_default():
            return "Le rôle `@everyone` ne peut pas être vendu."

        if role.managed:
            return (
                "Ce rôle est géré par Discord ou par une intégration. "
                "Le bot ne peut pas l'attribuer."
            )

        bot_member = guild.me

        if bot_member is None:
            return "Impossible de retrouver le compte du bot sur le serveur."

        if not bot_member.guild_permissions.manage_roles:
            return (
                "Le bot n'a pas la permission **Gérer les rôles**."
            )

        if role >= bot_member.top_role:
            return (
                "Le rôle de la boutique est placé au-dessus du rôle du bot. "
                "Déplace le rôle du bot au-dessus dans les paramètres Discord."
            )

        return None

    @app_commands.command(
        name="avent-admin-boutique",
        description="Configure le rôle vendu dans la boutique de l'Avent.",
    )
    @app_commands.describe(
        role="Rôle que les membres pourront acheter",
        annee="Année de la campagne, par exemple 2026",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_shop(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        annee: int | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Cette commande doit être utilisée sur un serveur.",
                ephemeral=True,
            )
            return

        role_error = self._check_role(interaction.guild, role)

        if role_error is not None:
            await interaction.response.send_message(
                role_error,
                ephemeral=True,
            )
            return

        campaign = await self._get_campaign(
            interaction.guild.id,
            year=annee,
        )

        if campaign is None:
            await interaction.response.send_message(
                "Aucune campagne de l'Avent n'existe sur ce serveur.",
                ephemeral=True,
            )
            return

        item_name = f"Noël {campaign['year']}"
        pool = self.bot.database.require_pool()

        await pool.execute(
            """
            INSERT INTO advent_shop_config (
                campaign_id,
                guild_id,
                role_id,
                item_name,
                price,
                min_openings,
                enabled,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, TRUE, NOW())

            ON CONFLICT (campaign_id)
            DO UPDATE SET
                guild_id = EXCLUDED.guild_id,
                role_id = EXCLUDED.role_id,
                item_name = EXCLUDED.item_name,
                price = EXCLUDED.price,
                min_openings = EXCLUDED.min_openings,
                enabled = TRUE,
                updated_at = NOW()
            """,
            campaign["id"],
            interaction.guild.id,
            role.id,
            item_name,
            SHOP_PRICE,
            SHOP_MIN_OPENINGS,
        )

        embed = discord.Embed(
            title="🛍️ Boutique de l'Avent configurée",
            color=discord.Color.from_rgb(231, 142, 181),
        )
        embed.add_field(
            name="Récompense",
            value=role.mention,
            inline=False,
        )
        embed.add_field(
            name="Prix",
            value=f"{SHOP_PRICE} points",
            inline=True,
        )
        embed.add_field(
            name="Cases nécessaires",
            value=f"{SHOP_MIN_OPENINGS} cases",
            inline=True,
        )
        embed.add_field(
            name="Campagne",
            value=f"{campaign['year']}",
            inline=True,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="avent-boutique",
        description="Affiche la boutique du calendrier de l'Avent.",
    )
    @app_commands.guild_only()
    async def shop(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            return

        campaign = await self._get_campaign(interaction.guild.id)

        if campaign is None:
            await interaction.response.send_message(
                "Aucune campagne de l'Avent n'existe.",
                ephemeral=True,
            )
            return

        config = await self._get_config(campaign["id"])

        if config is None or not config["enabled"]:
            await interaction.response.send_message(
                "La boutique de l'Avent n'est pas encore configurée.",
                ephemeral=True,
            )
            return

        role = interaction.guild.get_role(config["role_id"])

        if role is None:
            await interaction.response.send_message(
                "Le rôle de la boutique n'existe plus. "
                "Un administrateur doit refaire "
                "`/avent-admin-boutique`.",
                ephemeral=True,
            )
            return

        opened, total, available = await self._get_stats(
            campaign["id"],
            interaction.user.id,
        )

        points_missing = max(0, config["price"] - available)
        cases_missing = max(0, config["min_openings"] - opened)

        if points_missing == 0 and cases_missing == 0:
            status = (
                "✅ Tu remplis toutes les conditions.\n"
                "Utilise `/avent-acheter` pour obtenir le rôle."
            )
        else:
            requirements = []

            if points_missing:
                requirements.append(
                    f"• Il te manque **{points_missing} points**."
                )

            if cases_missing:
                requirements.append(
                    f"• Il te manque **{cases_missing} case(s)** ouverte(s)."
                )

            status = "\n".join(requirements)

        embed = discord.Embed(
            title="🎄 Boutique de l'Avent",
            description=(
                f"Récompense disponible : {role.mention}\n\n"
                f"💰 Prix : **{config['price']} points**\n"
                f"🎁 Condition : **{config['min_openings']} cases ouvertes**"
            ),
            color=discord.Color.from_rgb(231, 142, 181),
        )

        embed.add_field(
            name="Ton avancée",
            value=(
                f"Points gagnés : **{total}**\n"
                f"Solde disponible : **{available}**\n"
                f"Cases ouvertes : **{opened}/24**"
            ),
            inline=False,
        )

        embed.add_field(
            name="État de ton achat",
            value=status,
            inline=False,
        )

        embed.set_footer(
            text=(
                "Les points dépensés restent visibles dans le classement, "
                "mais ne sont plus disponibles dans ton solde."
            )
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="avent-solde",
        description="Affiche ton solde de points de l'Avent.",
    )
    @app_commands.guild_only()
    async def balance(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            return

        campaign = await self._get_campaign(interaction.guild.id)

        if campaign is None:
            await interaction.response.send_message(
                "Aucune campagne de l'Avent n'existe.",
                ephemeral=True,
            )
            return

        opened, total, available = await self._get_stats(
            campaign["id"],
            interaction.user.id,
        )

        spent = total - available

        embed = discord.Embed(
            title="💰 Ton solde de l'Avent",
            color=discord.Color.from_rgb(231, 142, 181),
        )
        embed.add_field(
            name="Points gagnés",
            value=str(total),
            inline=True,
        )
        embed.add_field(
            name="Points dépensés",
            value=str(spent),
            inline=True,
        )
        embed.add_field(
            name="Solde disponible",
            value=str(available),
            inline=True,
        )
        embed.add_field(
            name="Cases ouvertes",
            value=f"{opened}/24",
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="avent-acheter",
        description="Achète le rôle spécial de Noël.",
    )
    @app_commands.guild_only()
    async def buy(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        campaign = await self._get_campaign(interaction.guild.id)

        if campaign is None:
            await interaction.followup.send(
                "Aucune campagne de l'Avent n'existe.",
                ephemeral=True,
            )
            return

        config = await self._get_config(campaign["id"])

        if config is None or not config["enabled"]:
            await interaction.followup.send(
                "La boutique de l'Avent n'est pas configurée.",
                ephemeral=True,
            )
            return

        role = interaction.guild.get_role(config["role_id"])

        if role is None:
            await interaction.followup.send(
                "Le rôle vendu dans la boutique n'existe plus.",
                ephemeral=True,
            )
            return

        role_error = self._check_role(interaction.guild, role)

        if role_error is not None:
            await interaction.followup.send(
                role_error,
                ephemeral=True,
            )
            return

        member = interaction.guild.get_member(interaction.user.id)

        if member is None:
            try:
                member = await interaction.guild.fetch_member(
                    interaction.user.id
                )
            except discord.HTTPException:
                await interaction.followup.send(
                    "Impossible de retrouver ton profil sur le serveur.",
                    ephemeral=True,
                )
                return

        pool = self.bot.database.require_pool()

        existing_purchase = await pool.fetchrow(
            """
            SELECT id, status, points_spent
            FROM advent_shop_purchases
            WHERE campaign_id = $1
              AND user_id = $2
            """,
            campaign["id"],
            member.id,
        )

        if role in member.roles:
            if existing_purchase is not None:
                await interaction.followup.send(
                    f"Tu possèdes déjà {role.mention}. 🎄",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"Tu possèdes déjà {role.mention}. "
                    "Aucun point ne t'a été retiré.",
                    ephemeral=True,
                )
            return

        is_new_purchase = existing_purchase is None
        purchase_id: int

        if existing_purchase is None:
            opened, total, available = await self._get_stats(
                campaign["id"],
                member.id,
            )

            if opened < config["min_openings"]:
                missing = config["min_openings"] - opened

                await interaction.followup.send(
                    f"Il te manque **{missing} case(s)** ouverte(s).\n"
                    f"Tu dois avoir ouvert au moins "
                    f"**{config['min_openings']} cases**.",
                    ephemeral=True,
                )
                return

            if available < config["price"]:
                missing = config["price"] - available

                await interaction.followup.send(
                    f"Tu n'as pas assez de points.\n"
                    f"Solde : **{available} points**\n"
                    f"Prix : **{config['price']} points**\n"
                    f"Il te manque **{missing} points**.",
                    ephemeral=True,
                )
                return

            purchase = await pool.fetchrow(
                """
                INSERT INTO advent_shop_purchases (
                    campaign_id,
                    guild_id,
                    user_id,
                    role_id,
                    item_name,
                    points_spent,
                    status
                )
                VALUES ($1, $2, $3, $4, $5, $6, 'pending')

                ON CONFLICT (campaign_id, user_id)
                DO NOTHING

                RETURNING id
                """,
                campaign["id"],
                interaction.guild.id,
                member.id,
                role.id,
                config["item_name"],
                config["price"],
            )

            if purchase is None:
                await interaction.followup.send(
                    "Un achat existe déjà pour ton compte. "
                    "Réessaie la commande dans quelques secondes.",
                    ephemeral=True,
                )
                return

            purchase_id = purchase["id"]

        else:
            purchase_id = existing_purchase["id"]

        try:
            await member.add_roles(
                role,
                reason=(
                    f"Achat boutique Avent : "
                    f"{config['price']} points"
                ),
            )
        except discord.Forbidden:
            if is_new_purchase:
                await pool.execute(
                    """
                    DELETE FROM advent_shop_purchases
                    WHERE id = $1
                      AND status = 'pending'
                    """,
                    purchase_id,
                )

            await interaction.followup.send(
                "Discord refuse de donner le rôle. "
                "Vérifie que le rôle du bot est placé au-dessus du rôle "
                "vendu et que le bot possède la permission "
                "**Gérer les rôles**.\n\n"
                "Tes points n'ont pas été débités.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            if is_new_purchase:
                await pool.execute(
                    """
                    DELETE FROM advent_shop_purchases
                    WHERE id = $1
                      AND status = 'pending'
                    """,
                    purchase_id,
                )

            await interaction.followup.send(
                "Discord a rencontré une erreur pendant l'attribution "
                "du rôle. Tes points n'ont pas été débités.",
                ephemeral=True,
            )
            return

        await pool.execute(
            """
            UPDATE advent_shop_purchases
            SET status = 'completed'
            WHERE id = $1
            """,
            purchase_id,
        )

        if is_new_purchase:
            _, _, new_balance = await self._get_stats(
                campaign["id"],
                member.id,
            )

            embed = discord.Embed(
                title="🎉 Achat réussi !",
                description=(
                    f"Tu as obtenu le rôle {role.mention}.\n\n"
                    f"💰 Prix payé : **{config['price']} points**\n"
                    f"💳 Nouveau solde : **{new_balance} points**"
                ),
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="🎄 Rôle restauré",
                description=(
                    f"Ton rôle {role.mention} t'a été redonné.\n"
                    "Aucun point supplémentaire n'a été retiré."
                ),
                color=discord.Color.green(),
            )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @admin_shop.error
    async def admin_shop_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = (
                "Tu dois être administrateur pour configurer la boutique."
            )
        else:
            message = f"Erreur pendant la configuration : {error}"

        if interaction.response.is_done():
            await interaction.followup.send(
                message,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    cog = AdventShop(bot)
    await cog.initialize()
    await bot.add_cog(cog)
