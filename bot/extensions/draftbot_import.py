from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.extensions.progression import level_from_xp, xp_for_level


# ---------------------------------------------------------------------------
# Parsing du HTML DraftBot
# ---------------------------------------------------------------------------

LI_PATTERN = re.compile(
    r"<li\b(?P<attrs>[^>]*)>(?P<body>.*?)</li>",
    re.IGNORECASE | re.DOTALL,
)

ID_PATTERN = re.compile(
    r'\bid=["\'](?P<id>\d+)["\']',
    re.IGNORECASE,
)

CLASS_PATTERN = re.compile(
    r'\bclass=["\'](?P<class>[^"\']*)["\']',
    re.IGNORECASE,
)

USERNAME_PATTERN = re.compile(
    r'<span\b[^>]*class=["\'][^"\']*\busername\b[^"\']*["\'][^>]*>'
    r"(?P<username>.*?)"
    r"</span>",
    re.IGNORECASE | re.DOTALL,
)

LEVEL_PATTERN = re.compile(
    r'<div\b[^>]*class=["\'][^"\']*\blevel\b[^"\']*["\'][^>]*>'
    r"\s*<span\b[^>]*>\s*(?P<level>\d+)\s*</span>",
    re.IGNORECASE | re.DOTALL,
)

STAT_PATTERN = re.compile(
    r'<div\b[^>]*class=["\'][^"\']*\bvalue\b[^"\']*["\'][^>]*>'
    r"(?P<value>.*?)"
    r"</div>\s*"
    r'<div\b[^>]*class=["\'][^"\']*\btitle\b[^"\']*["\'][^>]*>'
    r"(?P<title>Total|Actuel|Prochain)"
    r"</div>",
    re.IGNORECASE | re.DOTALL,
)

PLACE_PATTERN = re.compile(
    r'\bplace=["\']?(?P<place>\d+)["\']?',
    re.IGNORECASE,
)

TAG_PATTERN = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class DraftBotUser:
    user_id: int
    username: str
    level: int
    total_xp_displayed: int
    current_xp: int
    next_xp: int
    place: int

    @property
    def exact_total_xp(self) -> int:
        """
        Calcule l'XP exacte DraftBot.

        Le total affiché par DraftBot peut être arrondi, par exemple 177,7 k.
        En revanche, le niveau et l'XP actuelle sont exacts.

        Pour Sinj :
        - niveau 43
        - début du niveau 43 : 177 375 XP
        - XP actuelle : 327
        - total exact : 177 702 XP
        """
        level_start = xp_for_level(self.level)
        next_level_start = xp_for_level(self.level + 1)
        level_size = next_level_start - level_start

        current_xp = max(0, self.current_xp)

        # Empêche une donnée HTML incohérente de faire dépasser le niveau.
        if level_size > 0:
            current_xp = min(current_xp, level_size - 1)

        return level_start + current_xp


def clean_text(value: str) -> str:
    value = TAG_PATTERN.sub("", value)
    value = html.unescape(value)
    return value.strip()


def parse_number(value: str) -> int:
    """
    Convertit notamment :
    - "177,7 k" en 177700
    - "11,2 k" en 11200
    - "327" en 327
    """
    value = clean_text(value)
    value = value.replace("\xa0", " ")
    value = value.strip().lower()

    multiplier = 1

    if value.endswith("k"):
        multiplier = 1_000
        value = value[:-1]
    elif value.endswith("m"):
        multiplier = 1_000_000
        value = value[:-1]

    value = value.strip()
    value = value.replace(" ", "")
    value = value.replace(",", ".")

    if not value:
        return 0

    try:
        return round(float(value) * multiplier)
    except ValueError:
        return 0


def parse_draftbot_html(content: str) -> list[DraftBotUser]:
    users: dict[int, DraftBotUser] = {}
    automatic_place = 0

    for li_match in LI_PATTERN.finditer(content):
        attrs = li_match.group("attrs")
        body = li_match.group("body")

        class_match = CLASS_PATTERN.search(attrs)

        if class_match is None:
            continue

        classes = class_match.group("class").split()

        if "user-element" not in classes:
            continue

        id_match = ID_PATTERN.search(attrs)
        username_match = USERNAME_PATTERN.search(body)
        level_match = LEVEL_PATTERN.search(body)

        if id_match is None or username_match is None or level_match is None:
            continue

        automatic_place += 1

        user_id = int(id_match.group("id"))
        username = clean_text(username_match.group("username"))
        level = int(level_match.group("level"))

        stats: dict[str, int] = {}

        for stat_match in STAT_PATTERN.finditer(body):
            title = clean_text(stat_match.group("title")).lower()
            value = parse_number(stat_match.group("value"))
            stats[title] = value

        place_match = PLACE_PATTERN.search(body)
        place = (
            int(place_match.group("place"))
            if place_match is not None
            else automatic_place
        )

        users[user_id] = DraftBotUser(
            user_id=user_id,
            username=username or f"Utilisateur {user_id}",
            level=level,
            total_xp_displayed=stats.get("total", 0),
            current_xp=stats.get("actuel", 0),
            next_xp=stats.get("prochain", 0),
            place=place,
        )

    return sorted(users.values(), key=lambda user: user.place)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class DraftBotImportCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def ensure_tables(self) -> None:
        pool = self.bot.database.require_pool()

        async with pool.acquire() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS draftbot_xp_imports (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    draftbot_level INTEGER NOT NULL,
                    draftbot_total_xp BIGINT NOT NULL,
                    current_xp BIGINT NOT NULL DEFAULT 0,
                    next_xp BIGINT NOT NULL DEFAULT 0,
                    converted_xp BIGINT NOT NULL,
                    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )

            # Compatibilité si la table vient d'une ancienne version.
            await connection.execute(
                """
                ALTER TABLE draftbot_xp_imports
                ADD COLUMN IF NOT EXISTS current_xp BIGINT NOT NULL DEFAULT 0
                """
            )

            await connection.execute(
                """
                ALTER TABLE draftbot_xp_imports
                ADD COLUMN IF NOT EXISTS next_xp BIGINT NOT NULL DEFAULT 0
                """
            )

            await connection.execute(
                """
                ALTER TABLE draftbot_xp_imports
                ADD COLUMN IF NOT EXISTS converted_xp BIGINT NOT NULL DEFAULT 0
                """
            )

            await connection.execute(
                """
                ALTER TABLE draftbot_xp_imports
                ADD COLUMN IF NOT EXISTS imported_at TIMESTAMPTZ
                NOT NULL DEFAULT NOW()
                """
            )

            await connection.execute(
                """
                ALTER TABLE draftbot_xp_imports
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
                NOT NULL DEFAULT NOW()
                """
            )

    @app_commands.command(
        name="import_draftbot",
        description="Importe les niveaux et l'XP depuis un fichier HTML DraftBot.",
    )
    @app_commands.describe(
        fichier="Le fichier HTML contenant le classement DraftBot",
        confirmer="Mettre Oui pour effectuer réellement l'import",
        remplacer_xp_existante=(
            "Oui pour remplacer l'XP du bot par l'XP exacte DraftBot"
        ),
        membres_presents_seulement=(
            "Importer seulement les utilisateurs encore présents sur le serveur"
        ),
        attribuer_roles="Attribuer les rôles de niveau après l'import",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def import_draftbot(
        self,
        interaction: discord.Interaction,
        fichier: discord.Attachment,
        confirmer: bool = False,
        remplacer_xp_existante: bool = False,
        membres_presents_seulement: bool = True,
        attribuer_roles: bool = False,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "Cette commande doit être utilisée sur un serveur.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Impossible de vérifier tes permissions.",
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Tu dois être administrateur pour utiliser cette commande.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            raw_content = await fichier.read()
        except discord.HTTPException as error:
            await interaction.followup.send(
                f"Impossible de télécharger le fichier : `{error}`",
                ephemeral=True,
            )
            return

        try:
            content = raw_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw_content.decode("utf-8", errors="replace")

        users = parse_draftbot_html(content)

        if not users:
            await interaction.followup.send(
                "Aucun utilisateur DraftBot n'a été trouvé dans le fichier.",
                ephemeral=True,
            )
            return

        guild_member_ids = {member.id for member in guild.members}

        selected_users: list[DraftBotUser] = []
        ignored_absent = 0

        for user in users:
            if (
                membres_presents_seulement
                and user.user_id not in guild_member_ids
            ):
                ignored_absent += 1
                continue

            selected_users.append(user)

        if not selected_users:
            await interaction.followup.send(
                "Aucun utilisateur du fichier n'est présent sur le serveur.",
                ephemeral=True,
            )
            return

        # -------------------------------------------------------------------
        # Prévisualisation
        # -------------------------------------------------------------------

        if not confirmer:
            preview_lines: list[str] = []

            for user in selected_users[:10]:
                preview_lines.append(
                    f"**{user.place}. {discord.utils.escape_markdown(user.username)}** "
                    f"— niveau `{user.level}` "
                    f"— XP exacte `{user.exact_total_xp:,}`"
                )

            mode = (
                "remplacement total de l'XP"
                if remplacer_xp_existante
                else "fusion/correction de l'import précédent"
            )

            message = (
                "### Prévisualisation de l'import DraftBot\n"
                f"Utilisateurs trouvés dans le fichier : **{len(users)}**\n"
                f"Utilisateurs qui seront importés : **{len(selected_users)}**\n"
                f"Utilisateurs absents ignorés : **{ignored_absent}**\n"
                f"Mode : **{mode}**\n\n"
                + "\n".join(preview_lines)
            )

            if len(selected_users) > 10:
                message += (
                    f"\n\n… et **{len(selected_users) - 10}** autres utilisateurs."
                )

            message += (
                "\n\nRelance la commande avec `confirmer: Oui` "
                "pour effectuer l'import."
            )

            await interaction.followup.send(message, ephemeral=True)
            return

        # -------------------------------------------------------------------
        # Import
        # -------------------------------------------------------------------

        pool = self.bot.database.require_pool()
        now = datetime.now(timezone.utc)

        newly_imported = 0
        corrected_imports = 0
        unchanged_imports = 0
        progression_modified = 0
        total_applied_delta = 0

        imported_results: list[tuple[DraftBotUser, int]] = []

        async with pool.acquire() as connection:
            async with connection.transaction():
                for user in selected_users:
                    exact_xp = user.exact_total_xp

                    # Création du profil local s'il n'existe pas.
                    await connection.execute(
                        """
                        INSERT INTO progression_members (
                            guild_id,
                            user_id,
                            total_xp,
                            wallet,
                            lifetime_coins,
                            rewarded_messages,
                            last_reward_at,
                            created_at,
                            updated_at
                        )
                        VALUES (
                            $1,
                            $2,
                            0,
                            0,
                            0,
                            0,
                            NULL,
                            $3,
                            $3
                        )
                        ON CONFLICT (guild_id, user_id)
                        DO NOTHING
                        """,
                        guild.id,
                        user.user_id,
                        now,
                    )

                    current_local_xp = await connection.fetchval(
                        """
                        SELECT total_xp
                        FROM progression_members
                        WHERE guild_id = $1
                          AND user_id = $2
                        FOR UPDATE
                        """,
                        guild.id,
                        user.user_id,
                    )

                    current_local_xp = int(current_local_xp or 0)

                    previous_import = await connection.fetchrow(
                        """
                        SELECT converted_xp
                        FROM draftbot_xp_imports
                        WHERE guild_id = $1
                          AND user_id = $2
                        FOR UPDATE
                        """,
                        guild.id,
                        user.user_id,
                    )

                    if remplacer_xp_existante:
                        # Le total local devient exactement le total DraftBot.
                        applied_delta = exact_xp - current_local_xp

                        resulting_xp = await connection.fetchval(
                            """
                            UPDATE progression_members
                            SET total_xp = $3,
                                updated_at = $4
                            WHERE guild_id = $1
                              AND user_id = $2
                            RETURNING total_xp
                            """,
                            guild.id,
                            user.user_id,
                            exact_xp,
                            now,
                        )
                    else:
                        # Première importation : ajoute toute l'XP DraftBot.
                        #
                        # Importation suivante : applique seulement la différence
                        # avec la précédente importation. Cela empêche de doubler
                        # l'XP en relançant la commande.
                        previous_converted_xp = (
                            int(previous_import["converted_xp"])
                            if previous_import is not None
                            else 0
                        )

                        applied_delta = exact_xp - previous_converted_xp

                        resulting_xp = await connection.fetchval(
                            """
                            UPDATE progression_members
                            SET total_xp = GREATEST(0, total_xp + $3),
                                updated_at = $4
                            WHERE guild_id = $1
                              AND user_id = $2
                            RETURNING total_xp
                            """,
                            guild.id,
                            user.user_id,
                            applied_delta,
                            now,
                        )

                    resulting_xp = int(resulting_xp or 0)

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
                            $1,
                            $2,
                            $3,
                            $4,
                            $5,
                            $6,
                            $7,
                            $8,
                            $8
                        )
                        ON CONFLICT (guild_id, user_id)
                        DO UPDATE SET
                            draftbot_level = EXCLUDED.draftbot_level,
                            draftbot_total_xp = EXCLUDED.draftbot_total_xp,
                            current_xp = EXCLUDED.current_xp,
                            next_xp = EXCLUDED.next_xp,
                            converted_xp = EXCLUDED.converted_xp,
                            updated_at = EXCLUDED.updated_at
                        """,
                        guild.id,
                        user.user_id,
                        user.level,
                        user.total_xp_displayed,
                        user.current_xp,
                        user.next_xp,
                        exact_xp,
                        now,
                    )

                    if previous_import is None:
                        newly_imported += 1
                    elif int(previous_import["converted_xp"]) != exact_xp:
                        corrected_imports += 1
                    else:
                        unchanged_imports += 1

                    if applied_delta != 0:
                        progression_modified += 1

                    total_applied_delta += applied_delta
                    imported_results.append((user, resulting_xp))

        # -------------------------------------------------------------------
        # Attribution facultative des rôles
        # -------------------------------------------------------------------

        roles_updated = 0
        role_errors = 0
        role_warning: str | None = None

        if attribuer_roles:
            progression_cog = self.bot.get_cog("ProgressionCog")

            if progression_cog is None:
                role_warning = (
                    "Le module de progression n'a pas été trouvé : "
                    "les rôles n'ont pas été attribués."
                )
            else:
                grant_roles = getattr(
                    progression_cog,
                    "grant_earned_level_roles",
                    None,
                )

                if grant_roles is None:
                    role_warning = (
                        "La fonction d'attribution des rôles n'a pas été trouvée."
                    )
                else:
                    for user, resulting_xp in imported_results:
                        member = guild.get_member(user.user_id)

                        if member is None:
                            continue

                        try:
                            resulting_level = level_from_xp(resulting_xp)
                            await grant_roles(member, resulting_level)
                            roles_updated += 1
                        except Exception:
                            role_errors += 1

        delta_display = f"{total_applied_delta:+,}".replace(",", " ")

        result_message = (
            "### Import DraftBot terminé\n"
            f"Utilisateurs traités : **{len(selected_users)}**\n"
            f"Nouvelles importations : **{newly_imported}**\n"
            f"Importations corrigées : **{corrected_imports}**\n"
            f"Importations déjà à jour : **{unchanged_imports}**\n"
            f"Profils dont l'XP a été modifiée : **{progression_modified}**\n"
            f"Variation totale appliquée : **{delta_display} XP**\n"
            f"Utilisateurs absents ignorés : **{ignored_absent}**"
        )

        if remplacer_xp_existante:
            result_message += (
                "\nMode utilisé : **remplacement par l'XP exacte DraftBot**"
            )
        else:
            result_message += (
                "\nMode utilisé : **fusion/correction sans double import**"
            )

        if attribuer_roles:
            result_message += (
                f"\nRôles vérifiés : **{roles_updated}**"
                f"\nErreurs de rôles : **{role_errors}**"
            )

        if role_warning:
            result_message += f"\n\n⚠️ {role_warning}"

        await interaction.followup.send(result_message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    cog = DraftBotImportCog(bot)
    await cog.ensure_tables()
    await bot.add_cog(cog)
