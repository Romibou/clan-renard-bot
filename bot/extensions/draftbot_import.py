from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.database import Database


logger = logging.getLogger(__name__)


DRAFTBOT_GUILD_ID = 733277977831407628


# Format :
# (
#     user_id,
#     niveau DraftBot,
#     XP total affiché par DraftBot,
# )
DRAFTBOT_USERS: tuple[tuple[int, int, int], ...] = (
    (733260131047047200, 43, 177_700),
    (425582105125322763, 39, 140_300),
    (1521621217079984311, 37, 125_900),
    (760182467361243186, 36, 113_200),
    (765578266295271445, 34, 100_000),
    (594105847941169152, 32, 81_200),
    (1430527773218181194, 24, 39_300),
    (891260015489466388, 22, 31_700),
    (347444894119493653, 19, 22_900),
    (566294850786426901, 18, 19_900),
    (1103728053923876895, 16, 15_200),
    (778585584583180308, 16, 14_900),
    (1235230812660699288, 11, 6_900),
    (1369361071437254697, 11, 6_200),
    (1215371540959330434, 11, 6_000),
    (851182904792580146, 11, 5_800),
    (1408904284489121902, 10, 5_600),
    (694178411618238514, 9, 3_900),
    (1018920833198075967, 9, 3_900),
    (1403486118657396776, 6, 2_100),
    (1147908324822622228, 6, 2_100),
    (510505225971302410, 6, 2_000),
    (1416692779446177903, 6, 1_800),
    (1353122014008967328, 6, 1_700),
    (684857177277857865, 6, 1_700),
    (1295288602560827402, 5, 1_500),
    (808341156751474698, 4, 1_000),
    (1099003523984805898, 4, 943),
    (1342493160785313862, 4, 902),
    (689503785684435127, 4, 887),
    (767074436557045811, 4, 846),
    (975082117061046302, 4, 818),
    (1392969249198444624, 3, 700),
    (1217139224629874754, 3, 646),
    (1258905263428210739, 3, 634),
    (1495869256649277503, 3, 597),
    (1154103857958367353, 3, 595),
    (1298429647603892247, 3, 551),
    (1096140548894634115, 3, 512),
    (1350028860099661825, 3, 495),
    (1278774786360741938, 3, 491),
    (1014918277509685280, 2, 467),
    (1265105058203439164, 2, 425),
    (1373385422406811670, 2, 408),
    (883435111947837523, 2, 390),
    (1135229297611780166, 2, 382),
    (1117112126499196980, 2, 366),
    (1310295225477890190, 2, 351),
    (1406688863799345153, 2, 350),
    (1442847390339043380, 2, 345),
)


def draftbot_xp_for_level(level: int) -> int:
    """
    XP total nécessaire pour atteindre un niveau sur DraftBot.

    DraftBot utilise approximativement :
        XP nécessaire pour passer le niveau L
        = 5L² + 50L + 100
    """
    level = max(0, level)

    if level == 0:
        return 0

    square_sum = (
        (level - 1)
        * level
        * (2 * level - 1)
        // 6
    )

    linear_sum = level * (level - 1) // 2

    return (
        5 * square_sum
        + 50 * linear_sum
        + 100 * level
    )


def draftbot_xp_required_for_next_level(
    level: int,
) -> int:
    level = max(0, level)

    return (
        5 * level * level
        + 50 * level
        + 100
    )


def local_xp_for_level(level: int) -> int:
    """
    Formule actuellement utilisée par ton système :

        niveau = sqrt(total_xp / 100)

    Donc :
        XP du niveau L = 100 × L²
    """
    level = max(0, level)
    return 100 * level * level


def convert_draftbot_xp(
    *,
    draftbot_level: int,
    draftbot_total_xp: int,
) -> int:
    """
    Convertit l'XP DraftBot vers ton système.

    Le niveau et le pourcentage de progression sont conservés.
    """
    draftbot_level = max(0, draftbot_level)
    draftbot_total_xp = max(0, draftbot_total_xp)

    draftbot_level_start = draftbot_xp_for_level(
        draftbot_level
    )

    draftbot_level_size = (
        draftbot_xp_required_for_next_level(
            draftbot_level
        )
    )

    draftbot_current_xp = max(
        0,
        draftbot_total_xp - draftbot_level_start,
    )

    # Les valeurs en "k" du site sont arrondies.
    # On empêche donc la conversion de dépasser le niveau affiché.
    draftbot_current_xp = min(
        draftbot_current_xp,
        max(0, draftbot_level_size - 1),
    )

    if draftbot_level_size <= 0:
        progress = 0.0
    else:
        progress = (
            draftbot_current_xp
            / draftbot_level_size
        )

    local_level_start = local_xp_for_level(
        draftbot_level
    )

    local_next_level_start = local_xp_for_level(
        draftbot_level + 1
    )

    local_level_size = (
        local_next_level_start
        - local_level_start
    )

    converted_progress = int(
        progress * local_level_size
    )

    converted_progress = min(
        converted_progress,
        max(0, local_level_size - 1),
    )

    return (
        local_level_start
        + converted_progress
    )


async def ensure_import_table(
    database: Database,
) -> None:
    """
    Cette table rend l'importation idempotente.

    Si tu lances deux fois la commande, l'XP ne sera pas
    ajoutée deux fois.
    """
    await database.execute(
        """
        CREATE TABLE IF NOT EXISTS draftbot_xp_imports (
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            draftbot_level INTEGER NOT NULL,
            draftbot_total_xp BIGINT NOT NULL,
            converted_xp BIGINT NOT NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            PRIMARY KEY (guild_id, user_id)
        )
        """
    )


class DraftBotImport(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        database: Database,
    ) -> None:
        self.bot = bot
        self.database = database

    async def _update_level_roles(
        self,
        guild: discord.Guild,
    ) -> tuple[int, int]:
        """
        Tente d'attribuer les rôles de niveau après l'import.

        L'échec d'un rôle n'annule pas l'importation de l'XP.
        """
        progression_cog = self.bot.get_cog(
            "Progression"
        )

        if progression_cog is None:
            progression_cog = self.bot.get_cog(
                "ProgressionCog"
            )

        if progression_cog is None:
            logger.warning(
                "Cog de progression introuvable : "
                "les rôles seront vérifiés au prochain gain d'XP."
            )
            return 0, 0

        role_handler = getattr(
            progression_cog,
            "grant_earned_level_roles",
            None,
        )

        if role_handler is None:
            logger.warning(
                "La méthode grant_earned_level_roles "
                "est introuvable."
            )
            return 0, 0

        success_count = 0
        error_count = 0

        for user_id, _, _ in DRAFTBOT_USERS:
            member = guild.get_member(user_id)

            if member is None:
                continue

            try:
                await role_handler(member)
                success_count += 1
            except Exception:
                error_count += 1

                logger.exception(
                    "Impossible de vérifier les rôles "
                    "de niveau de %s",
                    user_id,
                )

        return success_count, error_count

    @app_commands.command(
        name="import-draftbot-xp",
        description=(
            "Importe une seule fois l'XP de l'ancien classement."
        ),
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(
        administrator=True
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def import_draftbot_xp(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Cette commande doit être utilisée "
                "dans un serveur.",
                ephemeral=True,
            )
            return

        if interaction.guild.id != DRAFTBOT_GUILD_ID:
            await interaction.response.send_message(
                "❌ Ces données DraftBot n'appartiennent "
                "pas à ce serveur.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        pool = self.database.require_pool()

        imported_count = 0
        updated_count = 0
        unchanged_count = 0
        total_added = 0

        try:
            async with pool.acquire() as connection:
                async with connection.transaction():
                    for (
                        user_id,
                        draftbot_level,
                        draftbot_total_xp,
                    ) in DRAFTBOT_USERS:
                        converted_xp = convert_draftbot_xp(
                            draftbot_level=draftbot_level,
                            draftbot_total_xp=(
                                draftbot_total_xp
                            ),
                        )

                        previous_import = (
                            await connection.fetchrow(
                                """
                                SELECT converted_xp
                                FROM draftbot_xp_imports
                                WHERE guild_id = $1
                                  AND user_id = $2
                                """,
                                interaction.guild.id,
                                user_id,
                            )
                        )

                        if previous_import is None:
                            previous_converted_xp = 0
                            imported_count += 1
                        else:
                            previous_converted_xp = int(
                                previous_import[
                                    "converted_xp"
                                ]
                            )

                        difference = (
                            converted_xp
                            - previous_converted_xp
                        )

                        if difference == 0:
                            unchanged_count += 1
                        else:
                            updated_count += 1
                            total_added += difference

                        # Adapte uniquement le nom de cette table
                        # si ta table de progression porte un autre nom.
                        await connection.execute(
                            """
                            INSERT INTO progression_members (
                                guild_id,
                                user_id,
                                total_xp,
                                coins
                            )
                            VALUES ($1, $2, 0, 0)
                            ON CONFLICT (guild_id, user_id)
                            DO NOTHING
                            """,
                            interaction.guild.id,
                            user_id,
                        )

                        if difference != 0:
                            await connection.execute(
                                """
                                UPDATE progression_members
                                SET total_xp = GREATEST(
                                        0,
                                        total_xp + $3
                                    ),
                                    updated_at = NOW()
                                WHERE guild_id = $1
                                  AND user_id = $2
                                """,
                                interaction.guild.id,
                                user_id,
                                difference,
                            )

                        await connection.execute(
                            """
                            INSERT INTO draftbot_xp_imports (
                                guild_id,
                                user_id,
                                draftbot_level,
                                draftbot_total_xp,
                                converted_xp,
                                imported_at,
                                updated_at
                            )
                            VALUES (
                                $1,
                                $2,
                                $3,
                                $4,
                                $5,
                                NOW(),
                                NOW()
                            )
                            ON CONFLICT (guild_id, user_id)
                            DO UPDATE SET
                                draftbot_level =
                                    EXCLUDED.draftbot_level,
                                draftbot_total_xp =
                                    EXCLUDED.draftbot_total_xp,
                                converted_xp =
                                    EXCLUDED.converted_xp,
                                updated_at = NOW()
                            """,
                            interaction.guild.id,
                            user_id,
                            draftbot_level,
                            draftbot_total_xp,
                            converted_xp,
                        )

            role_success, role_errors = (
                await self._update_level_roles(
                    interaction.guild
                )
            )

        except Exception:
            logger.exception(
                "Impossible d'importer les données DraftBot"
            )

            await interaction.followup.send(
                (
                    "❌ L'importation DraftBot a échoué.\n"
                    "Regarde les logs Render pour obtenir "
                    "l'erreur complète."
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            (
                "✅ **Importation DraftBot terminée**\n\n"
                f"• Nouveaux membres importés : "
                f"**{imported_count}**\n"
                f"• Entrées mises à jour : "
                f"**{updated_count}**\n"
                f"• Entrées déjà à jour : "
                f"**{unchanged_count}**\n"
                f"• Différence totale ajoutée : "
                f"**{total_added:,} XP**\n"
                f"• Membres vérifiés pour les rôles : "
                f"**{role_success}**\n"
                f"• Erreurs de rôles : "
                f"**{role_errors}**\n\n"
                "La commande peut être relancée sans "
                "dupliquer l'XP."
            ).replace(",", " "),
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    database = getattr(bot, "database", None)

    if not isinstance(database, Database):
        raise RuntimeError(
            "La base de données du bot est introuvable."
        )

    await ensure_import_table(database)

    await bot.add_cog(
        DraftBotImport(
            bot,
            database,
        )
    )

    logger.info(
        "Outil d'importation DraftBot chargé"
    )


async def teardown(
    bot: commands.Bot,
) -> None:
    logger.info(
        "Outil d'importation DraftBot déchargé"
    )
