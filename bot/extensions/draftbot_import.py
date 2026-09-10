from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.extensions.progression import level_from_xp


logger = logging.getLogger(__name__)

GUILD_ID = 733277977831407628
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8 Mo


@dataclass(slots=True)
class DraftBotUser:
    user_id: int
    username: str
    level: int
    total_xp: int
    current_xp: int
    next_xp: int


USER_PATTERN = re.compile(
    r"""
    <li\b
    (?=[^>]*\bid="(?P<user_id>\d+)")
    (?=[^>]*\bclass="[^"]*\buser-element\b[^"]*")
    [^>]*>
    (?P<body>.*?)
    </li>
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

USERNAME_PATTERN = re.compile(
    r'<span\s+class="username">(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)

LEVEL_PATTERN = re.compile(
    r'<div\s+class="[^"]*\blevel\b[^"]*">\s*<span>(\d+)</span>',
    re.IGNORECASE | re.DOTALL,
)

STAT_PATTERN = re.compile(
    r"""
    <div\s+class="element">\s*
    <div\s+class="value">(.*?)</div>\s*
    <div\s+class="title">(Total|Actuel|Prochain)</div>
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

TAG_PATTERN = re.compile(r"<[^>]+>")


def clean_text(value: str) -> str:
    value = TAG_PATTERN.sub("", value)
    value = html.unescape(value)
    return value.strip()


def parse_number(value: str) -> int:
    """
    Convertit notamment :
    177,7 k -> 177700
    4,2 k   -> 4200
    327     -> 327
    """
    normalized = clean_text(value).lower()
    normalized = normalized.replace("\xa0", "")
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace(",", ".")

    multiplier = 1

    if normalized.endswith("k"):
        multiplier = 1_000
        normalized = normalized[:-1]
    elif normalized.endswith("m"):
        multiplier = 1_000_000
        normalized = normalized[:-1]

    return round(float(normalized) * multiplier)


def parse_draftbot_html(content: str) -> list[DraftBotUser]:
    users: dict[int, DraftBotUser] = {}

    for match in USER_PATTERN.finditer(content):
        user_id = int(match.group("user_id"))
        body = match.group("body")

        username_match = USERNAME_PATTERN.search(body)
        level_match = LEVEL_PATTERN.search(body)

        if level_match is None:
            logger.warning(
                "Impossible de trouver le niveau DraftBot pour %s.",
                user_id,
            )
            continue

        username = (
            clean_text(username_match.group(1))
            if username_match is not None
            else str(user_id)
        )

        stats: dict[str, int] = {}

        for stat_match in STAT_PATTERN.finditer(body):
            value = parse_number(stat_match.group(1))
            title = clean_text(stat_match.group(2)).lower()
            stats[title] = value

        if not {"total", "actuel", "prochain"}.issubset(stats):
            logger.warning(
                "Statistiques DraftBot incomplètes pour %s (%s).",
                username,
                user_id,
            )
            continue

        users[user_id] = DraftBotUser(
            user_id=user_id,
            username=username,
            level=int(level_match.group(1)),
            total_xp=stats["total"],
            current_xp=stats["actuel"],
            next_xp=stats["prochain"],
        )

    return list(users.values())


def convert_draftbot_xp(user: DraftBotUser) -> int:
    """
    Convertit la progression DraftBot vers le système XP du bot.

    Le système local utilise :
        seuil du niveau L = 100 * L²

    La proportion de progression dans le niveau DraftBot est conservée.
    """
    local_level_start = 100 * user.level * user.level
    local_next_level = 100 * (user.level + 1) * (user.level + 1)
    local_level_span = local_next_level - local_level_start

    draftbot_level_span = user.current_xp + user.next_xp

    if draftbot_level_span <= 0:
        progress = 0.0
    else:
        progress = user.current_xp / draftbot_level_span

    progress = max(0.0, min(progress, 0.999999))

    converted_progress = round(progress * local_level_span)
    converted_progress = min(converted_progress, local_level_span - 1)

    return local_level_start + converted_progress


class DraftBotImportCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def ensure_tables(self) -> None:
        database = getattr(self.bot, "database", None)

        if database is None:
            raise RuntimeError("La base de données n'est pas disponible.")

        await database.execute(
            """
            CREATE TABLE IF NOT EXISTS draftbot_xp_imports (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                draftbot_level INTEGER NOT NULL,
                draftbot_total_xp BIGINT NOT NULL,
                current_xp BIGINT,
                next_xp BIGINT,
                converted_xp BIGINT NOT NULL,
                imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        # Compatibilité si la table avait été créée avec l'ancienne version.
        await database.execute(
            """
            ALTER TABLE draftbot_xp_imports
            ADD COLUMN IF NOT EXISTS current_xp BIGINT
            """
        )

        await database.execute(
            """
            ALTER TABLE draftbot_xp_imports
            ADD COLUMN IF NOT EXISTS next_xp BIGINT
            """
        )

        await database.execute(
            """
            ALTER TABLE draftbot_xp_imports
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
            NOT NULL DEFAULT NOW()
            """
        )

    @app_commands.command(
        name="import-draftbot-xp",
        description="Importe les niveaux DraftBot depuis un fichier HTML.",
    )
    @app_commands.describe(
        fichier="Le fichier HTML contenant le classement DraftBot",
        confirmer="Mettre sur Oui pour effectuer réellement l'import",
        membres_presents_seulement=(
            "Ignorer les utilisateurs qui ne sont plus sur le serveur"
        ),
        attribuer_roles="Attribuer aussi les rôles correspondant aux niveaux",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def import_draftbot_xp(
        self,
        interaction: discord.Interaction,
        fichier: discord.Attachment,
        confirmer: bool = False,
        membres_presents_seulement: bool = True,
        attribuer_roles: bool = False,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un serveur.",
                ephemeral=True,
            )
            return

        if interaction.guild.id != GUILD_ID:
            await interaction.response.send_message(
                "Cette commande n'est pas disponible sur ce serveur.",
                ephemeral=True,
            )
            return

        if fichier.size > MAX_FILE_SIZE:
            await interaction.response.send_message(
                "Le fichier dépasse la limite de 8 Mo.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            raw_content = await fichier.read()
            content = raw_content.decode("utf-8", errors="replace")
            users = parse_draftbot_html(content)
        except Exception:
            logger.exception("Erreur pendant la lecture du fichier DraftBot.")
            await interaction.followup.send(
                "Impossible de lire le fichier HTML.",
                ephemeral=True,
            )
            return

        if not users:
            await interaction.followup.send(
                "Aucun membre DraftBot n'a été détecté dans ce fichier.",
                ephemeral=True,
            )
            return

        present_users: list[DraftBotUser] = []
        absent_users: list[DraftBotUser] = []

        for user in users:
            member = interaction.guild.get_member(user.user_id)

            if member is None:
                absent_users.append(user)
            else:
                present_users.append(user)

        users_to_import = (
            present_users if membres_presents_seulement else users
        )

        total_converted_xp = sum(
            convert_draftbot_xp(user)
            for user in users_to_import
        )

        if not confirmer:
            preview_lines = []

            for user in users_to_import[:10]:
                converted_xp = convert_draftbot_xp(user)
                preview_lines.append(
                    f"• {user.username} — niveau {user.level} "
                    f"→ {converted_xp:,} XP"
                )

            preview = "\n".join(preview_lines)

            await interaction.followup.send(
                "## Prévisualisation de l'import DraftBot\n"
                f"**Membres détectés :** {len(users)}\n"
                f"**Présents sur le serveur :** {len(present_users)}\n"
                f"**Absents du serveur :** {len(absent_users)}\n"
                f"**Membres à importer :** {len(users_to_import)}\n"
                f"**XP convertie totale :** {total_converted_xp:,}\n\n"
                f"{preview}\n\n"
                "Relance la commande avec `confirmer: Oui` pour effectuer "
                "l'import.",
                ephemeral=True,
            )
            return

        database = getattr(self.bot, "database", None)

        if database is None:
            await interaction.followup.send(
                "La base de données n'est pas disponible.",
                ephemeral=True,
            )
            return

        try:
            await self.ensure_tables()
        except Exception:
            logger.exception(
                "Impossible de préparer les tables d'import DraftBot."
            )
            await interaction.followup.send(
                "Impossible de préparer la base de données.",
                ephemeral=True,
            )
            return

        newly_imported = 0
        updated = 0
        unchanged = 0
        xp_added = 0

        imported_members: list[tuple[int, int]] = []
        now = datetime.now(timezone.utc)

        try:
            async with database.transaction() as connection:
                for user in users_to_import:
                    converted_xp = convert_draftbot_xp(user)

                    previous = await connection.fetchrow(
                        """
                        SELECT converted_xp
                        FROM draftbot_xp_imports
                        WHERE guild_id = $1
                          AND user_id = $2
                        FOR UPDATE
                        """,
                        interaction.guild.id,
                        user.user_id,
                    )

                    if previous is None:
                        previous_converted_xp = 0
                        newly_imported += 1
                    else:
                        previous_converted_xp = int(
                            previous["converted_xp"]
                        )

                    # Rend l'import idempotent :
                    # relancer le même fichier n'ajoute pas deux fois l'XP.
                    delta = max(
                        0,
                        converted_xp - previous_converted_xp,
                    )

                    stored_converted_xp = max(
                        converted_xp,
                        previous_converted_xp,
                    )

                    if previous is not None:
                        if delta > 0:
                            updated += 1
                        else:
                            unchanged += 1

                    await connection.execute(
                        """
                        INSERT INTO progression_members (
                            guild_id,
                            user_id,
                            total_xp,
                            wallet,
                            lifetime_coins,
                            rewarded_messages,
                            created_at,
                            updated_at
                        )
                        VALUES ($1, $2, 0, 0, 0, 0, $3, $3)
                        ON CONFLICT (guild_id, user_id)
                        DO NOTHING
                        """,
                        interaction.guild.id,
                        user.user_id,
                        now,
                    )

                    resulting_xp = await connection.fetchval(
                        """
                        UPDATE progression_members
                        SET total_xp = total_xp + $3,
                            updated_at = $4
                        WHERE guild_id = $1
                          AND user_id = $2
                        RETURNING total_xp
                        """,
                        interaction.guild.id,
                        user.user_id,
                        delta,
                        now,
                    )

                    await connection.execute(
                        """
                        INSERT INTO draftbot_xp_imports (
                            guild_id,
                            user_id,
                            draftbot_level,
                            draftbot_total_xp,
                            current_xp,
                            next_xp,
                            converted_xp,
                            imported_at,
                            updated_at
                        )
                        VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $8
                        )
                        ON CONFLICT (guild_id, user_id)
                        DO UPDATE SET
                            draftbot_level = EXCLUDED.draftbot_level,
                            draftbot_total_xp =
                                EXCLUDED.draftbot_total_xp,
                            current_xp = EXCLUDED.current_xp,
                            next_xp = EXCLUDED.next_xp,
                            converted_xp = EXCLUDED.converted_xp,
                            updated_at = EXCLUDED.updated_at
                        """,
                        interaction.guild.id,
                        user.user_id,
                        user.level,
                        user.total_xp,
                        user.current_xp,
                        user.next_xp,
                        stored_converted_xp,
                        now,
                    )

                    if delta > 0:
                        await connection.execute(
                            """
                            INSERT INTO progression_transactions (
                                guild_id,
                                user_id,
                                actor_id,
                                transaction_type,
                                amount,
                                reason,
                                created_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            """,
                            interaction.guild.id,
                            user.user_id,
                            interaction.user.id,
                            "draftbot_import",
                            delta,
                            (
                                "Import de la progression DraftBot "
                                f"(niveau {user.level})"
                            ),
                            now,
                        )

                    xp_added += delta

                    if resulting_xp is not None:
                        imported_members.append(
                            (user.user_id, int(resulting_xp))
                        )

        except Exception:
            logger.exception("Échec de l'import DraftBot.")
            await interaction.followup.send(
                "Une erreur est survenue pendant l'import. "
                "Aucune modification partielle n'a été conservée.",
                ephemeral=True,
            )
            return

        roles_added = 0
        role_errors = 0

        if attribuer_roles:
            progression_cog = self.bot.get_cog("ProgressionCog")

            if progression_cog is None:
                role_errors = len(imported_members)
            else:
                for user_id, total_xp in imported_members:
                    member = interaction.guild.get_member(user_id)

                    if member is None:
                        continue

                    try:
                        level = level_from_xp(total_xp)

                        await progression_cog.grant_earned_level_roles(
                            member,
                            level,
                        )

                        roles_added += 1
                    except Exception:
                        role_errors += 1
                        logger.exception(
                            "Impossible de synchroniser les rôles de %s.",
                            user_id,
                        )

        result = (
            "## Import DraftBot terminé\n"
            f"**Membres lus :** {len(users)}\n"
            f"**Membres traités :** {len(users_to_import)}\n"
            f"**Nouveaux imports :** {newly_imported}\n"
            f"**Imports mis à jour :** {updated}\n"
            f"**Déjà à jour :** {unchanged}\n"
            f"**XP ajoutée :** {xp_added:,}\n"
            f"**Membres absents ignorés :** "
            f"{len(absent_users) if membres_presents_seulement else 0}"
        )

        if attribuer_roles:
            result += (
                f"\n**Rôles synchronisés :** {roles_added}"
                f"\n**Erreurs de rôles :** {role_errors}"
            )

        await interaction.followup.send(
            result,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    cog = DraftBotImportCog(bot)
    await cog.ensure_tables()
    await bot.add_cog(cog)
