from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands


LOGGER = logging.getLogger(__name__)

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")

COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
WARNING_COLOR = discord.Color.from_rgb(235, 174, 65)

ALLOWED_PERIODS = {
    "daily",
    "weekly",
}

ALLOWED_METRICS = {
    "messages",
    "voice_minutes",
    "xp",
    "coins",
    "daily_claims",
    "streak",
}

MAXIMUM_MISSIONS = 25
MAXIMUM_NAME_LENGTH = 100
MAXIMUM_DESCRIPTION_LENGTH = 250
MAXIMUM_TARGET = 1_000_000_000
MAXIMUM_REWARD = 1_000_000_000


def error_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=ERROR_COLOR,
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


def warning_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=WARNING_COLOR,
    )


def base_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=COLOR,
    )


def current_paris_date() -> date:
    return datetime.now(
        PARIS_TIMEZONE
    ).date()


def get_period_key(
    period: str,
) -> str:
    today = current_paris_date()

    if period == "daily":
        return today.isoformat()

    monday = today - timedelta(
        days=today.weekday()
    )

    return monday.isoformat()


def format_number(
    value: int,
) -> str:
    return f"{int(value):,}".replace(
        ",",
        " ",
    )


def format_metric(
    metric: str,
) -> str:
    labels = {
        "messages": "messages",
        "voice_minutes": "minutes vocales",
        "xp": "XP",
        "coins": "pièces",
        "daily_claims": "récompenses quotidiennes",
        "streak": "jours de série",
    }

    return labels.get(
        metric,
        metric,
    )


def format_progress_value(
    metric: str,
    value: int,
) -> str:
    if metric == "voice_minutes":
        hours, minutes = divmod(
            max(0, int(value)),
            60,
        )

        if hours > 0:
            return f"{hours} h {minutes:02d}"

        return f"{minutes} min"

    if metric == "xp":
        return f"{format_number(value)} XP"

    if metric == "coins":
        return f"{format_number(value)} pièces"

    return format_number(value)


def normalize_missions(
    raw_value: str | list[Any],
) -> list[dict[str, Any]]:
    if isinstance(
        raw_value,
        str,
    ):
        try:
            decoded = json.loads(
                raw_value
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                (
                    "JSON invalide à la ligne "
                    f"{error.lineno}, colonne {error.colno}."
                )
            ) from error
    else:
        decoded = raw_value

    if not isinstance(
        decoded,
        list,
    ):
        raise ValueError(
            "La configuration doit être une liste JSON."
        )

    if len(decoded) > MAXIMUM_MISSIONS:
        raise ValueError(
            (
                f"Tu peux configurer au maximum "
                f"{MAXIMUM_MISSIONS} missions."
            )
        )

    normalized: list[dict[str, Any]] = []
    identifiers: set[str] = set()

    allowed_keys = {
        "id",
        "period",
        "name",
        "description",
        "metric",
        "target",
        "reward_xp",
        "reward_coins",
        "reward_cosmetic_id",
    }

    for index, raw_mission in enumerate(
        decoded,
        start=1,
    ):
        if not isinstance(
            raw_mission,
            dict,
        ):
            raise ValueError(
                f"La mission n°{index} doit être un objet JSON."
            )

        unknown_keys = set(raw_mission) - allowed_keys

        if unknown_keys:
            raise ValueError(
                (
                    f"La mission n°{index} contient des champs "
                    f"inconnus : {', '.join(sorted(unknown_keys))}."
                )
            )

        mission_id = str(
            raw_mission.get(
                "id",
                "",
            )
        ).strip().lower()

        if not mission_id:
            raise ValueError(
                f"La mission n°{index} doit avoir un identifiant."
            )

        if len(mission_id) > 50:
            raise ValueError(
                (
                    f"L'identifiant de la mission n°{index} "
                    "ne peut pas dépasser 50 caractères."
                )
            )

        if mission_id in identifiers:
            raise ValueError(
                f"L'identifiant `{mission_id}` est utilisé plusieurs fois."
            )

        identifiers.add(mission_id)

        period = str(
            raw_mission.get(
                "period",
                "daily",
            )
        ).strip().lower()

        if period not in ALLOWED_PERIODS:
            raise ValueError(
                (
                    f"La période de la mission `{mission_id}` "
                    "doit être `daily` ou `weekly`."
                )
            )

        name = str(
            raw_mission.get(
                "name",
                mission_id,
            )
        ).strip()

        if not name:
            name = mission_id

        if len(name) > MAXIMUM_NAME_LENGTH:
            raise ValueError(
                (
                    f"Le nom de la mission `{mission_id}` "
                    f"ne peut pas dépasser {MAXIMUM_NAME_LENGTH} caractères."
                )
            )

        description = str(
            raw_mission.get(
                "description",
                "",
            )
        ).strip()

        if len(description) > MAXIMUM_DESCRIPTION_LENGTH:
            raise ValueError(
                (
                    f"La description de la mission `{mission_id}` "
                    f"ne peut pas dépasser "
                    f"{MAXIMUM_DESCRIPTION_LENGTH} caractères."
                )
            )

        metric = str(
            raw_mission.get(
                "metric",
                "",
            )
        ).strip().lower()

        if metric not in ALLOWED_METRICS:
            raise ValueError(
                (
                    f"La métrique de `{mission_id}` est invalide.\n"
                    f"Métriques autorisées : "
                    f"{', '.join(sorted(ALLOWED_METRICS))}."
                )
            )

        try:
            target = int(
                raw_mission.get(
                    "target",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                f"La cible de `{mission_id}` doit être un entier."
            ) from error

        if not 1 <= target <= MAXIMUM_TARGET:
            raise ValueError(
                (
                    f"La cible de `{mission_id}` doit être comprise "
                    f"entre 1 et {format_number(MAXIMUM_TARGET)}."
                )
            )

        try:
            reward_xp = int(
                raw_mission.get(
                    "reward_xp",
                    0,
                )
            )

            reward_coins = int(
                raw_mission.get(
                    "reward_coins",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                (
                    f"Les récompenses de `{mission_id}` "
                    "doivent être des entiers."
                )
            ) from error

        if not 0 <= reward_xp <= MAXIMUM_REWARD:
            raise ValueError(
                f"La récompense XP de `{mission_id}` est invalide."
            )

        if not 0 <= reward_coins <= MAXIMUM_REWARD:
            raise ValueError(
                f"La récompense en pièces de `{mission_id}` est invalide."
            )

        reward_cosmetic_id = raw_mission.get(
            "reward_cosmetic_id"
        )

        if reward_cosmetic_id in (
            None,
            "",
        ):
            reward_cosmetic_id = None
        else:
            try:
                reward_cosmetic_id = int(
                    reward_cosmetic_id
                )
            except (
                TypeError,
                ValueError,
            ) as error:
                raise ValueError(
                    (
                        f"`reward_cosmetic_id` de `{mission_id}` "
                        "doit être un identifiant numérique."
                    )
                ) from error

            if reward_cosmetic_id <= 0:
                raise ValueError(
                    (
                        f"`reward_cosmetic_id` de `{mission_id}` "
                        "est invalide."
                    )
                )

        if (
            reward_xp == 0
            and reward_coins == 0
            and reward_cosmetic_id is None
        ):
            raise ValueError(
                (
                    f"La mission `{mission_id}` ne donne "
                    "aucune récompense."
                )
            )

        normalized.append(
            {
                "id": mission_id,
                "period": period,
                "name": name,
                "description": description,
                "metric": metric,
                "target": target,
                "reward_xp": reward_xp,
                "reward_coins": reward_coins,
                "reward_cosmetic_id": reward_cosmetic_id,
            }
        )

    return normalized


class MissionsConfigModal(
    discord.ui.Modal,
    title="Configuration des missions",
):
    def __init__(
        self,
        *,
        cog: MissionsCog,
        guild_id: int,
        current_missions: list[dict[str, Any]],
    ) -> None:
        super().__init__(
            timeout=600,
        )

        self.cog = cog
        self.guild_id = guild_id

        serialized = json.dumps(
            current_missions,
            ensure_ascii=False,
            indent=2,
        )

        if len(serialized) > 4000:
            serialized = "[]"

        self.configuration = discord.ui.TextInput(
            label="Missions en JSON",
            placeholder="Colle ici la configuration JSON des missions",
            default=serialized,
            style=discord.TextStyle.paragraph,
            required=True,
            min_length=2,
            max_length=4000,
        )

        self.add_item(
            self.configuration
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            missions = normalize_missions(
                str(self.configuration.value)
            )

            await self.cog.save_missions(
                guild_id=self.guild_id,
                missions=missions,
            )
        except ValueError as error:
            await interaction.response.send_message(
                embed=error_embed(
                    "Configuration invalide",
                    str(error),
                ),
                ephemeral=True,
            )
            return
        except Exception:
            LOGGER.exception(
                "Impossible d'enregistrer les missions du serveur %s.",
                self.guild_id,
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    "Les missions n'ont pas pu être enregistrées.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Missions enregistrées",
                (
                    f"**{len(missions)} mission(s)** ont été enregistrées.\n\n"
                    "Les anciennes missions absentes du JSON ont été "
                    "désactivées."
                ),
            ),
            ephemeral=True,
        )


class MissionsAdminView(
    discord.ui.View
):
    def __init__(
        self,
        *,
        cog: MissionsCog,
        owner_id: int,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=600,
        )

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
                "Action interdite",
                "Seul l'administrateur ayant ouvert ce panneau peut l'utiliser.",
            ),
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Configurer en JSON",
        emoji="🧩",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def configure(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        missions = await self.cog.get_missions(
            guild_id=self.guild_id,
            enabled_only=False,
        )

        await interaction.response.send_modal(
            MissionsConfigModal(
                cog=self.cog,
                guild_id=self.guild_id,
                current_missions=missions,
            )
        )

    @discord.ui.button(
        label="Activer / désactiver",
        emoji="🔌",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def toggle(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        enabled = await self.cog.toggle_system(
            guild_id=self.guild_id
        )

        await interaction.response.send_message(
            embed=success_embed(
                "État modifié",
                (
                    "Le système de missions est maintenant "
                    f"**{'activé' if enabled else 'désactivé'}**."
                ),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Exemple JSON",
        emoji="📋",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def example(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        example = [
            {
                "id": "messages-daily",
                "period": "daily",
                "name": "Bavard du jour",
                "description": "Envoie des messages sur le serveur.",
                "metric": "messages",
                "target": 20,
                "reward_xp": 100,
                "reward_coins": 25,
            },
            {
                "id": "vocal-weekly",
                "period": "weekly",
                "name": "Présence vocale",
                "description": "Passe du temps dans un salon vocal.",
                "metric": "voice_minutes",
                "target": 120,
                "reward_xp": 250,
                "reward_coins": 75,
            },
            {
                "id": "daily-weekly",
                "period": "weekly",
                "name": "Habitué du quotidien",
                "description": "Récupère plusieurs récompenses quotidiennes.",
                "metric": "daily_claims",
                "target": 5,
                "reward_xp": 300,
                "reward_coins": 100,
            },
            {
                "id": "xp-daily",
                "period": "daily",
                "name": "Petit niveau",
                "description": "Gagne de l'XP aujourd'hui.",
                "metric": "xp",
                "target": 500,
                "reward_xp": 50,
                "reward_coins": 20,
            },
        ]

        json_example = json.dumps(
            example,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        
        await interaction.response.send_message(
            content=(
                "🧩 **Exemple de configuration JSON des missions**\n\n"
                f"```json\n{json_example}\n```\n\n"
                "Tu peux copier ce JSON puis le modifier."
            ),
            ephemeral=True,
        )


    @discord.ui.button(
        label="Voir les missions",
        emoji="👁️",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def list_missions(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        missions = await self.cog.get_missions(
            guild_id=self.guild_id,
            enabled_only=False,
        )

        if not missions:
            await interaction.response.send_message(
                embed=base_embed(
                    "Missions",
                    "Aucune mission n'est configurée.",
                ),
                ephemeral=True,
            )
            return

        lines: list[str] = []

        for mission in missions:
            status = (
                "✅ Activée"
                if mission["enabled"]
                else "❌ Désactivée"
            )

            lines.append(
                (
                    f"**{mission['name']}** — {status}\n"
                    f"ID : `{mission['mission_id']}` · "
                    f"{mission['period']} · "
                    f"{format_metric(mission['metric'])} : "
                    f"{format_number(mission['target'])}\n"
                    f"Récompense : "
                    f"{format_number(mission['reward_xp'])} XP + "
                    f"{format_number(mission['reward_coins'])} pièces"
                )
            )

        await interaction.response.send_message(
            embed=base_embed(
                "📋 Missions configurées",
                "\n\n".join(lines)[:4000],
            ),
            ephemeral=True,
        )


class MissionSelect(
    discord.ui.Select
):
    def __init__(
        self,
        *,
        view: MissionsView,
        missions: list[dict[str, Any]],
    ) -> None:
        self.missions_view = view

        options: list[discord.SelectOption] = []

        for mission in missions[:25]:
            progress = int(
                mission["progress"]
            )

            target = int(
                mission["target"]
            )

            claimed = bool(
                mission["claimed"]
            )

            if claimed:
                status = "Réclamée"
            elif progress >= target:
                status = "Terminée"
            else:
                status = (
                    f"{format_number(progress)}/"
                    f"{format_number(target)}"
                )

            options.append(
                discord.SelectOption(
                    label=str(
                        mission["name"]
                    )[:100],
                    value=str(
                        mission["mission_id"]
                    ),
                    description=status[:100],
                    emoji="✅" if claimed else "🎯",
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="Aucune mission disponible",
                    value="none",
                    description="Aucune mission n'est configurée.",
                    emoji="📭",
                )
            )

        super().__init__(
            placeholder="Choisis une mission à réclamer…",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        selected_id = self.values[0]

        if selected_id == "none":
            await interaction.response.send_message(
                "Aucune mission n'est disponible.",
                ephemeral=True,
            )
            return

        self.missions_view.selected_mission_id = selected_id

        await interaction.response.send_message(
            f"Mission sélectionnée : **{selected_id}**.",
            ephemeral=True,
        )


class MissionsView(
    discord.ui.View
):
    def __init__(
        self,
        *,
        cog: MissionsCog,
        owner_id: int,
        guild_id: int,
        missions: list[dict[str, Any]],
    ) -> None:
        super().__init__(
            timeout=600,
        )

        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.selected_mission_id: str | None = None

        self.add_item(
            MissionSelect(
                view=self,
                missions=missions,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Missions personnelles",
                "Ce menu appartient à un autre membre.",
            ),
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Réclamer",
        emoji="🎁",
        style=discord.ButtonStyle.success,
        row=1,
    )
    async def claim(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.selected_mission_id is None:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Aucune mission sélectionnée",
                    "Choisis une mission dans la liste avant de réclamer.",
                ),
                ephemeral=True,
            )
            return

        try:
            reward = await self.cog.claim_mission(
                guild_id=self.guild_id,
                user_id=self.owner_id,
                mission_id=self.selected_mission_id,
            )
        except ValueError as error:
            await interaction.response.send_message(
                embed=error_embed(
                    "Réclamation impossible",
                    str(error),
                ),
                ephemeral=True,
            )
            return
        except Exception:
            LOGGER.exception(
                (
                    "Impossible de réclamer la mission %s "
                    "pour %s sur %s."
                ),
                self.selected_mission_id,
                self.owner_id,
                self.guild_id,
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    "La récompense n'a pas pu être récupérée.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Mission terminée",
                reward,
            ),
            ephemeral=True,
        )

        await self.refresh_message(
            interaction
        )

    @discord.ui.button(
        label="Actualiser",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def refresh_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.refresh_message(
            interaction
        )

    async def refresh_message(
        self,
        interaction: discord.Interaction,
    ) -> None:
        missions = await self.cog.get_member_missions(
            guild_id=self.guild_id,
            user_id=self.owner_id,
        )

        embed = self.cog.build_member_embed(
            missions
        )

        new_view = MissionsView(
            cog=self.cog,
            owner_id=self.owner_id,
            guild_id=self.guild_id,
            missions=missions,
        )

        await interaction.edit_original_response(
            embed=embed,
            view=new_view,
        )


class MissionsCog(
    commands.Cog
):
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

    async def initialize_database(
        self,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS mission_settings (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS mission_definitions (
                guild_id BIGINT NOT NULL,
                mission_id VARCHAR(50) NOT NULL,

                period VARCHAR(20) NOT NULL
                    CHECK (period IN ('daily', 'weekly')),

                name VARCHAR(100) NOT NULL,
                description VARCHAR(250) NOT NULL DEFAULT '',

                metric VARCHAR(30) NOT NULL,

                target BIGINT NOT NULL
                    CHECK (target > 0),

                reward_xp BIGINT NOT NULL DEFAULT 0
                    CHECK (reward_xp >= 0),

                reward_coins BIGINT NOT NULL DEFAULT 0
                    CHECK (reward_coins >= 0),

                reward_cosmetic_id BIGINT,

                enabled BOOLEAN NOT NULL DEFAULT TRUE,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                PRIMARY KEY (
                    guild_id,
                    mission_id
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS mission_progress (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                mission_id VARCHAR(50) NOT NULL,
                period_key VARCHAR(30) NOT NULL,

                baseline_value BIGINT NOT NULL DEFAULT 0,
                claimed_at TIMESTAMPTZ,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                PRIMARY KEY (
                    guild_id,
                    user_id,
                    mission_id,
                    period_key
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS mission_progress_user_idx
            ON mission_progress (
                guild_id,
                user_id,
                period_key
            )
            """
        )

        LOGGER.info(
            "Tables du système de missions vérifiées"
        )

    async def ensure_settings(
        self,
        guild_id: int,
    ) -> None:
        await self.get_pool().execute(
            """
            INSERT INTO mission_settings (
                guild_id
            )
            VALUES ($1)
            ON CONFLICT (guild_id)
            DO NOTHING
            """,
            guild_id,
        )

    async def toggle_system(
        self,
        guild_id: int,
    ) -> bool:
        await self.ensure_settings(
            guild_id
        )

        record = await self.get_pool().fetchrow(
            """
            UPDATE mission_settings
            SET
                enabled = NOT enabled,
                updated_at = NOW()
            WHERE guild_id = $1
            RETURNING enabled
            """,
            guild_id,
        )

        return bool(
            record["enabled"]
        )

    async def is_enabled(
        self,
        guild_id: int,
    ) -> bool:
        await self.ensure_settings(
            guild_id
        )

        value = await self.get_pool().fetchval(
            """
            SELECT enabled
            FROM mission_settings
            WHERE guild_id = $1
            """,
            guild_id,
        )

        return bool(value)

    async def save_missions(
        self,
        *,
        guild_id: int,
        missions: list[dict[str, Any]],
    ) -> None:
        await self.ensure_settings(
            guild_id
        )

        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                for mission in missions:
                    await connection.execute(
                        """
                        INSERT INTO mission_definitions (
                            guild_id,
                            mission_id,
                            period,
                            name,
                            description,
                            metric,
                            target,
                            reward_xp,
                            reward_coins,
                            reward_cosmetic_id,
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
                            guild_id,
                            mission_id
                        )
                        DO UPDATE SET
                            period = EXCLUDED.period,
                            name = EXCLUDED.name,
                            description = EXCLUDED.description,
                            metric = EXCLUDED.metric,
                            target = EXCLUDED.target,
                            reward_xp = EXCLUDED.reward_xp,
                            reward_coins = EXCLUDED.reward_coins,
                            reward_cosmetic_id =
                                EXCLUDED.reward_cosmetic_id,
                            enabled = TRUE,
                            updated_at = NOW()
                        """,
                        guild_id,
                        mission["id"],
                        mission["period"],
                        mission["name"],
                        mission["description"],
                        mission["metric"],
                        mission["target"],
                        mission["reward_xp"],
                        mission["reward_coins"],
                        mission["reward_cosmetic_id"],
                    )

                if missions:
                    mission_ids = [
                        mission["id"]
                        for mission in missions
                    ]

                    await connection.execute(
                        """
                        UPDATE mission_definitions
                        SET
                            enabled = FALSE,
                            updated_at = NOW()
                        WHERE guild_id = $1
                          AND NOT (
                              mission_id = ANY($2::TEXT[])
                          )
                        """,
                        guild_id,
                        mission_ids,
                    )
                else:
                    await connection.execute(
                        """
                        UPDATE mission_definitions
                        SET
                            enabled = FALSE,
                            updated_at = NOW()
                        WHERE guild_id = $1
                        """,
                        guild_id,
                    )

    async def get_missions(
        self,
        *,
        guild_id: int,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                mission_id,
                period,
                name,
                description,
                metric,
                target,
                reward_xp,
                reward_coins,
                reward_cosmetic_id,
                enabled
            FROM mission_definitions
            WHERE guild_id = $1
        """

        if enabled_only:
            query += " AND enabled = TRUE "

        query += """
            ORDER BY
                period,
                mission_id
            LIMIT 25
        """

        records = await self.get_pool().fetch(
            query,
            guild_id,
        )

        return [
            dict(record)
            for record in records
        ]

    async def get_current_metric(
        self,
        *,
        guild_id: int,
        user_id: int,
        metric: str,
    ) -> int:
        pool = self.get_pool()

        if metric == "messages":
            value = await pool.fetchval(
                """
                SELECT rewarded_messages
                FROM progression_members
                WHERE guild_id = $1
                  AND user_id = $2
                """,
                guild_id,
                user_id,
            )

        elif metric == "xp":
            value = await pool.fetchval(
                """
                SELECT total_xp
                FROM progression_members
                WHERE guild_id = $1
                  AND user_id = $2
                """,
                guild_id,
                user_id,
            )

        elif metric == "coins":
            value = await pool.fetchval(
                """
                SELECT lifetime_coins
                FROM progression_members
                WHERE guild_id = $1
                  AND user_id = $2
                """,
                guild_id,
                user_id,
            )

        elif metric == "voice_minutes":
            value = await pool.fetchval(
                """
                SELECT rewarded_minutes
                FROM progression_voice_rewards
                WHERE guild_id = $1
                  AND user_id = $2
                """,
                guild_id,
                user_id,
            )

        elif metric == "daily_claims":
            value = await pool.fetchval(
                """
                SELECT COUNT(*)
                FROM daily_claims
                WHERE guild_id = $1
                  AND user_id = $2
                """,
                guild_id,
                user_id,
            )

        elif metric == "streak":
            value = await pool.fetchval(
                """
                SELECT current_streak
                FROM daily_members
                WHERE guild_id = $1
                  AND user_id = $2
                """,
                guild_id,
                user_id,
            )

        else:
            raise ValueError(
                f"Métrique inconnue : {metric}"
            )

        return int(
            value or 0
        )

    async def get_member_missions(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> list[dict[str, Any]]:
        enabled = await self.is_enabled(
            guild_id
        )

        if not enabled:
            return []

        missions = await self.get_missions(
            guild_id=guild_id,
            enabled_only=True,
        )

        pool = self.get_pool()
        result: list[dict[str, Any]] = []

        for mission in missions:
            period = str(
                mission["period"]
            )

            mission_id = str(
                mission["mission_id"]
            )

            period_key = get_period_key(
                period
            )

            current_value = await self.get_current_metric(
                guild_id=guild_id,
                user_id=user_id,
                metric=str(
                    mission["metric"]
                ),
            )

            await pool.execute(
                """
                INSERT INTO mission_progress (
                    guild_id,
                    user_id,
                    mission_id,
                    period_key,
                    baseline_value
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (
                    guild_id,
                    user_id,
                    mission_id,
                    period_key
                )
                DO NOTHING
                """,
                guild_id,
                user_id,
                mission_id,
                period_key,
                current_value,
            )

            progress_record = await pool.fetchrow(
                """
                SELECT
                    baseline_value,
                    claimed_at
                FROM mission_progress
                WHERE guild_id = $1
                  AND user_id = $2
                  AND mission_id = $3
                  AND period_key = $4
                """,
                guild_id,
                user_id,
                mission_id,
                period_key,
            )

            baseline_value = int(
                progress_record["baseline_value"]
                if progress_record is not None
                else current_value
            )

            progress = max(
                0,
                current_value - baseline_value,
            )

            result.append(
                {
                    **mission,
                    "period_key": period_key,
                    "progress": progress,
                    "claimed": (
                        progress_record is not None
                        and progress_record["claimed_at"] is not None
                    ),
                }
            )

        return result

    async def claim_mission(
        self,
        *,
        guild_id: int,
        user_id: int,
        mission_id: str,
    ) -> str:
        if not await self.is_enabled(
            guild_id
        ):
            raise ValueError(
                "Le système de missions est désactivé."
            )

        mission = await self.get_pool().fetchrow(
            """
            SELECT
                mission_id,
                period,
                name,
                metric,
                target,
                reward_xp,
                reward_coins,
                reward_cosmetic_id
            FROM mission_definitions
            WHERE guild_id = $1
              AND mission_id = $2
              AND enabled = TRUE
            """,
            guild_id,
            mission_id,
        )

        if mission is None:
            raise ValueError(
                "Cette mission n'existe pas ou est désactivée."
            )

        period_key = get_period_key(
            str(mission["period"])
        )

        current_value = await self.get_current_metric(
            guild_id=guild_id,
            user_id=user_id,
            metric=str(
                mission["metric"]
            ),
        )

        pool = self.get_pool()

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO mission_progress (
                        guild_id,
                        user_id,
                        mission_id,
                        period_key,
                        baseline_value
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (
                        guild_id,
                        user_id,
                        mission_id,
                        period_key
                    )
                    DO NOTHING
                    """,
                    guild_id,
                    user_id,
                    mission_id,
                    period_key,
                    current_value,
                )

                progress_record = await connection.fetchrow(
                    """
                    SELECT
                        baseline_value,
                        claimed_at
                    FROM mission_progress
                    WHERE guild_id = $1
                      AND user_id = $2
                      AND mission_id = $3
                      AND period_key = $4
                    FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                    mission_id,
                    period_key,
                )

                if progress_record is None:
                    raise RuntimeError(
                        "La progression de la mission est introuvable."
                    )

                if progress_record["claimed_at"] is not None:
                    raise ValueError(
                        "Cette mission a déjà été réclamée pour cette période."
                    )

                baseline_value = int(
                    progress_record["baseline_value"]
                )

                progress = max(
                    0,
                    current_value - baseline_value,
                )

                target = int(
                    mission["target"]
                )

                if progress < target:
                    raise ValueError(
                        (
                            f"Mission incomplète : "
                            f"**{format_number(progress)}**/"
                            f"**{format_number(target)}** "
                            f"{format_metric(str(mission['metric']))}."
                        )
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

                reward_xp = int(
                    mission["reward_xp"] or 0
                )

                reward_coins = int(
                    mission["reward_coins"] or 0
                )

                updated_progression = await connection.fetchrow(
                    """
                    UPDATE progression_members
                    SET
                        total_xp = total_xp + $3,
                        wallet = wallet + $4,
                        lifetime_coins =
                            lifetime_coins + $4,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    RETURNING total_xp, wallet
                    """,
                    guild_id,
                    user_id,
                    reward_xp,
                    reward_coins,
                )

                if updated_progression is None:
                    raise RuntimeError(
                        "La récompense n'a pas pu être attribuée."
                    )

                if reward_coins > 0:
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
                            'mission_reward',
                            $4
                        )
                        """,
                        guild_id,
                        user_id,
                        reward_coins,
                        f"Mission : {mission['name']}"[:200],
                    )

                reward_cosmetic_id = mission[
                    "reward_cosmetic_id"
                ]

                if reward_cosmetic_id is not None:
                    profile_table_exists = await connection.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                              AND table_name = 'profile_inventory'
                        )
                        """
                    )

                    if profile_table_exists:
                        await connection.execute(
                            """
                            INSERT INTO profile_inventory (
                                guild_id,
                                user_id,
                                cosmetic_id,
                                source
                            )
                            VALUES ($1, $2, $3, 'mission')
                            ON CONFLICT (
                                guild_id,
                                user_id,
                                cosmetic_id
                            )
                            DO NOTHING
                            """,
                            guild_id,
                            user_id,
                            reward_cosmetic_id,
                        )

                await connection.execute(
                    """
                    UPDATE mission_progress
                    SET
                        claimed_at = NOW(),
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                      AND mission_id = $3
                      AND period_key = $4
                    """,
                    guild_id,
                    user_id,
                    mission_id,
                    period_key,
                )

        reward_lines: list[str] = []

        if reward_xp > 0:
            reward_lines.append(
                f"✨ **+{format_number(reward_xp)} XP**"
            )

        if reward_coins > 0:
            reward_lines.append(
                f"💰 **+{format_number(reward_coins)} pièces**"
            )

        if mission["reward_cosmetic_id"] is not None:
            reward_lines.append(
                "🎨 **Un cosmétique a été ajouté à ton inventaire**"
            )

        return (
            f"Tu as terminé la mission "
            f"**{mission['name']}** !\n\n"
            + "\n".join(reward_lines)
        )

    def build_member_embed(
        self,
        missions: list[dict[str, Any]],
    ) -> discord.Embed:
        if not missions:
            return warning_embed(
                "Missions indisponibles",
                (
                    "Le système de missions est désactivé "
                    "ou aucune mission n'est configurée."
                ),
            )

        embed = base_embed(
            "🎯 Tes missions",
            (
                "Les missions **quotidiennes** se réinitialisent "
                "chaque jour.\n"
                "Les missions **hebdomadaires** se réinitialisent "
                "chaque lundi.\n\n"
                "Sélectionne une mission terminée puis clique sur "
                "**Réclamer**."
            ),
        )

        for mission in missions:
            progress = int(
                mission["progress"]
            )

            target = int(
                mission["target"]
            )

            claimed = bool(
                mission["claimed"]
            )

            if claimed:
                status = "✅ Récompense déjà récupérée"
            elif progress >= target:
                status = "🎁 Mission terminée — récompense disponible"
            else:
                status = (
                    f"📊 {format_progress_value(str(mission['metric']), progress)}"
                    f" / "
                    f"{format_progress_value(str(mission['metric']), target)}"
                )

            reward = []

            if int(mission["reward_xp"] or 0) > 0:
                reward.append(
                    f"{format_number(mission['reward_xp'])} XP"
                )

            if int(mission["reward_coins"] or 0) > 0:
                reward.append(
                    f"{format_number(mission['reward_coins'])} pièces"
                )

            if mission["reward_cosmetic_id"] is not None:
                reward.append(
                    "cosmétique"
                )

            embed.add_field(
                name=(
                    f"{'📅' if mission['period'] == 'daily' else '🗓️'} "
                    f"{mission['name']}"
                ),
                value=(
                    f"{mission['description']}\n"
                    f"Type : **{format_metric(str(mission['metric']))}**\n"
                    f"{status}\n"
                    f"Récompense : **{' + '.join(reward)}**"
                ),
                inline=False,
            )

        return embed

    @app_commands.command(
        name="missions",
        description="Affiche tes missions quotidiennes et hebdomadaires.",
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
    async def missions(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        if interaction.guild_id is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Serveur requis",
                    "Cette commande doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        try:
            missions = await self.get_member_missions(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            )

            embed = self.build_member_embed(
                missions
            )

            view = MissionsView(
                cog=self,
                owner_id=interaction.user.id,
                guild_id=interaction.guild_id,
                missions=missions,
            )

            await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True,
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible d'afficher les missions de %s "
                    "sur le serveur %s."
                ),
                interaction.user.id,
                interaction.guild_id,
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Erreur",
                    "Les missions n'ont pas pu être chargées.",
                ),
                ephemeral=True,
            )

    @app_commands.command(
        name="missions-admin",
        description="Configure le système de missions du serveur.",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.guild_only()
    async def missions_admin(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Serveur requis",
                    "Cette commande doit être utilisée dans un serveur.",
                ),
                ephemeral=True,
            )
            return

        try:
            await self.ensure_settings(
                interaction.guild_id
            )

            enabled = await self.is_enabled(
                interaction.guild_id
            )

            missions = await self.get_missions(
                guild_id=interaction.guild_id,
                enabled_only=True,
            )

            embed = base_embed(
                "⚙️ Administration des missions",
                (
                    "Configure ici les missions quotidiennes et "
                    "hebdomadaires du serveur.\n\n"
                    f"État : **{'activé ✅' if enabled else 'désactivé ❌'}**\n"
                    f"Missions actives : **{len(missions)}**"
                ),
            )

            await interaction.response.send_message(
                embed=embed,
                view=MissionsAdminView(
                    cog=self,
                    owner_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                ),
                ephemeral=True,
            )
        except Exception:
            LOGGER.exception(
                "Impossible d'ouvrir l'administration des missions."
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    "Le panneau des missions n'a pas pu être ouvert.",
                ),
                ephemeral=True,
            )


async def setup(
    bot: commands.Bot,
) -> None:
    cog = MissionsCog(
        bot
    )

    await cog.initialize_database()
    await bot.add_cog(
        cog
    )

    LOGGER.info(
        "Système de missions initialisé"
    )


async def teardown(
    bot: commands.Bot,
) -> None:
    await bot.remove_cog(
        "MissionsCog"
    )

    LOGGER.info(
        "Système de missions déchargé"
    )
