from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands


LOGGER = logging.getLogger(__name__)

COLOR = discord.Color.from_rgb(226, 104, 161)
SUCCESS_COLOR = discord.Color.from_rgb(88, 191, 126)
ERROR_COLOR = discord.Color.from_rgb(220, 75, 85)
WARNING_COLOR = discord.Color.from_rgb(235, 174, 65)

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")

MAXIMUM_BASE_REWARD = 100_000_000
MAXIMUM_RULE_BONUS = 100_000_000
MAXIMUM_MULTIPLIER = Decimal("100")
MAXIMUM_RULES = 30
MAXIMUM_STREAK_DAY = 100_000


def get_next_daily_reset(
    current_time: datetime,
) -> datetime:
    """
    Retourne le prochain minuit en France, converti en UTC.
    """
    paris_time = current_time.astimezone(
        PARIS_TIMEZONE
    )

    next_midnight = (
        paris_time.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        + timedelta(days=1)
    )

    return next_midnight.astimezone(
        timezone.utc
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


def format_number(
    value: int,
) -> str:
    return f"{int(value):,}".replace(",", " ")


def format_duration(
    duration: timedelta,
) -> str:
    total_seconds = max(
        0,
        int(duration.total_seconds()),
    )

    hours, remaining = divmod(
        total_seconds,
        3600,
    )

    minutes, seconds = divmod(
        remaining,
        60,
    )

    parts: list[str] = []

    if hours > 0:
        parts.append(
            f"{hours} h"
        )

    if minutes > 0:
        parts.append(
            f"{minutes} min"
        )

    if not parts:
        parts.append(
            f"{seconds} s"
        )

    return " ".join(parts)


def xp_for_level(
    level: int,
) -> int:
    level = max(
        0,
        int(level),
    )

    if level == 0:
        return 0

    return (
        5
        * (level - 1)
        * level
        * (2 * level - 1)
        // 6
        + 25 * level * (level - 1)
        + 100 * level
    )


def level_from_xp(
    total_xp: int,
) -> int:
    total_xp = max(
        0,
        int(total_xp),
    )

    low = 0
    high = 1

    while xp_for_level(high) <= total_xp:
        high *= 2

    while low + 1 < high:
        middle = (
            low + high
        ) // 2

        if xp_for_level(middle) <= total_xp:
            low = middle
        else:
            high = middle

    return low


def decimal_from_value(
    value: Any,
    *,
    field_name: str,
) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(
            f"`{field_name}` doit être un nombre."
        )

    try:
        decimal_value = Decimal(
            str(value).strip().replace(",", ".")
        )
    except (
        InvalidOperation,
        ValueError,
        AttributeError,
    ) as error:
        raise ValueError(
            f"`{field_name}` doit être un nombre valide."
        ) from error

    if not decimal_value.is_finite():
        raise ValueError(
            f"`{field_name}` doit être un nombre fini."
        )

    return decimal_value


def integer_from_value(
    value: Any,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"`{field_name}` doit être un nombre entier."
        )

    try:
        decimal_value = Decimal(
            str(value).strip()
        )
    except (
        InvalidOperation,
        ValueError,
        AttributeError,
    ) as error:
        raise ValueError(
            f"`{field_name}` doit être un nombre entier."
        ) from error

    if not decimal_value.is_finite():
        raise ValueError(
            f"`{field_name}` doit être un nombre entier."
        )

    if decimal_value != decimal_value.to_integral_value():
        raise ValueError(
            f"`{field_name}` doit être un nombre entier."
        )

    integer_value = int(
        decimal_value
    )

    if not minimum <= integer_value <= maximum:
        raise ValueError(
            (
                f"`{field_name}` doit être compris entre "
                f"{format_number(minimum)} et "
                f"{format_number(maximum)}."
            )
        )

    return integer_value


def decimal_to_json_value(
    value: Decimal,
) -> int | float:
    normalized = value.normalize()

    if normalized == normalized.to_integral_value():
        return int(normalized)

    return float(normalized)


def format_multiplier(
    multiplier: Decimal,
) -> str:
    normalized = multiplier.normalize()

    return str(normalized).replace(
        ".",
        ",",
    )


def parse_database_json(
    value: Any,
) -> Any:
    if value is None:
        return []

    if isinstance(
        value,
        (
            list,
            dict,
        ),
    ):
        return value

    if isinstance(
        value,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        try:
            return json.loads(
                value
            )
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            TypeError,
        ):
            return []

    return []


def validate_bonus_rules(
    raw_rules: str | list[Any],
) -> list[dict[str, Any]]:
    if isinstance(
        raw_rules,
        str,
    ):
        cleaned = raw_rules.strip()

        if not cleaned:
            return []

        try:
            decoded = json.loads(
                cleaned
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                (
                    "Le JSON est invalide à la ligne "
                    f"{error.lineno}, colonne {error.colno}."
                )
            ) from error
    else:
        decoded = raw_rules

    if not isinstance(
        decoded,
        list,
    ):
        raise ValueError(
            (
                "Le JSON principal doit être une liste "
                "entourée de crochets `[` et `]`."
            )
        )

    if len(decoded) > MAXIMUM_RULES:
        raise ValueError(
            (
                "Tu peux configurer au maximum "
                f"{MAXIMUM_RULES} règles."
            )
        )

    normalized_rules: list[
        dict[str, Any]
    ] = []

    allowed_keys = {
        "name",
        "day",
        "every",
        "priority",
        "xp_multiplier",
        "coins_multiplier",
        "xp_bonus",
        "coins_bonus",
    }

    for index, raw_rule in enumerate(
        decoded,
        start=1,
    ):
        if not isinstance(
            raw_rule,
            dict,
        ):
            raise ValueError(
                (
                    f"La règle n°{index} doit être "
                    "un objet JSON `{ ... }`."
                )
            )

        unknown_keys = (
            set(raw_rule)
            - allowed_keys
        )

        if unknown_keys:
            unknown_text = ", ".join(
                sorted(unknown_keys)
            )

            raise ValueError(
                (
                    f"La règle n°{index} contient "
                    f"des champs inconnus : `{unknown_text}`."
                )
            )

        has_day = "day" in raw_rule
        has_every = "every" in raw_rule

        if has_day == has_every:
            raise ValueError(
                (
                    f"La règle n°{index} doit contenir "
                    "soit `day`, soit `every`, mais pas les deux."
                )
            )

        normalized_rule: dict[
            str,
            Any
        ] = {}

        if has_day:
            day = integer_from_value(
                raw_rule["day"],
                field_name="day",
                minimum=1,
                maximum=MAXIMUM_STREAK_DAY,
            )

            normalized_rule["day"] = day
            default_name = f"Bonus du jour {day}"
        else:
            every = integer_from_value(
                raw_rule["every"],
                field_name="every",
                minimum=1,
                maximum=MAXIMUM_STREAK_DAY,
            )

            normalized_rule["every"] = every
            default_name = (
                f"Bonus tous les {every} jours"
            )

        name = str(
            raw_rule.get(
                "name",
                default_name,
            )
        ).strip()

        if not name:
            name = default_name

        if len(name) > 100:
            raise ValueError(
                (
                    f"Le nom de la règle n°{index} "
                    "ne peut pas dépasser 100 caractères."
                )
            )

        priority = integer_from_value(
            raw_rule.get(
                "priority",
                0,
            ),
            field_name="priority",
            minimum=0,
            maximum=100_000,
        )

        xp_multiplier = decimal_from_value(
            raw_rule.get(
                "xp_multiplier",
                1,
            ),
            field_name="xp_multiplier",
        )

        coins_multiplier = decimal_from_value(
            raw_rule.get(
                "coins_multiplier",
                1,
            ),
            field_name="coins_multiplier",
        )

        if not (
            Decimal("1")
            <= xp_multiplier
            <= MAXIMUM_MULTIPLIER
        ):
            raise ValueError(
                (
                    f"Le multiplicateur d'XP de la règle n°{index} "
                    "doit être compris entre 1 et "
                    f"{MAXIMUM_MULTIPLIER}."
                )
            )

        if not (
            Decimal("1")
            <= coins_multiplier
            <= MAXIMUM_MULTIPLIER
        ):
            raise ValueError(
                (
                    f"Le multiplicateur de pièces de la règle n°{index} "
                    "doit être compris entre 1 et "
                    f"{MAXIMUM_MULTIPLIER}."
                )
            )

        xp_bonus = integer_from_value(
            raw_rule.get(
                "xp_bonus",
                0,
            ),
            field_name="xp_bonus",
            minimum=0,
            maximum=MAXIMUM_RULE_BONUS,
        )

        coins_bonus = integer_from_value(
            raw_rule.get(
                "coins_bonus",
                0,
            ),
            field_name="coins_bonus",
            minimum=0,
            maximum=MAXIMUM_RULE_BONUS,
        )

        if (
            xp_multiplier == Decimal("1")
            and coins_multiplier == Decimal("1")
            and xp_bonus == 0
            and coins_bonus == 0
        ):
            raise ValueError(
                (
                    f"La règle n°{index} ne donne aucun bonus.\n"
                    "Ajoute un multiplicateur supérieur à 1 "
                    "ou un bonus fixe."
                )
            )

        normalized_rule.update(
            {
                "name": name,
                "priority": priority,
                "xp_multiplier": (
                    decimal_to_json_value(
                        xp_multiplier
                    )
                ),
                "coins_multiplier": (
                    decimal_to_json_value(
                        coins_multiplier
                    )
                ),
                "xp_bonus": xp_bonus,
                "coins_bonus": coins_bonus,
            }
        )

        normalized_rules.append(
            normalized_rule
        )

    return normalized_rules


def rule_is_applicable(
    rule: dict[str, Any],
    streak: int,
) -> bool:
    if "day" in rule:
        return int(
            rule["day"]
        ) == streak

    if "every" in rule:
        interval = int(
            rule["every"]
        )

        return (
            interval > 0
            and streak % interval == 0
        )

    return False


def rule_selection_key(
    rule: dict[str, Any],
    index: int,
) -> tuple[
    int,
    int,
    Decimal,
    Decimal,
    int,
    int,
]:
    priority = int(
        rule.get(
            "priority",
            0,
        )
    )

    exact_day_priority = (
        1
        if "day" in rule
        else 0
    )

    xp_multiplier = Decimal(
        str(
            rule.get(
                "xp_multiplier",
                1,
            )
        )
    )

    coins_multiplier = Decimal(
        str(
            rule.get(
                "coins_multiplier",
                1,
            )
        )
    )

    fixed_bonus = (
        int(
            rule.get(
                "xp_bonus",
                0,
            )
        )
        + int(
            rule.get(
                "coins_bonus",
                0,
            )
        )
    )

    return (
        priority,
        exact_day_priority,
        max(
            xp_multiplier,
            coins_multiplier,
        ),
        xp_multiplier + coins_multiplier,
        fixed_bonus,
        -index,
    )


def select_bonus_rule(
    rules: list[dict[str, Any]],
    streak: int,
) -> dict[str, Any] | None:
    applicable_rules: list[
        tuple[
            int,
            dict[str, Any],
        ]
    ] = []

    for index, rule in enumerate(
        rules
    ):
        if rule_is_applicable(
            rule,
            streak,
        ):
            applicable_rules.append(
                (
                    index,
                    rule,
                )
            )

    if not applicable_rules:
        return None

    _, selected_rule = max(
        applicable_rules,
        key=lambda item: rule_selection_key(
            item[1],
            item[0],
        ),
    )

    return selected_rule


def calculate_reward(
    *,
    base_reward: int,
    multiplier: Decimal,
    fixed_bonus: int,
) -> int:
    multiplied_reward = (
        Decimal(base_reward)
        * multiplier
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    return max(
        0,
        int(multiplied_reward)
        + int(fixed_bonus),
    )


def describe_rule(
    rule: dict[str, Any],
) -> str:
    name = str(
        rule.get(
            "name",
            "Bonus de série",
        )
    )

    if "day" in rule:
        trigger = (
            f"jour **{int(rule['day'])}**"
        )
    else:
        trigger = (
            "tous les "
            f"**{int(rule['every'])} jours**"
        )

    effects: list[str] = []

    xp_multiplier = Decimal(
        str(
            rule.get(
                "xp_multiplier",
                1,
            )
        )
    )

    coins_multiplier = Decimal(
        str(
            rule.get(
                "coins_multiplier",
                1,
            )
        )
    )

    xp_bonus = int(
        rule.get(
            "xp_bonus",
            0,
        )
    )

    coins_bonus = int(
        rule.get(
            "coins_bonus",
            0,
        )
    )

    if xp_multiplier > Decimal("1"):
        effects.append(
            "XP "
            f"×{format_multiplier(xp_multiplier)}"
        )

    if coins_multiplier > Decimal("1"):
        effects.append(
            "pièces "
            f"×{format_multiplier(coins_multiplier)}"
        )

    if xp_bonus > 0:
        effects.append(
            f"+{format_number(xp_bonus)} XP"
        )

    if coins_bonus > 0:
        effects.append(
            (
                f"+{format_number(coins_bonus)} "
                "pièces"
            )
        )

    effects_text = (
        ", ".join(effects)
        if effects
        else "aucun effet"
    )

    priority = int(
        rule.get(
            "priority",
            0,
        )
    )

    priority_text = ""

    if priority > 0:
        priority_text = (
            f" · priorité {priority}"
        )

    return (
        f"• **{name}** — {trigger}\n"
        f"  ↳ {effects_text}{priority_text}"
    )


@dataclass(slots=True)
class DailyClaimResult:
    status: str

    current_streak: int
    best_streak: int
    total_claims: int

    xp_reward: int
    coins_reward: int

    base_xp: int
    base_coins: int

    bonus_xp: int
    bonus_coins: int

    xp_multiplier: Decimal
    coins_multiplier: Decimal

    applied_rule: dict[str, Any] | None

    old_level: int
    new_level: int

    total_xp: int
    wallet: int

    next_claim_at: datetime | None


class DailyBaseConfigModal(
    discord.ui.Modal,
    title="Récompense quotidienne",
):
    def __init__(
        self,
        *,
        cog: DailyCog,
        guild_id: int,
        settings: dict[str, Any],
    ) -> None:
        super().__init__(
            timeout=300,
        )

        self.cog = cog
        self.guild_id = guild_id

        self.base_xp_input = discord.ui.TextInput(
            label="XP quotidienne",
            placeholder="Exemple : 100",
            default=str(
                settings["base_xp"]
            ),
            required=True,
            min_length=1,
            max_length=10,
        )

        self.base_coins_input = discord.ui.TextInput(
            label="Pièces quotidiennes",
            placeholder="Exemple : 15",
            default=str(
                settings["base_coins"]
            ),
            required=True,
            min_length=1,
            max_length=10,
        )

        self.add_item(
            self.base_xp_input
        )

        self.add_item(
            self.base_coins_input
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            base_xp = integer_from_value(
                self.base_xp_input.value,
                field_name="XP quotidienne",
                minimum=0,
                maximum=MAXIMUM_BASE_REWARD,
            )

            base_coins = integer_from_value(
                self.base_coins_input.value,
                field_name="Pièces quotidiennes",
                minimum=0,
                maximum=MAXIMUM_BASE_REWARD,
            )
        except ValueError as error:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    str(error),
                ),
                ephemeral=True,
            )
            return

        try:
            await self.cog.update_base_rewards(
                guild_id=self.guild_id,
                base_xp=base_xp,
                base_coins=base_coins,
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible de modifier les récompenses "
                    "quotidiennes du serveur %s."
                ),
                self.guild_id,
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    (
                        "Les récompenses n'ont pas "
                        "pu être enregistrées."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Récompense enregistrée",
                (
                    "La récompense quotidienne fixe est maintenant :\n\n"
                    f"✨ **{format_number(base_xp)} XP**\n"
                    f"💰 **{format_number(base_coins)} pièces**\n\n"
                    "Les bonus de série configurés dans le JSON "
                    "peuvent modifier cette récompense."
                ),
            ),
            ephemeral=True,
        )


class DailyRulesModal(
    discord.ui.Modal,
    title="Bonus de série en JSON",
):
    def __init__(
        self,
        *,
        cog: DailyCog,
        guild_id: int,
        rules: list[dict[str, Any]],
    ) -> None:
        super().__init__(
            timeout=600,
        )

        self.cog = cog
        self.guild_id = guild_id

        serialized_rules = json.dumps(
            rules,
            ensure_ascii=False,
            indent=2,
        )

        if len(serialized_rules) > 4000:
            serialized_rules = "[]"

        self.rules_input = discord.ui.TextInput(
            label="Règles JSON",
            placeholder=(
                '[{"every":7,"coins_multiplier":2},'
                '{"day":30,"xp_multiplier":2}]'
            ),
            default=serialized_rules,
            style=discord.TextStyle.paragraph,
            required=True,
            min_length=2,
            max_length=4000,
        )

        self.add_item(
            self.rules_input
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            normalized_rules = validate_bonus_rules(
                str(
                    self.rules_input.value
                )
            )
        except ValueError as error:
            await interaction.response.send_message(
                embed=error_embed(
                    "JSON invalide",
                    str(error),
                ),
                ephemeral=True,
            )
            return

        try:
            await self.cog.update_bonus_rules(
                guild_id=self.guild_id,
                rules=normalized_rules,
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible de modifier les bonus "
                    "quotidiens du serveur %s."
                ),
                self.guild_id,
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    (
                        "Les bonus n'ont pas "
                        "pu être enregistrés."
                    ),
                ),
                ephemeral=True,
            )
            return

        if normalized_rules:
            description = (
                f"**{len(normalized_rules)} règle(s)** "
                "de bonus ont été enregistrées.\n\n"
                "Si plusieurs règles correspondent au même jour, "
                "une seule règle sera appliquée."
            )
        else:
            description = (
                "Toutes les règles de bonus ont été supprimées.\n\n"
                "La récompense restera identique tous les jours."
            )

        await interaction.response.send_message(
            embed=success_embed(
                "Bonus enregistrés",
                description,
            ),
            ephemeral=True,
        )


class DailyResetConfirmView(
    discord.ui.View
):
    def __init__(
        self,
        *,
        cog: DailyCog,
        owner_id: int,
        guild_id: int,
        user_id: int,
    ) -> None:
        super().__init__(
            timeout=60,
        )

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
                (
                    "Seul l'administrateur ayant lancé "
                    "cette action peut répondre."
                ),
            ),
            ephemeral=True,
        )

        return False

    def disable_buttons(self) -> None:
        for item in self.children:
            if isinstance(
                item,
                discord.ui.Button,
            ):
                item.disabled = True

    async def on_timeout(self) -> None:
        self.disable_buttons()

    @discord.ui.button(
        label="Confirmer la réinitialisation",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=0,
    )
    async def confirm_reset(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        try:
            result = await self.cog.reset_daily_member(
                guild_id=self.guild_id,
                user_id=self.user_id,
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible de réinitialiser le quotidien "
                    "de %s sur le serveur %s."
                ),
                self.user_id,
                self.guild_id,
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    (
                        "Le quotidien de ce membre "
                        "n'a pas pu être réinitialisé."
                    ),
                ),
                ephemeral=True,
            )
            return

        self.disable_buttons()

        await interaction.response.edit_message(
            embed=success_embed(
                "Quotidien réinitialisé",
                (
                    f"Le quotidien de <@{self.user_id}> "
                    "a été entièrement réinitialisé.\n\n"
                    f"Réclamations supprimées : "
                    f"**{result['claims_deleted']}**\n"
                    "Série actuelle : **0**\n"
                    "Meilleure série : **0**\n"
                    "Total de réclamations : **0**\n\n"
                    "Le membre peut immédiatement utiliser "
                    "`/quotidien` à nouveau.\n\n"
                    "Les pièces et l'XP déjà gagnées "
                    "n'ont pas été retirées."
                ),
            ),
            view=self,
        )

        self.stop()

    @discord.ui.button(
        label="Annuler",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def cancel_reset(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.disable_buttons()

        await interaction.response.edit_message(
            embed=warning_embed(
                "Réinitialisation annulée",
                (
                    "Aucune donnée quotidienne "
                    "n'a été supprimée."
                ),
            ),
            view=self,
        )

        self.stop()


class DailyResetMemberSelect(
    discord.ui.UserSelect
):
    def __init__(
        self,
        *,
        cog: DailyCog,
        owner_id: int,
        guild_id: int,
    ) -> None:
        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id

        super().__init__(
            placeholder=(
                "Sélectionne le membre à réinitialiser…"
            ),
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.values:
            await interaction.response.send_message(
                embed=error_embed(
                    "Aucun membre",
                    (
                        "Aucun membre "
                        "n'a été sélectionné."
                    ),
                ),
                ephemeral=True,
            )
            return

        selected_user = self.values[0]

        if selected_user.bot:
            await interaction.response.send_message(
                embed=error_embed(
                    "Membre invalide",
                    (
                        "Le quotidien d'un bot "
                        "ne peut pas être réinitialisé."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=warning_embed(
                "Confirmation obligatoire",
                (
                    "Tu vas réinitialiser le quotidien de "
                    f"{selected_user.mention}.\n\n"
                    "Les éléments suivants seront supprimés :\n"
                    "• sa série actuelle ;\n"
                    "• sa meilleure série ;\n"
                    "• son nombre total de réclamations ;\n"
                    "• la date de sa dernière réclamation ;\n"
                    "• son historique quotidien.\n\n"
                    "Les pièces et l'XP déjà gagnées "
                    "seront conservées."
                ),
            ),
            view=DailyResetConfirmView(
                cog=self.cog,
                owner_id=self.owner_id,
                guild_id=self.guild_id,
                user_id=selected_user.id,
            ),
            ephemeral=True,
        )


class DailyResetMemberView(
    discord.ui.View
):
    def __init__(
        self,
        *,
        cog: DailyCog,
        owner_id: int,
        guild_id: int,
    ) -> None:
        super().__init__(
            timeout=180,
        )

        self.owner_id = owner_id

        self.add_item(
            DailyResetMemberSelect(
                cog=cog,
                owner_id=owner_id,
                guild_id=guild_id,
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
                "Panneau personnel",
                (
                    "Seul l'administrateur ayant ouvert "
                    "ce menu peut l'utiliser."
                ),
            ),
            ephemeral=True,
        )

        return False


class DailyAdminView(
    discord.ui.View
):
    def __init__(
        self,
        *,
        cog: DailyCog,
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
                "Panneau personnel",
                (
                    "Seul l'administrateur ayant ouvert "
                    "ce panneau peut l'utiliser."
                ),
            ),
            ephemeral=True,
        )

        return False

    @discord.ui.button(
        label="Récompense",
        emoji="🎁",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def configure_rewards(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
            use_cache=False,
        )

        await interaction.response.send_modal(
            DailyBaseConfigModal(
                cog=self.cog,
                guild_id=self.guild_id,
                settings=settings,
            )
        )

    @discord.ui.button(
        label="Bonus de série",
        emoji="🔥",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def configure_rules(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        settings = await self.cog.get_settings(
            self.guild_id,
            use_cache=False,
        )

        await interaction.response.send_modal(
            DailyRulesModal(
                cog=self.cog,
                guild_id=self.guild_id,
                rules=settings["bonus_rules"],
            )
        )

    @discord.ui.button(
        label="Activer/désactiver",
        emoji="🔌",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def toggle_system(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        try:
            settings = await self.cog.get_settings(
                self.guild_id,
                use_cache=False,
            )

            enabled = not bool(
                settings["enabled"]
            )

            await self.cog.set_enabled(
                guild_id=self.guild_id,
                enabled=enabled,
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible de modifier l'état du quotidien "
                    "du serveur %s."
                ),
                self.guild_id,
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    (
                        "L'état du système "
                        "n'a pas pu être modifié."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "État modifié",
                (
                    "La récompense quotidienne est maintenant "
                    f"**{'activée' if enabled else 'désactivée'}**."
                ),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Voir la configuration",
        emoji="📋",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def show_configuration(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        try:
            embed = await self.cog.build_admin_embed(
                self.guild_id
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible d'afficher la configuration "
                    "du serveur %s."
                ),
                self.guild_id,
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    (
                        "La configuration "
                        "n'a pas pu être chargée."
                    ),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Exemple JSON",
        emoji="🧩",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def show_json_example(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        example = [
            {
                "name": "Septième jour",
                "every": 7,
                "coins_multiplier": 2,
            },
            {
                "name": "Trentième jour",
                "day": 30,
                "priority": 10,
                "xp_multiplier": 2,
                "coins_multiplier": 3,
            },
            {
                "name": "Centième jour",
                "day": 100,
                "priority": 20,
                "xp_bonus": 5000,
                "coins_bonus": 1000,
            },
        ]

        json_example = json.dumps(
            example,
            ensure_ascii=False,
            indent=2,
        )

        await interaction.response.send_message(
            embed=base_embed(
                "🧩 Exemple de configuration JSON",
                (
                    "Copie et adapte cet exemple dans "
                    "**Bonus de série** :\n\n"
                    f"```json\n{json_example}\n```\n"
                    "`every` applique une règle tous les X jours.\n"
                    "`day` applique une règle à un jour précis.\n"
                    "`priority` permet de choisir une règle "
                    "si plusieurs correspondent au même jour."
                ),
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Réinitialiser un membre",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=2,
    )
    async def reset_daily_member_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            embed=warning_embed(
                "Réinitialisation quotidienne",
                (
                    "Sélectionne le membre dont tu souhaites "
                    "réinitialiser le quotidien.\n\n"
                    "Ses récompenses déjà gagnées seront conservées."
                ),
            ),
            view=DailyResetMemberView(
                cog=self.cog,
                owner_id=self.owner_id,
                guild_id=self.guild_id,
            ),
            ephemeral=True,
        )


class DailyCog(
    commands.Cog
):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

        self._settings_cache: dict[
            int,
            tuple[
                float,
                dict[str, Any],
            ],
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

    def get_progression_cog(
        self,
    ) -> commands.Cog | None:
        return self.bot.get_cog(
            "ProgressionCog"
        )

    async def initialize_database(
        self,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_settings (
                guild_id BIGINT PRIMARY KEY,

                enabled BOOLEAN NOT NULL DEFAULT TRUE,

                base_xp BIGINT NOT NULL DEFAULT 100
                    CHECK (base_xp >= 0),

                base_coins BIGINT NOT NULL DEFAULT 15
                    CHECK (base_coins >= 0),

                streak_xp_bonus BIGINT NOT NULL DEFAULT 0
                    CHECK (streak_xp_bonus >= 0),

                streak_coins_bonus BIGINT NOT NULL DEFAULT 0
                    CHECK (streak_coins_bonus >= 0),

                maximum_bonus_days INTEGER NOT NULL DEFAULT 0
                    CHECK (maximum_bonus_days >= 0),

                bonus_rules JSONB NOT NULL DEFAULT '[]'::JSONB,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            ALTER TABLE daily_settings
            ADD COLUMN IF NOT EXISTS bonus_rules JSONB
                NOT NULL DEFAULT '[]'::JSONB
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_members (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,

                current_streak INTEGER NOT NULL DEFAULT 0
                    CHECK (current_streak >= 0),

                best_streak INTEGER NOT NULL DEFAULT 0
                    CHECK (best_streak >= 0),

                total_claims BIGINT NOT NULL DEFAULT 0
                    CHECK (total_claims >= 0),

                last_claim_at TIMESTAMPTZ,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                PRIMARY KEY (
                    guild_id,
                    user_id
                )
            )
            """
        )

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_claims (
                id BIGSERIAL PRIMARY KEY,

                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,

                streak INTEGER NOT NULL
                    CHECK (streak >= 1),

                xp_reward BIGINT NOT NULL
                    CHECK (xp_reward >= 0),

                coins_reward BIGINT NOT NULL
                    CHECK (coins_reward >= 0),

                base_xp BIGINT NOT NULL
                    CHECK (base_xp >= 0),

                base_coins BIGINT NOT NULL
                    CHECK (base_coins >= 0),

                bonus_xp BIGINT NOT NULL DEFAULT 0
                    CHECK (bonus_xp >= 0),

                bonus_coins BIGINT NOT NULL DEFAULT 0
                    CHECK (bonus_coins >= 0),

                xp_multiplier NUMERIC(10, 2)
                    NOT NULL DEFAULT 1.00,

                coins_multiplier NUMERIC(10, 2)
                    NOT NULL DEFAULT 1.00,

                applied_rules JSONB
                    NOT NULL DEFAULT '[]'::JSONB,

                claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            """
            ALTER TABLE daily_claims
            ADD COLUMN IF NOT EXISTS xp_multiplier
                NUMERIC(10, 2) NOT NULL DEFAULT 1.00
            """
        )

        await pool.execute(
            """
            ALTER TABLE daily_claims
            ADD COLUMN IF NOT EXISTS coins_multiplier
                NUMERIC(10, 2) NOT NULL DEFAULT 1.00
            """
        )

        await pool.execute(
            """
            ALTER TABLE daily_claims
            ADD COLUMN IF NOT EXISTS applied_rules
                JSONB NOT NULL DEFAULT '[]'::JSONB
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS daily_members_claim_idx
            ON daily_members (
                guild_id,
                last_claim_at DESC
            )
            """
        )

        await pool.execute(
            """
            CREATE INDEX IF NOT EXISTS daily_claims_member_idx
            ON daily_claims (
                guild_id,
                user_id,
                claimed_at DESC
            )
            """
        )

        LOGGER.info(
            "Tables des récompenses quotidiennes vérifiées"
        )

    async def ensure_settings(
        self,
        guild_id: int,
    ) -> None:
        pool = self.get_pool()

        await pool.execute(
            """
            INSERT INTO daily_settings (
                guild_id
            )
            VALUES ($1)
            ON CONFLICT (guild_id)
            DO NOTHING
            """,
            guild_id,
        )

    async def get_settings(
        self,
        guild_id: int,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        current_time = time.monotonic()

        cached = self._settings_cache.get(
            guild_id
        )

        if (
            use_cache
            and cached is not None
            and cached[0] > current_time
        ):
            return cached[1]

        await self.ensure_settings(
            guild_id
        )

        pool = self.get_pool()

        record = await pool.fetchrow(
            """
            SELECT
                enabled,
                base_xp,
                base_coins,
                bonus_rules
            FROM daily_settings
            WHERE guild_id = $1
            """,
            guild_id,
        )

        if record is None:
            raise RuntimeError(
                (
                    "La configuration des récompenses "
                    "quotidiennes est introuvable."
                )
            )

        raw_rules = parse_database_json(
            record["bonus_rules"]
        )

        try:
            normalized_rules = validate_bonus_rules(
                raw_rules
            )
        except ValueError:
            LOGGER.exception(
                (
                    "Les règles quotidiennes du serveur %s "
                    "sont invalides."
                ),
                guild_id,
            )

            normalized_rules = []

        settings = {
            "enabled": bool(
                record["enabled"]
            ),
            "base_xp": int(
                record["base_xp"] or 0
            ),
            "base_coins": int(
                record["base_coins"] or 0
            ),
            "bonus_rules": normalized_rules,
        }

        self._settings_cache[
            guild_id
        ] = (
            current_time + 60,
            settings,
        )

        return settings

    async def update_base_rewards(
        self,
        *,
        guild_id: int,
        base_xp: int,
        base_coins: int,
    ) -> None:
        await self.ensure_settings(
            guild_id
        )

        pool = self.get_pool()

        await pool.execute(
            """
            UPDATE daily_settings
            SET
                base_xp = $2,
                base_coins = $3,
                streak_xp_bonus = 0,
                streak_coins_bonus = 0,
                maximum_bonus_days = 0,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            base_xp,
            base_coins,
        )

        self._settings_cache.pop(
            guild_id,
            None,
        )

    async def update_bonus_rules(
        self,
        *,
        guild_id: int,
        rules: list[dict[str, Any]],
    ) -> None:
        normalized_rules = validate_bonus_rules(
            rules
        )

        serialized_rules = json.dumps(
            normalized_rules,
            ensure_ascii=False,
        )

        await self.ensure_settings(
            guild_id
        )

        pool = self.get_pool()

        await pool.execute(
            """
            UPDATE daily_settings
            SET
                bonus_rules = $2::JSONB,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            serialized_rules,
        )

        self._settings_cache.pop(
            guild_id,
            None,
        )

    async def set_enabled(
        self,
        *,
        guild_id: int,
        enabled: bool,
    ) -> None:
        await self.ensure_settings(
            guild_id
        )

        pool = self.get_pool()

        await pool.execute(
            """
            UPDATE daily_settings
            SET
                enabled = $2,
                updated_at = NOW()
            WHERE guild_id = $1
            """,
            guild_id,
            enabled,
        )

        self._settings_cache.pop(
            guild_id,
            None,
        )

    async def reset_daily_member(
        self,
        *,
        guild_id: int,
        user_id: int,
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
                    f"daily:{guild_id}:{user_id}",
                )

                claims_deleted = await connection.fetchval(
                    """
                    WITH deleted_claims AS (
                        DELETE FROM daily_claims
                        WHERE guild_id = $1
                          AND user_id = $2
                        RETURNING 1
                    )
                    SELECT COUNT(*)
                    FROM deleted_claims
                    """,
                    guild_id,
                    user_id,
                )

                members_deleted = await connection.fetchval(
                    """
                    WITH deleted_member AS (
                        DELETE FROM daily_members
                        WHERE guild_id = $1
                          AND user_id = $2
                        RETURNING 1
                    )
                    SELECT COUNT(*)
                    FROM deleted_member
                    """,
                    guild_id,
                    user_id,
                )

        return {
            "claims_deleted": int(
                claims_deleted or 0
            ),
            "members_deleted": int(
                members_deleted or 0
            ),
        }

    async def claim_daily_reward(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> DailyClaimResult:
        pool = self.get_pool()

        current_time = datetime.now(
            timezone.utc
        )

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1, 0)
                    )
                    """,
                    f"daily:{guild_id}:{user_id}",
                )

                await connection.execute(
                    """
                    INSERT INTO daily_settings (
                        guild_id
                    )
                    VALUES ($1)
                    ON CONFLICT (guild_id)
                    DO NOTHING
                    """,
                    guild_id,
                )

                settings_record = await connection.fetchrow(
                    """
                    SELECT
                        enabled,
                        base_xp,
                        base_coins,
                        bonus_rules
                    FROM daily_settings
                    WHERE guild_id = $1
                    """,
                    guild_id,
                )

                if settings_record is None:
                    raise RuntimeError(
                        (
                            "La configuration quotidienne "
                            "est introuvable."
                        )
                    )

                enabled = bool(
                    settings_record["enabled"]
                )

                base_xp = int(
                    settings_record["base_xp"]
                    or 0
                )

                base_coins = int(
                    settings_record["base_coins"]
                    or 0
                )

                raw_rules = parse_database_json(
                    settings_record[
                        "bonus_rules"
                    ]
                )

                try:
                    bonus_rules = validate_bonus_rules(
                        raw_rules
                    )
                except ValueError:
                    LOGGER.exception(
                        (
                            "Règles quotidiennes invalides "
                            "pour le serveur %s."
                        ),
                        guild_id,
                    )

                    bonus_rules = []

                await connection.execute(
                    """
                    INSERT INTO daily_members (
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

                daily_record = await connection.fetchrow(
                    """
                    SELECT
                        current_streak,
                        best_streak,
                        total_claims,
                        last_claim_at
                    FROM daily_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                )

                if daily_record is None:
                    raise RuntimeError(
                        (
                            "Les données quotidiennes "
                            "du membre sont introuvables."
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

                progression_record = await connection.fetchrow(
                    """
                    SELECT
                        total_xp,
                        wallet
                    FROM progression_members
                    WHERE guild_id = $1
                      AND user_id = $2
                    FOR UPDATE
                    """,
                    guild_id,
                    user_id,
                )

                if progression_record is None:
                    raise RuntimeError(
                        (
                            "La progression du membre "
                            "est introuvable."
                        )
                    )

                current_streak = int(
                    daily_record[
                        "current_streak"
                    ]
                    or 0
                )

                best_streak = int(
                    daily_record[
                        "best_streak"
                    ]
                    or 0
                )

                total_claims = int(
                    daily_record[
                        "total_claims"
                    ]
                    or 0
                )

                last_claim_at = daily_record[
                    "last_claim_at"
                ]

                old_xp = int(
                    progression_record[
                        "total_xp"
                    ]
                    or 0
                )

                old_wallet = int(
                    progression_record[
                        "wallet"
                    ]
                    or 0
                )

                old_level = level_from_xp(
                    old_xp
                )

                if not enabled:
                    return DailyClaimResult(
                        status="disabled",
                        current_streak=current_streak,
                        best_streak=best_streak,
                        total_claims=total_claims,
                        xp_reward=0,
                        coins_reward=0,
                        base_xp=base_xp,
                        base_coins=base_coins,
                        bonus_xp=0,
                        bonus_coins=0,
                        xp_multiplier=Decimal("1"),
                        coins_multiplier=Decimal("1"),
                        applied_rule=None,
                        old_level=old_level,
                        new_level=old_level,
                        total_xp=old_xp,
                        wallet=old_wallet,
                        next_claim_at=None,
                    )

                paris_date = current_time.astimezone(
                    PARIS_TIMEZONE
                ).date()

                next_claim_at = get_next_daily_reset(
                    current_time
                )

                if last_claim_at is not None:
                    last_claim_date = (
                        last_claim_at.astimezone(
                            PARIS_TIMEZONE
                        ).date()
                    )

                    if last_claim_date >= paris_date:
                        return DailyClaimResult(
                            status="cooldown",
                            current_streak=current_streak,
                            best_streak=best_streak,
                            total_claims=total_claims,
                            xp_reward=0,
                            coins_reward=0,
                            base_xp=base_xp,
                            base_coins=base_coins,
                            bonus_xp=0,
                            bonus_coins=0,
                            xp_multiplier=Decimal("1"),
                            coins_multiplier=Decimal("1"),
                            applied_rule=None,
                            old_level=old_level,
                            new_level=old_level,
                            total_xp=old_xp,
                            wallet=old_wallet,
                            next_claim_at=next_claim_at,
                        )

                    days_since_last_claim = (
                        paris_date
                        - last_claim_date
                    ).days

                    if days_since_last_claim == 1:
                        new_streak = (
                            current_streak + 1
                        )
                    else:
                        new_streak = 1
                else:
                    new_streak = 1

                new_best_streak = max(
                    best_streak,
                    new_streak,
                )

                new_total_claims = (
                    total_claims + 1
                )

                selected_rule = select_bonus_rule(
                    bonus_rules,
                    new_streak,
                )

                if selected_rule is None:
                    xp_multiplier = Decimal("1")
                    coins_multiplier = Decimal("1")
                    fixed_xp_bonus = 0
                    fixed_coins_bonus = 0
                    applied_rules: list[
                        dict[str, Any]
                    ] = []
                else:
                    xp_multiplier = Decimal(
                        str(
                            selected_rule.get(
                                "xp_multiplier",
                                1,
                            )
                        )
                    )

                    coins_multiplier = Decimal(
                        str(
                            selected_rule.get(
                                "coins_multiplier",
                                1,
                            )
                        )
                    )

                    fixed_xp_bonus = int(
                        selected_rule.get(
                            "xp_bonus",
                            0,
                        )
                    )

                    fixed_coins_bonus = int(
                        selected_rule.get(
                            "coins_bonus",
                            0,
                        )
                    )

                    applied_rules = [
                        selected_rule
                    ]

                xp_reward = calculate_reward(
                    base_reward=base_xp,
                    multiplier=xp_multiplier,
                    fixed_bonus=fixed_xp_bonus,
                )

                coins_reward = calculate_reward(
                    base_reward=base_coins,
                    multiplier=coins_multiplier,
                    fixed_bonus=fixed_coins_bonus,
                )

                bonus_xp = max(
                    0,
                    xp_reward - base_xp,
                )

                bonus_coins = max(
                    0,
                    coins_reward - base_coins,
                )

                updated_progression = (
                    await connection.fetchrow(
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
                        RETURNING
                            total_xp,
                            wallet
                        """,
                        guild_id,
                        user_id,
                        xp_reward,
                        coins_reward,
                    )
                )

                if updated_progression is None:
                    raise RuntimeError(
                        (
                            "La récompense n'a pas "
                            "pu être ajoutée."
                        )
                    )

                await connection.execute(
                    """
                    UPDATE daily_members
                    SET
                        current_streak = $3,
                        best_streak = $4,
                        total_claims = $5,
                        last_claim_at = $6,
                        updated_at = NOW()
                    WHERE guild_id = $1
                      AND user_id = $2
                    """,
                    guild_id,
                    user_id,
                    new_streak,
                    new_best_streak,
                    new_total_claims,
                    current_time,
                )

                serialized_applied_rules = json.dumps(
                    applied_rules,
                    ensure_ascii=False,
                )

                await connection.execute(
                    """
                    INSERT INTO daily_claims (
                        guild_id,
                        user_id,
                        streak,
                        xp_reward,
                        coins_reward,
                        base_xp,
                        base_coins,
                        bonus_xp,
                        bonus_coins,
                        xp_multiplier,
                        coins_multiplier,
                        applied_rules,
                        claimed_at
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
                        $11,
                        $12::JSONB,
                        $13
                    )
                    """,
                    guild_id,
                    user_id,
                    new_streak,
                    xp_reward,
                    coins_reward,
                    base_xp,
                    base_coins,
                    bonus_xp,
                    bonus_coins,
                    xp_multiplier,
                    coins_multiplier,
                    serialized_applied_rules,
                    current_time,
                )

                if coins_reward > 0:
                    reason = (
                        "Récompense quotidienne"
                    )

                    if selected_rule is not None:
                        reason += (
                            " — "
                            + str(
                                selected_rule.get(
                                    "name",
                                    "Bonus de série",
                                )
                            )
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
                            'daily_reward',
                            $4
                        )
                        """,
                        guild_id,
                        user_id,
                        coins_reward,
                        reason[:200],
                    )

                total_xp = int(
                    updated_progression[
                        "total_xp"
                    ]
                    or 0
                )

                wallet = int(
                    updated_progression[
                        "wallet"
                    ]
                    or 0
                )

                new_level = level_from_xp(
                    total_xp
                )

                return DailyClaimResult(
                    status="claimed",
                    current_streak=new_streak,
                    best_streak=new_best_streak,
                    total_claims=new_total_claims,
                    xp_reward=xp_reward,
                    coins_reward=coins_reward,
                    base_xp=base_xp,
                    base_coins=base_coins,
                    bonus_xp=bonus_xp,
                    bonus_coins=bonus_coins,
                    xp_multiplier=xp_multiplier,
                    coins_multiplier=coins_multiplier,
                    applied_rule=selected_rule,
                    old_level=old_level,
                    new_level=new_level,
                    total_xp=total_xp,
                    wallet=wallet,
                    next_claim_at=next_claim_at,
                )

    def find_next_bonus(
        self,
        *,
        rules: list[dict[str, Any]],
        current_streak: int,
    ) -> tuple[
        int,
        dict[str, Any],
    ] | None:
        if not rules:
            return None

        start_day = max(
            1,
            current_streak + 1,
        )

        search_limit = min(
            MAXIMUM_STREAK_DAY,
            start_day + 100_000,
        )

        for streak_day in range(
            start_day,
            search_limit + 1,
        ):
            selected_rule = select_bonus_rule(
                rules,
                streak_day,
            )

            if selected_rule is not None:
                return (
                    streak_day,
                    selected_rule,
                )

        return None

    async def update_member_level_role(
        self,
        *,
        guild: discord.Guild,
        member: discord.Member,
        level: int,
    ) -> list[discord.Role]:
        progression_cog = (
            self.get_progression_cog()
        )

        if progression_cog is None:
            return []

        role_updater = getattr(
            progression_cog,
            "grant_earned_level_roles",
            None,
        )

        if role_updater is None:
            return []

        try:
            result = await role_updater(
                member,
                level,
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible d'actualiser le rôle "
                    "de niveau de %s sur le serveur %s."
                ),
                member.id,
                guild.id,
            )

            return []

        if isinstance(
            result,
            list,
        ):
            return result

        return []

    async def build_admin_embed(
        self,
        guild_id: int,
    ) -> discord.Embed:
        settings = await self.get_settings(
            guild_id,
            use_cache=False,
        )

        enabled = bool(
            settings["enabled"]
        )

        base_xp = int(
            settings["base_xp"]
        )

        base_coins = int(
            settings["base_coins"]
        )

        rules: list[
            dict[str, Any]
        ] = settings["bonus_rules"]

        embed = base_embed(
            "🎁 Récompense quotidienne",
            (
                "La récompense de base est identique chaque jour.\n"
                "Seuls les paliers configurés dans le JSON "
                "peuvent lui ajouter un bonus."
            ),
        )

        embed.add_field(
            name="État",
            value=(
                "Activé ✅"
                if enabled
                else "Désactivé ❌"
            ),
            inline=True,
        )

        embed.add_field(
            name="Récompense fixe",
            value=(
                f"✨ **{format_number(base_xp)} XP**\n"
                f"💰 **{format_number(base_coins)} pièces**"
            ),
            inline=True,
        )

        embed.add_field(
            name="Réinitialisation",
            value=(
                "⏱️ Nouvelle récompense : "
                "**chaque jour à minuit**\n"
                "🕰️ Fuseau horaire : **Europe/Paris**\n"
                "🔥 La série continue en réclamant "
                "deux jours consécutifs."
            ),
            inline=False,
        )

        if rules:
            displayed_rules = [
                describe_rule(rule)
                for rule in rules[:10]
            ]

            rules_text = "\n\n".join(
                displayed_rules
            )

            if len(rules) > 10:
                rules_text += (
                    "\n\n"
                    f"… et {len(rules) - 10} autre(s) règle(s)."
                )

            embed.add_field(
                name=(
                    "🔥 Bonus configurés "
                    f"({len(rules)})"
                ),
                value=rules_text[:1024],
                inline=False,
            )
        else:
            embed.add_field(
                name="🔥 Bonus configurés",
                value=(
                    "Aucun bonus de série.\n"
                    "La récompense restera identique "
                    "tous les jours."
                ),
                inline=False,
            )

        embed.add_field(
            name="Chevauchement des règles",
            value=(
                "Une seule règle peut être appliquée par jour.\n"
                "La priorité la plus élevée gagne. "
                "À priorité égale, un jour précis est prioritaire "
                "sur une règle récurrente."
            ),
            inline=False,
        )

        embed.set_footer(
            text=(
                "Utilise le bouton Exemple JSON "
                "pour voir tous les champs disponibles."
            )
        )

        return embed

    @app_commands.command(
        name="quotidien",
        description=(
            "Récupère ta récompense quotidienne."
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
    async def daily(
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
                    "Serveur requis",
                    (
                        "Cette commande doit être utilisée "
                        "dans un serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        if not isinstance(
            interaction.user,
            discord.Member,
        ):
            await interaction.followup.send(
                embed=error_embed(
                    "Membre introuvable",
                    (
                        "Impossible de retrouver ton compte "
                        "sur ce serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        try:
            result = await self.claim_daily_reward(
                guild_id=guild.id,
                user_id=interaction.user.id,
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible d'attribuer la récompense "
                    "quotidienne de %s sur le serveur %s."
                ),
                interaction.user.id,
                guild.id,
            )

            await interaction.followup.send(
                embed=error_embed(
                    "Erreur",
                    (
                        "Ta récompense quotidienne n'a pas "
                        "pu être récupérée.\n"
                        "Consulte les logs du bot."
                    ),
                ),
                ephemeral=True,
            )
            return

        if result.status == "disabled":
            await interaction.followup.send(
                embed=warning_embed(
                    "Système désactivé",
                    (
                        "Les récompenses quotidiennes sont "
                        "actuellement désactivées sur ce serveur."
                    ),
                ),
                ephemeral=True,
            )
            return

        if result.status == "cooldown":
            next_claim_at = result.next_claim_at

            if next_claim_at is None:
                remaining = timedelta()
                timestamp_text = ""
            else:
                current_time = datetime.now(
                    timezone.utc
                )

                remaining = max(
                    timedelta(),
                    next_claim_at - current_time,
                )

                unix_timestamp = int(
                    next_claim_at.timestamp()
                )

                timestamp_text = (
                    f"\nDisponible <t:{unix_timestamp}:R>."
                )

            await interaction.followup.send(
                embed=warning_embed(
                    "Récompense déjà récupérée",
                    (
                        "Tu as déjà récupéré ta récompense "
                        "quotidienne aujourd'hui.\n\n"
                        f"⏱️ Temps restant : "
                        f"**{format_duration(remaining)}**"
                        f"{timestamp_text}\n"
                        f"🔥 Série actuelle : "
                        f"**{result.current_streak} jour(s)**"
                    ),
                ),
                ephemeral=True,
            )
            return

        granted_roles: list[
            discord.Role
        ] = []

        if result.new_level > result.old_level:
            granted_roles = (
                await self.update_member_level_role(
                    guild=guild,
                    member=interaction.user,
                    level=result.new_level,
                )
            )

        settings = await self.get_settings(
            guild.id
        )

        reward_lines = [
            (
                f"✨ **{format_number(result.xp_reward)} XP**"
            ),
            (
                f"💰 **{format_number(result.coins_reward)} pièces**"
            ),
        ]

        if result.applied_rule is not None:
            rule_name = str(
                result.applied_rule.get(
                    "name",
                    "Bonus de série",
                )
            )

            reward_lines.append(
                (
                    f"\n🔥 Bonus appliqué : "
                    f"**{rule_name}**"
                )
            )

            if (
                result.xp_multiplier
                > Decimal("1")
            ):
                reward_lines.append(
                    (
                        "• Multiplicateur XP : "
                        f"**×{format_multiplier(result.xp_multiplier)}**"
                    )
                )

            if (
                result.coins_multiplier
                > Decimal("1")
            ):
                reward_lines.append(
                    (
                        "• Multiplicateur pièces : "
                        f"**×{format_multiplier(result.coins_multiplier)}**"
                    )
                )

            fixed_xp_bonus = int(
                result.applied_rule.get(
                    "xp_bonus",
                    0,
                )
            )

            fixed_coins_bonus = int(
                result.applied_rule.get(
                    "coins_bonus",
                    0,
                )
            )

            if fixed_xp_bonus > 0:
                reward_lines.append(
                    (
                        "• Bonus fixe : "
                        f"**+{format_number(fixed_xp_bonus)} XP**"
                    )
                )

            if fixed_coins_bonus > 0:
                reward_lines.append(
                    (
                        "• Bonus fixe : "
                        f"**+{format_number(fixed_coins_bonus)} pièces**"
                    )
                )

        information_lines = [
            (
                f"\n🔥 Série actuelle : "
                f"**{result.current_streak} jour(s)**"
            ),
            (
                f"🏆 Meilleure série : "
                f"**{result.best_streak} jour(s)**"
            ),
            (
                f"🎁 Récompenses récupérées : "
                f"**{format_number(result.total_claims)}**"
            ),
        ]

        next_bonus = self.find_next_bonus(
            rules=settings["bonus_rules"],
            current_streak=result.current_streak,
        )

        if next_bonus is not None:
            next_bonus_day, next_rule = (
                next_bonus
            )

            days_remaining = max(
                0,
                next_bonus_day
                - result.current_streak,
            )

            next_rule_name = str(
                next_rule.get(
                    "name",
                    "Bonus de série",
                )
            )

            information_lines.append(
                (
                    f"🎯 Prochain bonus : **{next_rule_name}** "
                    f"dans **{days_remaining} jour(s)** "
                    f"(jour {next_bonus_day})"
                )
            )

        if result.new_level > result.old_level:
            information_lines.append(
                (
                    f"\n🌟 Tu as atteint le "
                    f"**niveau {result.new_level}** !"
                )
            )

        if granted_roles:
            information_lines.append(
                (
                    "🎭 Nouveau rôle : "
                    + ", ".join(
                        role.mention
                        for role in granted_roles
                    )
                )
            )

        if result.next_claim_at is not None:
            unix_timestamp = int(
                result.next_claim_at.timestamp()
            )

            information_lines.append(
                (
                    f"\n⏱️ Prochaine récompense "
                    f"<t:{unix_timestamp}:R>."
                )
            )

        description = (
            "Tu as récupéré ta récompense quotidienne !\n\n"
            + "\n".join(reward_lines)
            + "\n"
            + "\n".join(information_lines)
        )

        await interaction.followup.send(
            embed=success_embed(
                "Récompense récupérée",
                description,
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="quotidien-admin",
        description=(
            "Configure les récompenses quotidiennes."
        ),
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.guild_only()
    async def daily_admin(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
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

        try:
            embed = await self.build_admin_embed(
                guild.id
            )
        except Exception:
            LOGGER.exception(
                (
                    "Impossible d'ouvrir la configuration "
                    "quotidienne du serveur %s."
                ),
                guild.id,
            )

            await interaction.response.send_message(
                embed=error_embed(
                    "Erreur",
                    (
                        "La configuration n'a pas "
                        "pu être chargée."
                    ),
                ),
                ephemeral=True,
            )
            return

        view = DailyAdminView(
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
    cog = DailyCog(
        bot
    )

    await cog.initialize_database()

    await bot.add_cog(
        cog
    )

    LOGGER.info(
        "Système permanent de récompenses quotidiennes initialisé"
    )
