from __future__ import annotations

import logging
import math
import random
import time
from datetime import datetime, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands


LOGGER = logging.getLogger(__name__)

XP_BASE = 100
PROGRESS_BAR_SIZE = 12

COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
WARNING_COLOR = discord.Color.from_rgb(235, 174, 65)


def base_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=COLOR,
    )


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


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def level_from_xp(total_xp: int) -> int:
    """
    Niveau 0 : 0 XP
    Niveau 1 : 100 XP
    Niveau 2 : 400 XP
    Niveau 3 : 900 XP
    Niveau 10 : 10 000 XP
    """
    normalized = max(0, total_xp)
    return math.isqrt(normalized // XP_BASE)


def xp_for_level(level: int) -> int:
    return XP_BASE * max(0, level) ** 2


def progress_bar(
    current: int,
    maximum: int,
) -> str:
    if maximum <= 0:
        ratio = 1.0
    else:
        ratio = max(
            0.0,
            min(1.0, current / maximum),
        )

    filled = round(ratio * PROGRESS_BAR_SIZE)
    empty = PROGRESS_BAR_SIZE - filled

    return "🟪" * filled + "⬛" * empty


class ProgressionView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        owner_id: int,
        guild_id: int,
    ) -> None:
        super().__init__(timeout=300)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Panneau personnel",
                (
                    "Ce panneau appartient à un autre membre.\n"
                    "Utilise `/progression` pour ouvrir le tien."
                ),
            ),
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="Classement XP",
        emoji="🏆",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def xp_leaderboard(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    "Cette action doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        embed = await self.cog.build_leaderboard_embed(
            guild=guild,
            ranking_type="xp",
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Classement argent",
        emoji="💰",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def money_leaderboard(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    "Cette action doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        embed = await self.cog.build_leaderboard_embed(
            guild=guild,
            ranking_type="money",
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


class AdminMemberSelect(discord.ui.UserSelect):
    def __init__(
        self,
        panel: ProgressionAdminView,
    ) -> None:
        self.panel = panel

        super().__init__(
            placeholder="Sélectionne un membre à gérer…",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.values:
            return

        selected = self.values[0]
        self.panel.selected_user_id = selected.id

        await interaction.response.send_message(
            embed=success_embed(
                "Membre sélectionné",
                (
                    f"{selected.mention} est maintenant sélectionné.\n"
                    "Tu peux utiliser **Modifier** ou "
                    "**Réinitialiser**."
                ),
            ),
            ephemeral=True,
        )


class ProgressionConfigModal(
    discord.ui.Modal,
    title="Configuration de la progression",
):
    cooldown = discord.ui.TextInput(
        label="Délai entre deux gains, en secondes",
        placeholder="60",
        min_length=1,
        max_length=4,
    )

    xp_min = discord.ui.TextInput(
        label="XP minimum par message",
        placeholder="15",
        min_length=1,
        max_length=6,
    )

    xp_max = discord.ui.TextInput(
        label="XP maximum par message",
        placeholder="25",
        min_length=1,
        max_length=6,
    )

    coins_min = discord.ui.TextInput(
        label="Pièces minimum par message",
        placeholder="2",
        min_length=1,
        max_length=6,
    )

    coins_max = discord.ui.TextInput(
        label="Pièces maximum par message",
        placeholder="4",
        min_length=1,
        max_length=6,
    )

    def __init__(
        self,
        *,
        cog: ProgressionCog,
        guild_id: int,
        settings: dict[str, Any],
    ) -> None:
        super().__init__(timeout=300)

        self.cog = cog
        self.guild_id = guild_id

        self.cooldown.default = str(
            settings["cooldown_seconds"]
        )
        self.xp_min.default = str(
            settings["xp_min"]
        )
        self.xp_max.default = str(
            settings["xp_max"]
        )
        self.coins_min.default = str(
            settings["coins_min"]
        )
        self.coins_max.default = str(
            settings["coins_max"]
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            cooldown = int(self.cooldown.value)
            xp_min = int(self.xp_min.value)
            xp_max = int(self.xp_max.value)
            coins_min = int(self.coins_min.value)
            coins_max = int(self.coins_max.value)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    "Tous les champs doivent contenir des nombres entiers.",
                ),
                ephemeral=True,
            )
            return

        if not 5 <= cooldown <= 3600:
            await interaction.response.send_message(
                embed=error_embed(
                    "Délai invalide",
                    "Le délai doit être compris entre 5 et 3 600 secondes.",
                ),
                ephemeral=True,
            )
            return

        if not 0 <= xp_min <= xp_max <= 1_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "XP invalide",
                    (
                        "Les valeurs d'XP doivent être positives "
                        "et le minimum ne doit pas dépasser le maximum."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not 0 <= coins_min <= coins_max <= 1_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Argent invalide",
                    (
                        "Les valeurs d'argent doivent être positives "
                        "et le minimum ne doit pas dépasser le maximum."
                    ),
                ),
                ephemeral=True,
            )
            return

        await self.cog.update_settings(
            guild_id=self.guild_id,
            cooldown_seconds=cooldown,
            xp_min=xp_min,
            xp_max=xp_max,
            coins_min=coins_min,
            coins_max=coins_max,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Configuration enregistrée",
                (
                    f"Cooldown : **{cooldown} secondes**\n"
                    f"XP : **{xp_min} à {xp_max}**\n"
                    f"Argent : **{coins_min} à {coins_max} pièces**"
                ),
            ),
            ephemeral=True,
        )


class AdjustMemberModal(
    discord.ui.Modal,
    title="Modifier un membre",
):
    xp_delta = discord.ui.TextInput(
        label="XP à ajouter ou retirer",
        placeholder="Exemples : 500 ou -200",
        default="0",
        min_length=1,
        max_length=12,
    )

    coins_delta = discord.ui.TextInput(
        label="Pièces à ajouter ou retirer",
        placeholder="Exemples : 100 ou -50",
        default="0",
        min_length=1,
        max_length=12,
    )

    reason = discord.ui.TextInput(
        label="Raison",
        placeholder="Correction administrative",
        default="Correction administrative",
        max_length=200,
        required=False,
    )

    def __init__(
        self,
        *,
        cog: ProgressionCog,
        guild_id: int,
        user_id: int,
    ) -> None:
        super().__init__(timeout=300)

        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            xp_delta = int(self.xp_delta.value)
            coins_delta = int(self.coins_delta.value)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    (
                        "Utilise uniquement des nombres entiers.\n"
                        "Exemples : `500`, `-200` ou `0`."
                    ),
                ),
                ephemeral=True,
            )
            return

        if abs(xp_delta) > 100_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur trop grande",
                    "La modification d'XP est trop importante.",
                ),
                ephemeral=True,
            )
            return

        if abs(coins_delta) > 100_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur trop grande",
                    "La modification d'argent est trop importante.",
                ),
                ephemeral=True,
            )
            return

        stats = await self.cog.adjust_member(
            guild_id=self.guild_id,
            user_id=self.user_id,
            xp_delta=xp_delta,
            coins_delta=coins_delta,
            actor_id=interaction.user.id,
            reason=(
                self.reason.value.strip()
                or "Correction administrative"
            ),
        )

        member_text = f"<@{self.user_id}>"

        await interaction.response.send_message(
            embed=success_embed(
                "Progression modifiée",
                (
                    f"Membre : {member_text}\n"
                    f"XP : **{format_number(stats['total_xp'])}**\n"
                    f"Niveau : **{stats['level']}**\n"
                    f"Argent : **{format_number(stats['wallet'])} pièces**"
                ),
            ),
            ephemeral=True,
        )


class ConfirmProgressionResetView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        owner_id: int,
        guild_id: int,
        user_id: int,
    ) -> None:
        super().__init__(timeout=60)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.user_id = user_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Action interdite",
                "Seul l'administrateur ayant lancé cette action peut répondre.",
            ),
            ephemeral=True,
        )
        return False

    async def disable_buttons(
        self,
        interaction: discord.Interaction,
    ) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        await interaction.response.edit_message(
            view=self,
        )

    @discord.ui.button(
        label="Confirmer la réinitialisation",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.cog.reset_member(
            guild_id=self.guild_id,
            user_id=self.user_id,
        )

        await self.disable_buttons(interaction)

        await interaction.followup.send(
            embed=success_embed(
                "Progression réinitialisée",
                (
                    f"La progression de <@{self.user_id}> "
                    "a été entièrement supprimée."
                ),
            ),
            ephemeral=True,
        )

        self.stop()

    @discord.ui.button(
        label="Annuler",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.disable_buttons(interaction)
        self.stop()


class ProgressionAdminView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: ProgressionCog,
        owner_id: int,
        guild_id: int,
    ) -> None:
        super().__init__(timeout=600)

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.selected_user_id: int | None = None

        self.add_item(
            AdminMemberSelect(self)
        )

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
        label="Configuration",
        emoji="⚙️",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def configuration(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
            use_cache=False,
        )

        modal = ProgressionConfigModal(
            cog=self.cog,
            guild_id=self.guild_id,
            settings=settings,
        )

        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Activer/désactiver",
        emoji="🔌",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def toggle_system(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
            use_cache=False,
        )

        enabled = not settings["enabled"]

        await self.cog.set_setting_boolean(
            guild_id=self.guild_id,
            column="enabled",
            value=enabled,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "État modifié",
                (
                    "Le gain automatique d'XP et d'argent est "
                    f"maintenant **{'activé' if enabled else 'désactivé'}**."
                ),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Notifications de niveau",
        emoji="🔔",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def toggle_notifications(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
            use_cache=False,
        )

        enabled = not settings["level_notifications"]

        await self.cog.set_setting_boolean(
            guild_id=self.guild_id,
            column="level_notifications",
            value=enabled,
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Notifications modifiées",
                (
                    "Les annonces de montée de niveau sont "
                    f"maintenant **{'activées' if enabled else 'désactivées'}**."
                ),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Modifier le membre",
        emoji="✏️",
        style=discord.ButtonStyle.success,
        row=2,
    )
    async def modify_member(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.selected_user_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Aucun membre",
                    "Sélectionne d'abord un membre dans le menu.",
                ),
                ephemeral=True,
            )
            return

        modal = AdjustMemberModal(
            cog=self.cog,
            guild_id=self.guild_id,
            user_id=self.selected_user_id,
        )

        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Réinitialiser le membre",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=2,
    )
    async def reset_selected_member(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.selected_user_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Aucun membre",
                    "Sélectionne d'abord un membre dans le menu.",
                ),
                ephemeral=True,
            )
            return

        view = ConfirmProgressionResetView(
            cog=self.cog,
            owner_id=self.owner_id,
            guild_id=self.guild_id,
            user_id=self.selected_user_id,
        )

        await interaction.response.send_message(
            embed=warning_embed(
                "Confirmation obligatoire",
                (
                    f"Tu vas supprimer l'XP et l'argent de "
                    f"<@{self.selected_user_id}>.\n\n"
                    "**Cette action est définitive.**"
                ),
            ),
            view=view,
            ephemeral=True,
        )


class ProgressionCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

        self._settings_cache: dict[
            int,
            tuple[float, dict[str, Any]],
        ] = {}

    def get_pool(self):
        database = getattr(
            self.bot,
            "database",
            None,
        )

        if database is None:
            raise RuntimeError(
                "Le gestionnaire PostgreSQL est indisponible."
            )

        return database.require_pool()

    async def initialize_database(self) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS progression_settings (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                cooldown_seconds INTEGER NOT NULL DEFAULT 60
                    CHECK (
                        cooldown_seconds >= 5
                        AND cooldown_seconds <= 3600
                    ),
                xp_min INTEGER NOT NULL DEFAULT 15
                    CHECK (xp_min >= 0),
                xp_max INTEGER NOT NULL DEFAULT 25
                    CHECK (xp_max >= xp_min),
                coins_min INTEGER NOT NULL DEFAULT 2
                    CHECK (coins_min >= 0),
                coins_max INTEGER NOT NULL DEFAULT 4
                    CHECK (coins_max >= coins_min),
                level_notifications BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS progression_members (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                total_xp BIGINT NOT NULL DEFAULT 0
                    CHECK (total_xp >= 0),
                wallet BIGINT NOT NULL DEFAULT 0
                    CHECK (wallet >= 0),
                lifetime_coins BIGINT NOT NULL DEFAULT 0
                    CHECK (lifetime_coins >= 0),
                rewarded_messages BIGINT NOT NULL DEFAULT 0
                    CHECK (rewarded_messages >= 0),
                last_reward_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS progression_transactions (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                actor_id BIGINT,
                amount BIGINT NOT NULL,
                transaction_type VARCHAR(50) NOT NULL,
                reason VARCHAR(200) NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS
                progression_members_xp_idx
            ON progression_members (
                guild_id,
                total_xp DESC
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS
                progression_members_wallet_idx
            ON progression_members (
                guild_id,
                wallet DESC
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS
                progression_transactions_user_idx
            ON progression_transactions (
                guild_id,
                user_id,
                created_at DESC
            )
            """
        )

        LOGGER.info(
            "Tables du système de progression vérifiées"
        )

    async def ensure_settings(
        self,
        guild_id: int,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            INSERT INTO progression_settings (
                guild_id
            )
            VALUES ($1)
            ON CONFLICT (guild_id) DO NOTHING
            """,
            guild_id,
        )

    async def get_settings(
        self,
        guild_id: int,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        now = time.monotonic()
        cached = self._settings_cache.get(guild_id)

        if (
            use_cache
            and cached is not None
            and cached[0] > now
        ):
            return cached[1]

        await self.ensure_settings(guild_id)

        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                enabled,
                cooldown_seconds,
                xp_min,
                xp_max,
                coins_min,
                coins_max,
                level_notifications
            FROM progression_settings
            WHERE guild_id = $1
            """,
            guild_id,
        )

        if record is None:
            raise RuntimeError(
                "La configuration de progression est introuvable."
            )

        settings = {
            "enabled": bool(record["enabled"]),
            "cooldown_seconds": int(
                record["cooldown_seconds"]
            ),
            "xp_min": int(record["xp_min"]),
            "xp_max": int(record["xp_max"]),
            "coins_min": int(record["coins_min"]),
            "coins_max": int(record["coins_max"]),
            "level_notifications": bool(
                record["level_notifications"]
            ),
        }

        self._settings_cache[guild_id] = (
            now + 60,
            settings,
        )

        return settings

    async def update_settings(
        self,
        *,
        guild_id: int,
        cooldown_seconds: int,
        xp_min: int,
        xp_max: int,
        coins_min: int,
        coins_max: int,
    ) -> None:
        await self.ensure_settings(guild_id)

        pool = self.get_pool()

        await pool.execute(
            """
            UPDATE progression_settings
            SET
                cooldown_seconds = $2,
                xp_min = $3,
                xp_max = $4,
                coins_min = $5,
                coins_max = $6,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            cooldown_seconds,
            xp_min,
            xp_max,
            coins_min,
            coins_max,
        )

        self._settings_cache.pop(
            guild_id,
            None,
        )

    async def set_setting_boolean(
        self,
        *,
        guild_id: int,
        column: str,
        value: bool,
    ) -> None:
        allowed_columns = {
            "enabled",
            "level_notifications",
        }

        if column not in allowed_columns:
            raise ValueError(
                "Colonne de configuration invalide."
            )

        await self.ensure_settings(guild_id)

        pool = self.get_pool()

        await pool.execute(
            f"""
            UPDATE progression_settings
            SET
                {column} = $2,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            value,
        )

        self._settings_cache.pop(
            guild_id,
            None,
        )

    async def get_member_stats(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> dict[str, int]:
        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                total_xp,
                wallet,
                lifetime_coins,
                rewarded_messages
            FROM progression_members
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
        )

        if record is None:
            total_xp = 0
            wallet = 0
            lifetime_coins = 0
            rewarded_messages = 0
        else:
            total_xp = int(
                record["total_xp"] or 0
            )
            wallet = int(
                record["wallet"] or 0
            )
            lifetime_coins = int(
                record["lifetime_coins"] or 0
            )
            rewarded_messages = int(
                record["rewarded_messages"] or 0
            )

        return {
            "total_xp": total_xp,
            "wallet": wallet,
            "lifetime_coins": lifetime_coins,
            "rewarded_messages": rewarded_messages,
            "level": level_from_xp(total_xp),
        }

    async def award_message(
        self,
        *,
        guild_id: int,
        user_id: int,
        settings: dict[str, Any],
    ) -> dict[str, int] | None:
        pool = self.get_pool()
        current_time = datetime.now(timezone.utc)

        async with pool.acquire() as connection:
            async with connection.transaction():
                lock_key = (
                    f"progression:{guild_id}:{user_id}"
                )

                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1, 0)
                    )
                    """,
                    lock_key,
                )

                await connection.execute(
                    """
                    INSERT INTO progression_members (
                        guild_id,
                        user_id
                    )
                    VALUES ($1, $2)
                    ON CONFLICT (
                        guild_id,
                        user_id
                    )
                    DO NOTHING
                    """,
                    guild_id,
                    user_id,
                )

                current = await connection.fetchrow(
                    """
                    SELECT
                        total_xp,
                        wallet,
                        lifetime_coins,
                        rewarded_messages,
                        last_reward_at
                    FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                )

                if current is None:
                    return None

                last_reward_at = current[
                    "last_reward_at"
                ]

                if last_reward_at is not None:
                    elapsed = (
                        current_time - last_reward_at
                    ).total_seconds()

                    if elapsed < settings[
                        "cooldown_seconds"
                    ]:
                        return None

                xp_gain = random.randint(
                    settings["xp_min"],
                    settings["xp_max"],
                )
                coins_gain = random.randint(
                    settings["coins_min"],
                    settings["coins_max"],
                )

                old_xp = int(
                    current["total_xp"] or 0
                )
                old_level = level_from_xp(
                    old_xp
                )

                updated = await connection.fetchrow(
                    """
                    UPDATE progression_members
                    SET
                        total_xp = total_xp + $3,
                        wallet = wallet + $4,
                        lifetime_coins =
                            lifetime_coins + $4,
                        rewarded_messages =
                            rewarded_messages + 1,
                        last_reward_at = $5,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    RETURNING
                        total_xp,
                        wallet
                    """,
                    guild_id,
                    user_id,
                    xp_gain,
                    coins_gain,
                    current_time,
                )

                if updated is None:
                    return None

                if coins_gain != 0:
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
                            'message_reward',
                            'Récompense de message'
                        )
                        """,
                        guild_id,
                        user_id,
                        coins_gain,
                    )

                total_xp = int(
                    updated["total_xp"]
                )
                new_level = level_from_xp(
                    total_xp
                )

                return {
                    "xp_gain": xp_gain,
                    "coins_gain": coins_gain,
                    "total_xp": total_xp,
                    "wallet": int(
                        updated["wallet"]
                    ),
                    "old_level": old_level,
                    "new_level": new_level,
                }

    async def adjust_member(
        self,
        *,
        guild_id: int,
        user_id: int,
        xp_delta: int,
        coins_delta: int,
        actor_id: int,
        reason: str,
    ) -> dict[str, int]:
        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1, 0)
                    )
                    """,
                    f"progression:{guild_id}:{user_id}",
                )

                await connection.execute(
                    """
                    INSERT INTO progression_members (
                        guild_id,
                        user_id
                    )
                    VALUES ($1, $2)
                    ON CONFLICT (
                        guild_id,
                        user_id
                    )
                    DO NOTHING
                    """,
                    guild_id,
                    user_id,
                )

                current = await connection.fetchrow(
                    """
                    SELECT
                        total_xp,
                        wallet,
                        lifetime_coins
                    FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                )

                if current is None:
                    raise RuntimeError(
                        "Le membre n'a pas pu être créé."
                    )

                old_xp = int(
                    current["total_xp"] or 0
                )
                old_wallet = int(
                    current["wallet"] or 0
                )
                lifetime_coins = int(
                    current["lifetime_coins"] or 0
                )

                new_xp = max(
                    0,
                    old_xp + xp_delta,
                )
                new_wallet = max(
                    0,
                    old_wallet + coins_delta,
                )

                actual_coins_delta = (
                    new_wallet - old_wallet
                )

                new_lifetime_coins = (
                    lifetime_coins
                    + max(0, actual_coins_delta)
                )

                await connection.execute(
                    """
                    UPDATE progression_members
                    SET
                        total_xp = $3,
                        wallet = $4,
                        lifetime_coins = $5,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                    new_xp,
                    new_wallet,
                    new_lifetime_coins,
                )

                if actual_coins_delta != 0:
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
                            $3,
                            $4,
                            'admin_adjustment',
                            $5
                        )
                        """,
                        guild_id,
                        user_id,
                        actor_id,
                        actual_coins_delta,
                        reason[:200],
                    )

        return {
            "total_xp": new_xp,
            "wallet": new_wallet,
            "level": level_from_xp(new_xp),
        }

    async def reset_member(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> None:
        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    DELETE FROM progression_transactions
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                )

                await connection.execute(
                    """
                    DELETE FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                )

    async def build_progression_embed(
        self,
        *,
        member: discord.Member | discord.User,
        guild_id: int,
    ) -> discord.Embed:
        stats = await self.get_member_stats(
            guild_id=guild_id,
            user_id=member.id,
        )

        total_xp = stats["total_xp"]
        level = stats["level"]

        current_level_xp = xp_for_level(
            level
        )
        next_level_xp = xp_for_level(
            level + 1
        )

        current_progress = (
            total_xp - current_level_xp
        )
        required_progress = (
            next_level_xp - current_level_xp
        )

        embed = base_embed(
            f"🦊 Progression de {member.display_name}",
            (
                "Ta progression est permanente et indépendante "
                "du calendrier de l'Avent."
            ),
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.add_field(
            name="⭐ Niveau",
            value=f"**{level}**",
            inline=True,
        )

        embed.add_field(
            name="✨ XP total",
            value=f"**{format_number(total_xp)} XP**",
            inline=True,
        )

        embed.add_field(
            name="💰 Argent",
            value=(
                f"**{format_number(stats['wallet'])} pièces**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Progression du niveau",
            value=(
                f"{progress_bar(current_progress, required_progress)}\n"
                f"**{format_number(current_progress)}** / "
                f"**{format_number(required_progress)} XP**\n"
                f"Prochain niveau à "
                f"**{format_number(next_level_xp)} XP total**"
            ),
            inline=False,
        )

        embed.add_field(
            name="📨 Messages récompensés",
            value=(
                f"**{format_number(stats['rewarded_messages'])}**"
            ),
            inline=True,
        )

        embed.add_field(
            name="🪙 Argent gagné au total",
            value=(
                f"**{format_number(stats['lifetime_coins'])} pièces**"
            ),
            inline=True,
        )

        embed.set_footer(
            text=(
                "L'XP et l'argent peuvent être gagnés "
                "une fois par période de cooldown."
            )
        )

        return embed

    async def build_leaderboard_embed(
        self,
        *,
        guild: discord.Guild,
        ranking_type: str,
    ) -> discord.Embed:
        pool = self.get_pool()

        if ranking_type == "money":
            records = await pool.fetch(
                """
                SELECT
                    user_id,
                    wallet,
                    total_xp
                FROM progression_members
                WHERE guild_id = $1
                ORDER BY
                    wallet DESC,
                    total_xp DESC,
                    user_id ASC
                LIMIT 10
                """,
                guild.id,
            )

            title = "💰 Classement de l'argent"
        else:
            records = await pool.fetch(
                """
                SELECT
                    user_id,
                    wallet,
                    total_xp
                FROM progression_members
                WHERE guild_id = $1
                ORDER BY
                    total_xp DESC,
                    wallet DESC,
                    user_id ASC
                LIMIT 10
                """,
                guild.id,
            )

            title = "🏆 Classement XP"

        if not records:
            return base_embed(
                title,
                "Aucun membre ne possède encore de progression.",
            )

        medals = {
            1: "🥇",
            2: "🥈",
            3: "🥉",
        }

        lines: list[str] = []

        for position, record in enumerate(
            records,
            start=1,
        ):
            user_id = int(
                record["user_id"]
            )

            member = guild.get_member(
                user_id
            )

            member_text = (
                member.mention
                if member is not None
                else f"<@{user_id}>"
            )

            prefix = medals.get(
                position,
                f"**{position}.**",
            )

            total_xp = int(
                record["total_xp"] or 0
            )
            wallet = int(
                record["wallet"] or 0
            )

            if ranking_type == "money":
                value = (
                    f"**{format_number(wallet)} pièces**"
                )
            else:
                level = level_from_xp(
                    total_xp
                )
                value = (
                    f"niveau **{level}** — "
                    f"**{format_number(total_xp)} XP**"
                )

            lines.append(
                f"{prefix} {member_text} — {value}"
            )

        return base_embed(
            title,
            "\n".join(lines),
        )

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ) -> None:
        guild = message.guild

        if guild is None:
            return

        if message.author.bot:
            return

        if message.webhook_id is not None:
            return

        try:
            settings = await self.get_settings(
                guild.id
            )

            if not settings["enabled"]:
                return

            result = await self.award_message(
                guild_id=guild.id,
                user_id=message.author.id,
                settings=settings,
            )

            if result is None:
                return

            if (
                result["new_level"]
                <= result["old_level"]
            ):
                return

            if not settings["level_notifications"]:
                return

            embed = success_embed(
                "Niveau supérieur !",
                (
                    f"{message.author.mention} vient d'atteindre "
                    f"le **niveau {result['new_level']}** !\n\n"
                    f"✨ XP gagné : **{result['xp_gain']}**\n"
                    f"💰 Argent gagné : "
                    f"**{result['coins_gain']} pièces**"
                ),
            )

            try:
                await message.channel.send(
                    embed=embed,
                )
            except discord.HTTPException:
                LOGGER.debug(
                    "Impossible d'envoyer la notification de niveau",
                    exc_info=True,
                )

        except Exception:
            LOGGER.exception(
                "Impossible d'attribuer la récompense de message "
                "à %s dans le serveur %s",
                message.author.id,
                guild.id,
            )

    @app_commands.command(
        name="progression",
        description="Affiche ton niveau, ton XP et ton argent.",
    )
    @app_commands.describe(
        membre="Membre dont tu veux consulter la progression."
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        4.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def progression(
        self,
        interaction: discord.Interaction,
        membre: discord.Member | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Serveur requis",
                    "Cette commande doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        selected_member = (
            membre
            if membre is not None
            else interaction.user
        )

        embed = await self.build_progression_embed(
            member=selected_member,
            guild_id=guild.id,
        )

        view = ProgressionView(
            cog=self,
            owner_id=interaction.user.id,
            guild_id=guild.id,
        )

        await interaction.followup.send(
            embed=embed,
            view=view,
            ephemeral=True,
        )

    @app_commands.command(
        name="progression-admin",
        description="Ouvre le panneau administratif de la progression.",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.guild_only()
    async def progression_admin(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    "Cette commande doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        settings = await self.get_settings(
            guild.id,
            use_cache=False,
        )

        embed = base_embed(
            "⚙️ Administration de la progression",
            (
                "Configure le gain automatique d'XP et d'argent, "
                "ou sélectionne un membre pour modifier sa progression."
            ),
        )

        embed.add_field(
            name="Système",
            value=(
                "Activé ✅"
                if settings["enabled"]
                else "Désactivé ❌"
            ),
            inline=True,
        )

        embed.add_field(
            name="Cooldown",
            value=(
                f"**{settings['cooldown_seconds']} secondes**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Notifications",
            value=(
                "Activées ✅"
                if settings["level_notifications"]
                else "Désactivées ❌"
            ),
            inline=True,
        )

        embed.add_field(
            name="Gain d'XP",
            value=(
                f"**{settings['xp_min']} à "
                f"{settings['xp_max']} XP**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Gain d'argent",
            value=(
                f"**{settings['coins_min']} à "
                f"{settings['coins_max']} pièces**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Gestion d'un membre",
            value=(
                "1. Sélectionne le membre dans le menu.\n"
                "2. Utilise **Modifier** ou **Réinitialiser**."
            ),
            inline=False,
        )

        view = ProgressionAdminView(
            cog=self,
            owner_id=interaction.user.id,
            guild_id=guild.id,
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    cog = ProgressionCog(bot)

    await cog.initialize_database()
    await bot.add_cog(cog)

    LOGGER.info(
        "Système permanent d'XP et d'argent initialisé"
    )
