from __future__ import annotations

import asyncio
import io
import logging
import math
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.shared.leaderboard_card import render_leaderboard_card


LOGGER = logging.getLogger(__name__)

LEADERBOARD_PAGE_SIZE = 10
LEADERBOARD_MAX_PAGES = 10
LEADERBOARD_TIMEOUT_SECONDS = 300

ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)


def error_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=ERROR_COLOR,
    )


def normalize_ranking_type(
    ranking_type: str,
) -> str:
    normalized = str(ranking_type).strip().lower()

    if normalized not in {
        "xp",
        "money",
    }:
        raise ValueError(
            "Le type de classement doit être `xp` ou `money`."
        )

    return normalized


class LeaderboardPageModal(
    discord.ui.Modal,
    title="Rechercher une page",
):
    page_input = discord.ui.TextInput(
        label="Numéro de la page",
        placeholder="Exemple : 3",
        required=True,
        min_length=1,
        max_length=3,
    )

    def __init__(
        self,
        *,
        leaderboard_view: LeaderboardView,
    ) -> None:
        super().__init__(
            timeout=180,
        )

        self.leaderboard_view = leaderboard_view

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            requested_page = int(
                str(self.page_input.value).strip()
            )
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Page invalide",
                    "Entre uniquement un numéro de page.",
                ),
                ephemeral=True,
            )
            return

        if not (
            1
            <= requested_page
            <= self.leaderboard_view.total_pages
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Page introuvable",
                    (
                        "Le numéro doit être compris entre "
                        f"**1** et "
                        f"**{self.leaderboard_view.total_pages}**."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        self.leaderboard_view.current_page = requested_page
        self.leaderboard_view.update_buttons()

        await self.leaderboard_view.refresh_message()


class LeaderboardView(discord.ui.View):
    def __init__(
        self,
        *,
        cog: RankingsCog,
        owner_id: int,
        guild_id: int,
        ranking_type: str,
        total_pages: int,
    ) -> None:
        super().__init__(
            timeout=LEADERBOARD_TIMEOUT_SECONDS,
        )

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.ranking_type = normalize_ranking_type(
            ranking_type
        )

        self.current_page = 1
        self.total_pages = max(
            1,
            min(
                LEADERBOARD_MAX_PAGES,
                int(total_pages),
            ),
        )

        self.message: discord.Message | None = None
        self.closed = False

        self.update_buttons()

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Classement personnel",
                (
                    "Seule la personne ayant ouvert ce classement "
                    "peut utiliser ses boutons.\n\n"
                    "Utilise `/classement` pour ouvrir le tien."
                ),
            ),
            ephemeral=True,
        )
        return False

    def update_buttons(self) -> None:
        self.previous_page.disabled = (
            self.current_page <= 1
        )

        self.next_page.disabled = (
            self.current_page >= self.total_pages
        )

        self.search_page.disabled = (
            self.total_pages <= 1
        )

    async def refresh_message(self) -> None:
        if self.closed:
            return

        if self.message is None:
            return

        guild = self.cog.bot.get_guild(
            self.guild_id
        )

        if guild is None:
            return

        try:
            leaderboard_file = (
                await self.cog.build_leaderboard_file(
                    guild=guild,
                    requester_id=self.owner_id,
                    ranking_type=self.ranking_type,
                    page=self.current_page,
                    total_pages=self.total_pages,
                )
            )

            await self.message.edit(
                attachments=[leaderboard_file],
                view=self,
            )
        except discord.NotFound:
            self.closed = True
            self.stop()
        except discord.HTTPException:
            LOGGER.exception(
                "Impossible d'actualiser le classement du serveur %s.",
                self.guild_id,
            )
        except Exception:
            LOGGER.exception(
                "Erreur pendant la génération du classement du serveur %s.",
                self.guild_id,
            )

    async def on_timeout(self) -> None:
        if self.closed:
            return

        for item in self.children:
            if isinstance(
                item,
                discord.ui.Button,
            ):
                item.disabled = True

        if self.message is None:
            return

        try:
            await self.message.edit(
                view=self,
            )
        except (
            discord.NotFound,
            discord.HTTPException,
        ):
            pass

    @discord.ui.button(
        emoji="◀️",
        label="Précédent",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def previous_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.current_page <= 1:
            await interaction.response.defer()
            return

        await interaction.response.defer()

        self.current_page -= 1
        self.update_buttons()

        await self.refresh_message()

    @discord.ui.button(
        emoji="🔎",
        label="Rechercher",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def search_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            LeaderboardPageModal(
                leaderboard_view=self,
            )
        )

    @discord.ui.button(
        emoji="🗑️",
        label="Fermer",
        style=discord.ButtonStyle.danger,
        row=0,
    )
    async def close_leaderboard(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()

        self.closed = True
        self.stop()

        message = self.message

        if message is None:
            return

        try:
            await message.delete()
        except (
            discord.NotFound,
            discord.HTTPException,
        ):
            pass

    @discord.ui.button(
        emoji="▶️",
        label="Suivant",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def next_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.current_page >= self.total_pages:
            await interaction.response.defer()
            return

        await interaction.response.defer()

        self.current_page += 1
        self.update_buttons()

        await self.refresh_message()


class RankingsCog(commands.Cog):
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
                "Le gestionnaire PostgreSQL est indisponible."
            )

        return database.require_pool()

    def get_progression_cog(self) -> commands.Cog:
        progression_cog = self.bot.get_cog(
            "ProgressionCog"
        )

        if progression_cog is None:
            raise RuntimeError(
                "Le système de progression n'est pas chargé."
            )

        return progression_cog

    def get_leaderboard_background_path(
        self,
    ) -> Path:
        return (
            Path(__file__).resolve().parents[2]
            / "assets"
            / "progression"
            / "leaderboard_background.png"
        )

    async def get_leaderboard_total_members(
        self,
        *,
        guild_id: int,
    ) -> int:
        pool = self.get_pool()

        result = await pool.fetchval(
            """
            SELECT COUNT(*)
            FROM progression_members
            WHERE guild_id = $1
            """,
            guild_id,
        )

        return int(result or 0)

    async def get_leaderboard_total_pages(
        self,
        *,
        guild_id: int,
    ) -> int:
        total_members = (
            await self.get_leaderboard_total_members(
                guild_id=guild_id,
            )
        )

        calculated_pages = math.ceil(
            total_members
            / LEADERBOARD_PAGE_SIZE
        )

        return max(
            1,
            min(
                LEADERBOARD_MAX_PAGES,
                calculated_pages,
            ),
        )

    async def get_leaderboard_records(
        self,
        *,
        guild_id: int,
        ranking_type: str,
        page: int,
    ) -> list[Any]:
        ranking_type = normalize_ranking_type(
            ranking_type
        )

        page = max(
            1,
            min(
                LEADERBOARD_MAX_PAGES,
                int(page),
            ),
        )

        offset = (
            page - 1
        ) * LEADERBOARD_PAGE_SIZE

        pool = self.get_pool()

        if ranking_type == "money":
            records = await pool.fetch(
                """
                SELECT
                    user_id,
                    total_xp,
                    wallet
                FROM progression_members
                WHERE guild_id = $1
                ORDER BY
                    wallet DESC,
                    total_xp DESC,
                    user_id ASC
                LIMIT $2
                OFFSET $3
                """,
                guild_id,
                LEADERBOARD_PAGE_SIZE,
                offset,
            )
        else:
            records = await pool.fetch(
                """
                SELECT
                    user_id,
                    total_xp,
                    wallet
                FROM progression_members
                WHERE guild_id = $1
                ORDER BY
                    total_xp DESC,
                    wallet DESC,
                    user_id ASC
                LIMIT $2
                OFFSET $3
                """,
                guild_id,
                LEADERBOARD_PAGE_SIZE,
                offset,
            )

        return list(records)

    async def get_personal_leaderboard_data(
        self,
        *,
        guild_id: int,
        user_id: int,
        ranking_type: str,
    ) -> dict[str, int | None]:
        ranking_type = normalize_ranking_type(
            ranking_type
        )

        pool = self.get_pool()

        personal_record = await pool.fetchrow(
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

        if personal_record is None:
            return {
                "rank": None,
                "total_xp": 0,
                "wallet": 0,
            }

        total_xp = int(
            personal_record["total_xp"] or 0
        )

        wallet = int(
            personal_record["wallet"] or 0
        )

        if ranking_type == "money":
            rank = await pool.fetchval(
                """
                SELECT COUNT(*) + 1
                FROM progression_members
                WHERE guild_id = $1
                  AND (
                        wallet > $2
                        OR (
                            wallet = $2
                            AND total_xp > $3
                        )
                        OR (
                            wallet = $2
                            AND total_xp = $3
                            AND user_id < $4
                        )
                  )
                """,
                guild_id,
                wallet,
                total_xp,
                user_id,
            )
        else:
            rank = await pool.fetchval(
                """
                SELECT COUNT(*) + 1
                FROM progression_members
                WHERE guild_id = $1
                  AND (
                        total_xp > $2
                        OR (
                            total_xp = $2
                            AND wallet > $3
                        )
                        OR (
                            total_xp = $2
                            AND wallet = $3
                            AND user_id < $4
                        )
                  )
                """,
                guild_id,
                total_xp,
                wallet,
                user_id,
            )

        return {
            "rank": (
                int(rank)
                if rank is not None
                else None
            ),
            "total_xp": total_xp,
            "wallet": wallet,
        }

    def get_display_name(
        self,
        *,
        guild: discord.Guild,
        user_id: int,
    ) -> str:
        member = guild.get_member(
            user_id
        )

        if member is not None:
            return member.display_name

        cached_user = self.bot.get_user(
            user_id
        )

        if cached_user is not None:
            return cached_user.display_name

        return f"Utilisateur {user_id}"

    async def build_leaderboard_file(
    self,
    *,
    guild: discord.Guild,
    requester: discord.Member | discord.User,
    ranking_type: str,
    page: int,
) -> tuple[discord.File, int]:
    total_entries = await self.get_leaderboard_count(
        guild_id=guild.id,
    )

    total_pages = max(
        1,
        min(
            MAX_LEADERBOARD_PAGES,
            math.ceil(total_entries / LEADERBOARD_PAGE_SIZE),
        ),
    )

    page = max(0, min(page, total_pages - 1))
    offset = page * LEADERBOARD_PAGE_SIZE

    records = await self.get_leaderboard_page(
        guild_id=guild.id,
        ranking_type=ranking_type,
        offset=offset,
    )

    rows: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        user_id = int(record["user_id"])
        total_xp = int(record["total_xp"] or 0)
        wallet = int(record["wallet"] or 0)

        value = (
            wallet
            if ranking_type == "money"
            else total_xp
        )

        rows.append(
            {
                "rank": offset + index,
                "user_id": user_id,
                "display_name": self.get_display_name(
                    guild,
                    user_id,
                ),
                "value": value,
            }
        )

    personal = await self.get_personal_leaderboard_row(
        guild_id=guild.id,
        user_id=requester.id,
        ranking_type=ranking_type,
    )

    personal_total_xp = int(personal["total_xp"])
    personal_wallet = int(personal["wallet"])

    personal_value = (
        personal_wallet
        if ranking_type == "money"
        else personal_total_xp
    )

    personal_row = {
        "rank": int(personal["rank"]),
        "user_id": requester.id,
        "display_name": getattr(
            requester,
            "display_name",
            requester.name,
        ),
        "value": personal_value,
    }

    image = await asyncio.to_thread(
        render_leaderboard_card,
        ranking_type=ranking_type,
        page=page + 1,
        total_pages=total_pages,
        rows=rows,
        personal_row=personal_row,
        background_path=LEADERBOARD_BACKGROUND_PATH,
    )

    image.seek(0)

    leaderboard_file = discord.File(
        image,
        filename=(
            f"classement-{ranking_type}-"
            f"page-{page + 1}.png"
        ),
    )

    return leaderboard_file, total_pages

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
                    (
                        "Cette commande doit être utilisée "
                        "dans un serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        selected_member = (
            membre
            if membre is not None
            else interaction.user
        )

        try:
            progression_cog = (
                self.get_progression_cog()
            )

            build_progression_card = getattr(
                progression_cog,
                "build_progression_card",
            )

            progression_file = (
                await build_progression_card(
                    member=selected_member,
                    guild_id=guild.id,
                )
            )
        except Exception:
            LOGGER.exception(
                "Impossible de générer la carte de progression de %s.",
                selected_member.id,
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Erreur de génération",
                    (
                        "La carte de progression n'a pas pu "
                        "être générée.\n"
                        "Consulte les logs du bot."
                    ),
                ),
                ephemeral=True,
            )
            return

        # La carte est envoyée directement :
        # aucun embed et aucun bouton.
        await interaction.followup.send(
            file=progression_file,
            ephemeral=True,
        )

    @app_commands.command(
        name="classement",
        description=(
            "Affiche le classement XP ou argent du serveur."
        ),
    )
    @app_commands.rename(
        ranking_type="type",
    )
    @app_commands.describe(
        ranking_type=(
            "Type de classement à afficher."
        ),
    )
    @app_commands.choices(
        ranking_type=[
            app_commands.Choice(
                name="XP",
                value="xp",
            ),
            app_commands.Choice(
                name="Argent",
                value="money",
            ),
        ]
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
    async def classement(
        self,
        interaction: discord.Interaction,
        ranking_type: app_commands.Choice[str],
    ) -> None:
        await interaction.response.defer(
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Serveur requis",
                    (
                        "Cette commande doit être utilisée "
                        "dans un serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        selected_type = normalize_ranking_type(
            ranking_type.value
        )

        try:
            total_pages = (
                await self.get_leaderboard_total_pages(
                    guild_id=guild.id,
                )
            )

            leaderboard_file = (
                await self.build_leaderboard_file(
                    guild=guild,
                    requester_id=interaction.user.id,
                    ranking_type=selected_type,
                    page=1,
                    total_pages=total_pages,
                )
            )
        except Exception:
            LOGGER.exception(
                "Impossible de générer le classement %s du serveur %s.",
                selected_type,
                guild.id,
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Erreur de génération",
                    (
                        "Le classement n'a pas pu être généré.\n"
                        "Consulte les logs du bot."
                    ),
                ),
                ephemeral=True,
            )
            return

        view = LeaderboardView(
            cog=self,
            owner_id=interaction.user.id,
            guild_id=guild.id,
            ranking_type=selected_type,
            total_pages=total_pages,
        )

        # Aucun embed : l'image est directement attachée
        # au message public.
        message = await interaction.followup.send(
            file=leaderboard_file,
            view=view,
            wait=True,
        )

        view.message = message


async def setup(
    bot: commands.Bot,
) -> None:
    # progression.py possède déjà une ancienne commande
    # /progression. On la retire de l'arbre des commandes avant
    # d'ajouter la nouvelle version sans embed et sans boutons.
    existing_progression = bot.tree.get_command(
        "progression"
    )

    if existing_progression is not None:
        bot.tree.remove_command(
            "progression"
        )

    await bot.add_cog(
        RankingsCog(bot)
    )

    LOGGER.info(
        "Nouvelle commande /progression et classement graphique chargés"
    )
