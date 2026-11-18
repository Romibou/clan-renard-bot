from __future__ import annotations

import unicodedata
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.features.advent.constants import (
    CATCHUP_DISABLED,
    CATCHUP_ENABLED,
)
from bot.shared.embeds import (
    base_embed,
    error_embed,
    success_embed,
)


async def send_error(
    interaction: discord.Interaction,
    description: str,
) -> None:
    embed = error_embed(
        "Action impossible",
        description,
    )

    if interaction.response.is_done():
        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


def get_cog(
    interaction: discord.Interaction,
    name: str,
) -> Any | None:
    get_cog_method = getattr(
        interaction.client,
        "get_cog",
        None,
    )

    if get_cog_method is None:
        return None

    return get_cog_method(name)


async def invoke_command(
    interaction: discord.Interaction,
    cog_name: str,
    command_name: str,
    *args: Any,
    **kwargs: Any,
) -> None:
    cog = get_cog(
        interaction,
        cog_name,
    )

    if cog is None:
        await send_error(
            interaction,
            f"Le module `{cog_name}` est indisponible.",
        )
        return

    command = getattr(
        cog,
        command_name,
        None,
    )

    if command is None:
        await send_error(
            interaction,
            f"L'action `{command_name}` est introuvable.",
        )
        return

    callback = getattr(
        command,
        "callback",
        None,
    )

    if callback is None:
        await send_error(
            interaction,
            f"L'action `{command_name}` ne peut pas être exécutée.",
        )
        return

    await callback(
        cog,
        interaction,
        *args,
        **kwargs,
    )


def optional_year(value: str) -> int | None:
    normalized = value.strip()

    if not normalized:
        return None

    year = int(normalized)

    if not 2020 <= year <= 2200:
        raise ValueError(
            "L'année doit être comprise entre 2020 et 2200."
        )

    return year


def required_int(
    value: str,
    *,
    minimum: int,
    maximum: int,
    field_name: str,
) -> int:
    try:
        result = int(value.strip())
    except ValueError as error:
        raise ValueError(
            f"{field_name} doit être un nombre entier."
        ) from error

    if not minimum <= result <= maximum:
        raise ValueError(
            f"{field_name} doit être compris entre "
            f"{minimum} et {maximum}."
        )

    return result


class AdminModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        action: str,
    ) -> None:
        self.action = action
        self.inputs: dict[str, discord.ui.TextInput] = {}

        titles = {
            "initialize": "Initialiser une campagne",
            "timezone": "Modifier le fuseau",
            "hour": "Modifier l'heure",
            "reward_message": "Récompense message",
            "reward_points": "Récompense points",
            "reward_random": "Récompense aléatoire",
            "reward_coins": "Récompense en pièces",
            "reward_xp": "Récompense en XP",
            "reward_cosmetic": "Récompense cosmétique",
            "reward_delete": "Supprimer une récompense",
            "shop_delete": "Supprimer un article",
        }

        super().__init__(
            title=titles.get(
                action,
                "Administration Avent",
            ),
            timeout=300,
        )

        if action == "initialize":
            self.add_input(
                "year",
                "Année",
                placeholder="2026",
            )
            self.add_input(
                "timezone",
                "Fuseau horaire",
                placeholder="Europe/Paris",
                default="Europe/Paris",
            )
            self.add_input(
                "title",
                "Titre du calendrier",
                default="Calendrier de l'Avent",
                max_length=60,
            )

        elif action == "timezone":
            self.add_input(
                "timezone",
                "Nouveau fuseau",
                placeholder="Europe/Paris",
            )
            self.add_input(
                "year",
                "Année facultative",
                required=False,
                placeholder="Laisser vide pour la campagne actuelle",
            )

        elif action == "hour":
            self.add_input(
                "hour",
                "Heure d'ouverture",
                placeholder="0",
            )
            self.add_input(
                "year",
                "Année facultative",
                required=False,
            )

        elif action == "reward_message":
            self.add_input(
                "day",
                "Jour",
                placeholder="1 à 24",
            )
            self.add_input(
                "message",
                "Message reçu par le membre",
                style=discord.TextStyle.paragraph,
                max_length=1000,
            )
            self.add_input(
                "year",
                "Année facultative",
                required=False,
            )

        elif action == "reward_points":
            self.add_input(
                "day",
                "Jour",
                placeholder="1 à 24",
            )
            self.add_input(
                "points",
                "Nombre de points",
                placeholder="100",
            )
            self.add_input(
                "message",
                "Message facultatif",
                required=False,
                style=discord.TextStyle.paragraph,
                max_length=1000,
            )
            self.add_input(
                "year",
                "Année facultative",
                required=False,
            )

        elif action in ("reward_coins", "reward_xp"):
            unit = "pièces" if action == "reward_coins" else "XP"

            self.add_input(
                "day",
                "Jour",
                placeholder="1 à 24",
            )
            self.add_input(
                "amount",
                f"Nombre de {unit}",
                placeholder="200",
            )
            self.add_input(
                "message",
                "Message facultatif",
                required=False,
                style=discord.TextStyle.paragraph,
                max_length=1000,
            )
            self.add_input(
                "year",
                "Année facultative",
                required=False,
            )

        elif action == "reward_cosmetic":
            self.add_input(
                "day",
                "Jour",
                placeholder="1 à 24",
            )
            self.add_input(
                "identifier",
                "Identifiant du cosmétique (/profil-admin)",
                placeholder="cadre-givre",
                max_length=50,
            )
            self.add_input(
                "message",
                "Message facultatif",
                required=False,
                style=discord.TextStyle.paragraph,
                max_length=1000,
            )
            self.add_input(
                "year",
                "Année facultative",
                required=False,
            )

        elif action == "reward_random":
            self.add_input(
                "day",
                "Jour",
                placeholder="1 à 24",
            )
            self.add_input(
                "json",
                "Configuration JSON",
                style=discord.TextStyle.paragraph,
                max_length=4000,
                placeholder=(
                    '[{"type":"points","weight":1,'
                    '"data":{"points":100}}]'
                ),
            )
            self.add_input(
                "year",
                "Année facultative",
                required=False,
            )

        elif action == "reward_delete":
            self.add_input(
                "day",
                "Jour à supprimer",
                placeholder="1 à 24",
            )
            self.add_input(
                "year",
                "Année facultative",
                required=False,
            )

        elif action == "shop_delete":
            self.add_input(
                "identifier",
                "Identifiant de l'article",
                placeholder="role-noel-2026",
            )
            self.add_input(
                "year",
                "Année facultative",
                required=False,
            )

    def add_input(
        self,
        key: str,
        label: str,
        *,
        placeholder: str | None = None,
        default: str | None = None,
        required: bool = True,
        style: discord.TextStyle = discord.TextStyle.short,
        max_length: int | None = None,
    ) -> None:
        text_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            default=default,
            required=required,
            style=style,
            max_length=max_length,
        )

        self.inputs[key] = text_input
        self.add_item(text_input)

    def value(self, key: str) -> str:
        return str(self.inputs[key].value or "")

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            if self.action == "initialize":
                year = required_int(
                    self.value("year"),
                    minimum=2020,
                    maximum=2200,
                    field_name="L'année",
                )

                await invoke_command(
                    interaction,
                    "AdventAdminCommands",
                    "initialize_campaign",
                    year,
                    self.value("timezone").strip(),
                    self.value("title").strip(),
                )

            elif self.action == "timezone":
                await invoke_command(
                    interaction,
                    "AdventAdminCommands",
                    "set_timezone",
                    self.value("timezone").strip(),
                    optional_year(
                        self.value("year")
                    ),
                )

            elif self.action == "hour":
                hour = required_int(
                    self.value("hour"),
                    minimum=0,
                    maximum=23,
                    field_name="L'heure",
                )

                await invoke_command(
                    interaction,
                    "AdventAdminCommands",
                    "set_opening_hour",
                    hour,
                    optional_year(
                        self.value("year")
                    ),
                )

            elif self.action == "reward_message":
                day = required_int(
                    self.value("day"),
                    minimum=1,
                    maximum=24,
                    field_name="Le jour",
                )

                await invoke_command(
                    interaction,
                    "AdventAdminRewardsCommands",
                    "reward_message",
                    day,
                    self.value("message").strip(),
                    optional_year(
                        self.value("year")
                    ),
                )

            elif self.action == "reward_points":
                day = required_int(
                    self.value("day"),
                    minimum=1,
                    maximum=24,
                    field_name="Le jour",
                )
                points = required_int(
                    self.value("points"),
                    minimum=0,
                    maximum=1_000_000,
                    field_name="Le nombre de points",
                )
                message = (
                    self.value("message").strip()
                    or None
                )

                await invoke_command(
                    interaction,
                    "AdventAdminRewardsCommands",
                    "reward_points",
                    day,
                    points,
                    message,
                    optional_year(
                        self.value("year")
                    ),
                )

            elif self.action == "reward_random":
                day = required_int(
                    self.value("day"),
                    minimum=1,
                    maximum=24,
                    field_name="Le jour",
                )

                await invoke_command(
                    interaction,
                    "AdventAdminRewardsCommands",
                    "reward_random",
                    day,
                    self.value("json").strip(),
                    optional_year(
                        self.value("year")
                    ),
                )

            elif self.action in (
                "reward_coins",
                "reward_xp",
                "reward_cosmetic",
            ):
                day = required_int(
                    self.value("day"),
                    minimum=1,
                    maximum=24,
                    field_name="Le jour",
                )
                year = optional_year(self.value("year"))
                message = self.value("message").strip() or None

                cog = get_cog(
                    interaction,
                    "AdventAdminRewardsCommands",
                )

                if cog is None:
                    await send_error(
                        interaction,
                        "Le module des récompenses est indisponible.",
                    )
                    return

                if self.action == "reward_cosmetic":
                    await interaction.response.defer(
                        ephemeral=True,
                        thinking=True,
                    )
                    await cog.save_cosmetic_reward(
                        interaction,
                        day=day,
                        identifier=self.value("identifier").strip(),
                        message=message,
                        year=year,
                    )
                else:
                    amount = required_int(
                        self.value("amount"),
                        minimum=1,
                        maximum=1_000_000,
                        field_name="La quantité",
                    )
                    await interaction.response.defer(
                        ephemeral=True,
                        thinking=True,
                    )
                    await cog.save_amount_reward(
                        interaction,
                        day=day,
                        reward_type=(
                            "coins"
                            if self.action == "reward_coins"
                            else "xp"
                        ),
                        amount=amount,
                        message=message,
                        year=year,
                    )

            elif self.action == "reward_delete":
                day = required_int(
                    self.value("day"),
                    minimum=1,
                    maximum=24,
                    field_name="Le jour",
                )

                await invoke_command(
                    interaction,
                    "AdventAdminRewardsCommands",
                    "delete_reward",
                    day,
                    optional_year(
                        self.value("year")
                    ),
                )

            elif self.action == "shop_delete":
                await invoke_command(
                    interaction,
                    "AdventShop",
                    "delete_shop_item",
                    self.value("identifier").strip(),
                    optional_year(
                        self.value("year")
                    ),
                )

        except ValueError as error:
            await send_error(
                interaction,
                str(error),
            )


class RewardRoleModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        role: discord.Role,
    ) -> None:
        super().__init__(
            title="Récompense rôle",
            timeout=300,
        )

        self.role = role

        self.day = discord.ui.TextInput(
            label="Jour",
            placeholder="1 à 24",
        )
        self.message = discord.ui.TextInput(
            label="Message facultatif",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )
        self.year = discord.ui.TextInput(
            label="Année facultative",
            required=False,
        )

        self.add_item(self.day)
        self.add_item(self.message)
        self.add_item(self.year)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            day = required_int(
                str(self.day.value),
                minimum=1,
                maximum=24,
                field_name="Le jour",
            )

            await invoke_command(
                interaction,
                "AdventAdminRewardsCommands",
                "reward_role",
                day,
                self.role,
                str(self.message.value).strip() or None,
                optional_year(
                    str(self.year.value)
                ),
            )

        except ValueError as error:
            await send_error(
                interaction,
                str(error),
            )


class ShopConfigureModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        role: discord.Role,
    ) -> None:
        super().__init__(
            title="Configurer un article",
            timeout=300,
        )

        self.role = role

        self.identifier = discord.ui.TextInput(
            label="Identifiant unique",
            placeholder="role-noel-2026",
            max_length=50,
        )
        self.name = discord.ui.TextInput(
            label="Nom affiché",
            placeholder="Rôle spécial Noël",
            max_length=100,
        )
        self.price = discord.ui.TextInput(
            label="Prix en points",
            placeholder="500",
        )
        self.minimum = discord.ui.TextInput(
            label="Cases minimum",
            placeholder="0 à 24",
            default="0",
        )
        self.message = discord.ui.TextInput(
            label="Message après l'achat",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )

        self.add_item(self.identifier)
        self.add_item(self.name)
        self.add_item(self.price)
        self.add_item(self.minimum)
        self.add_item(self.message)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            price = required_int(
                str(self.price.value),
                minimum=0,
                maximum=1_000_000,
                field_name="Le prix",
            )
            minimum = required_int(
                str(self.minimum.value),
                minimum=0,
                maximum=24,
                field_name="Le minimum de cases",
            )

            await invoke_command(
                interaction,
                "AdventShop",
                "configure_shop_item",
                str(self.identifier.value).strip(),
                str(self.name.value).strip(),
                self.role,
                price,
                minimum,
                str(self.message.value).strip(),
                "",
                "🎁",
                None,
            )

        except ValueError as error:
            await send_error(
                interaction,
                str(error),
            )


class AdminChannelSelect(discord.ui.ChannelSelect):
    def __init__(
        self,
        *,
        action: str,
    ) -> None:
        self.action = action

        super().__init__(
            placeholder="Choisis un salon textuel…",
            min_values=1,
            max_values=1,
            channel_types=[
                discord.ChannelType.text,
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        # Le menu renvoie un salon « partiel » (AppCommandChannel) :
        # on récupère le vrai salon du serveur avant de le vérifier.
        selected = self.values[0]
        channel = (
            interaction.guild.get_channel(selected.id)
            if interaction.guild is not None
            else None
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await send_error(
                interaction,
                "Choisis un salon textuel classique.",
            )
            return

        if self.action == "channel":
            await invoke_command(
                interaction,
                "AdventAdminCommands",
                "set_channel",
                channel,
                None,
            )

        elif self.action == "publish":
            await invoke_command(
                interaction,
                "AdventAdminRewardsCommands",
                "publish_panel",
                channel,
                None,
            )


class AdminRoleSelect(discord.ui.RoleSelect):
    def __init__(
        self,
        *,
        action: str,
    ) -> None:
        self.action = action

        super().__init__(
            placeholder="Choisis un rôle…",
            min_values=1,
            max_values=1,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        role = self.values[0]

        if not isinstance(role, discord.Role):
            await send_error(
                interaction,
                "Le rôle sélectionné est invalide.",
            )
            return

        if self.action == "announcements":
            await invoke_command(
                interaction,
                "AdventAdminCommands",
                "set_announcements",
                True,
                role,
                None,
            )

        elif self.action == "reward_role":
            await interaction.response.send_modal(
                RewardRoleModal(
                    role=role,
                )
            )

        elif self.action == "shop_role":
            await interaction.response.send_modal(
                ShopConfigureModal(
                    role=role,
                )
            )


class AdminUserSelect(discord.ui.UserSelect):
    def __init__(
        self,
        *,
        action: str,
    ) -> None:
        self.action = action

        super().__init__(
            placeholder="Choisis un membre…",
            min_values=1,
            max_values=1,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await send_error(
                interaction,
                "Cette action doit être utilisée dans un serveur.",
            )
            return

        selected_user = self.values[0]

        member = guild.get_member(
            selected_user.id
        )

        if member is None:
            try:
                member = await guild.fetch_member(
                    selected_user.id
                )
            except discord.HTTPException:
                await send_error(
                    interaction,
                    "Impossible de retrouver ce membre.",
                )
                return

        if self.action == "inspect_user":
            await invoke_command(
                interaction,
                "AdventAdminRewardsCommands",
                "inspect_user",
                member,
                None,
            )

        elif self.action == "reset_user":
            await invoke_command(
                interaction,
                "AdventAdminRewardsCommands",
                "reset_user",
                member,
                None,
            )


class PickerView(discord.ui.View):
    def __init__(
        self,
        *,
        owner_id: int,
        picker: discord.ui.Item,
    ) -> None:
        super().__init__(
            timeout=180,
        )

        self.owner_id = owner_id
        self.add_item(picker)

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


def parse_catchup_days(
    text: str,
) -> tuple[str, int | None]:
    """
    Interprète la saisie du formulaire de rattrapage.

    - vide         → ("unlimited", None) : rattrapage sans limite ;
    - 0            → ("disabled", None)  : rattrapage désactivé ;
    - 1 à 23       → ("limited", n)      : n jours en arrière au plus.
    """
    cleaned = text.strip().lower().removesuffix("jours").removesuffix(
        "jour"
    ).removesuffix("j").strip()

    if not cleaned:
        return "unlimited", None

    if not cleaned.isdigit():
        raise ValueError(
            "Écris un nombre entre 0 et 23 (ou laisse vide)."
        )

    days = int(cleaned)

    if days == 0:
        return "disabled", None

    if days > 23:
        raise ValueError(
            "Le calendrier n'a que 24 cases : 23 jours au maximum."
        )

    return "limited", days


class CatchupDaysModal(
    discord.ui.Modal,
    title="Limite du rattrapage",
):
    days = discord.ui.TextInput(
        label="Nombre de jours de rattrapage maximum",
        placeholder="Ex. 3 • 0 = pas de rattrapage • vide = sans limite",
        required=False,
        max_length=10,
    )

    def __init__(
        self,
        *,
        current: int | None,
        catchup_enabled: bool,
    ) -> None:
        super().__init__(timeout=300)

        if not catchup_enabled:
            self.days.default = "0"
        elif current is not None:
            self.days.default = str(current)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            mode, days = parse_catchup_days(
                str(self.days.value)
            )
        except ValueError as error:
            await send_error(
                interaction,
                str(error),
            )
            return

        cog = get_cog(
            interaction,
            "AdventAdminCommands",
        )

        if cog is None or interaction.guild_id is None:
            await send_error(
                interaction,
                "Le module administratif est indisponible.",
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        try:
            campaign = await cog._campaign(
                interaction.guild_id,
                None,
            )
        except Exception as error:
            await send_error(
                interaction,
                str(error),
            )
            return

        await cog.repository.update_campaign_catchup(
            campaign.id,
            CATCHUP_DISABLED if mode == "disabled" else CATCHUP_ENABLED,
        )
        await cog.repository.update_campaign_catchup_days(
            campaign.id,
            days,
        )
        await cog._audit(
            interaction,
            campaign_id=campaign.id,
            action="campaign_catchup_days_changed",
            details={
                "mode": mode,
                "catchup_days": days,
            },
        )

        if mode == "disabled":
            description = (
                "Rattrapage **désactivé** : une case non ouverte le "
                "jour même est manquée."
            )
        elif mode == "unlimited":
            description = (
                "Rattrapage **activé sans limite** : les membres "
                "peuvent ouvrir toutes les cases passées."
            )
        else:
            example_day = max(10, days + 2)
            first = example_day - days
            description = (
                f"Rattrapage **activé** sur les **{days} dernier(s) "
                f"jour(s)**.\n\nExemple : le {example_day} décembre, "
                f"les cases {first} à {example_day - 1} peuvent encore "
                "être ouvertes ; les plus anciennes sont manquées."
            )

        await interaction.followup.send(
            embed=success_embed(
                "Rattrapage enregistré",
                description,
            ),
            ephemeral=True,
        )


async def open_catchup_days_modal(
    interaction: discord.Interaction,
) -> None:
    cog = get_cog(
        interaction,
        "AdventAdminCommands",
    )

    if cog is None or interaction.guild_id is None:
        await send_error(
            interaction,
            "Le module administratif est indisponible.",
        )
        return

    try:
        campaign = await cog._campaign(
            interaction.guild_id,
            None,
        )
    except Exception as error:
        await send_error(
            interaction,
            str(error),
        )
        return

    await interaction.response.send_modal(
        CatchupDaysModal(
            current=campaign.catchup_days,
            catchup_enabled=campaign.catchup_mode == CATCHUP_ENABLED,
        )
    )


RESET_ALL_CONFIRMATION_WORD = "REINITIALISER"


def normalize_confirmation(
    text: str,
) -> str:
    """« Réinitialiser », « RÉINITIALISER »… → « REINITIALISER »."""
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .upper()
    )


class ResetAllConfirmModal(
    discord.ui.Modal,
    title="Réinitialiser tout le monde",
):
    confirmation = discord.ui.TextInput(
        label="Tape RÉINITIALISER pour confirmer",
        placeholder="RÉINITIALISER",
        min_length=1,
        max_length=30,
    )

    def __init__(
        self,
        *,
        campaign_id: int,
        year: int,
    ) -> None:
        super().__init__(timeout=120)
        self.campaign_id = campaign_id
        self.year = year

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if (
            normalize_confirmation(str(self.confirmation.value))
            != RESET_ALL_CONFIRMATION_WORD
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Réinitialisation annulée",
                    (
                        "Le mot de confirmation est incorrect.\n"
                        "**Aucune donnée n'a été supprimée.**"
                    ),
                ),
                ephemeral=True,
            )
            return

        cog = get_cog(
            interaction,
            "AdventAdminRewardsCommands",
        )

        if cog is None:
            await send_error(
                interaction,
                "Le module administratif est indisponible.",
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        deleted = await cog.transactions.reset_all(
            self.campaign_id
        )

        await cog._audit(
            interaction,
            campaign_id=self.campaign_id,
            action="all_users_reset",
            details=deleted,
        )

        await interaction.followup.send(
            embed=success_embed(
                "Tout le monde a été réinitialisé",
                (
                    f"Campagne **{self.year}** :\n"
                    f"• **{deleted['openings']}** case(s) ouverte(s) "
                    "supprimée(s)\n"
                    f"• **{deleted['purchases']}** achat(s) de la "
                    "boutique de l'Avent supprimé(s)\n\n"
                    "Les récompenses, la boutique et la configuration "
                    "du calendrier sont intactes."
                ),
            ),
            ephemeral=True,
        )


class ResetAllWarningView(discord.ui.View):
    """
    Premier verrou : avertissement et bouton « Je comprends ».
    Le second verrou est le mot à taper dans ResetAllConfirmModal.
    """

    def __init__(
        self,
        *,
        owner_id: int,
        campaign_id: int,
        year: int,
    ) -> None:
        super().__init__(timeout=60)
        self.owner_id = owner_id
        self.campaign_id = campaign_id
        self.year = year

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            embed=error_embed(
                "Action interdite",
                "Seul l'administrateur qui a lancé cette action peut confirmer.",
            ),
            ephemeral=True,
        )
        return False

    def _disable(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

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
        self._disable()
        self.stop()

        await interaction.response.edit_message(
            embed=base_embed(
                "Action annulée",
                "Aucune donnée n'a été supprimée.",
            ),
            view=self,
        )

    @discord.ui.button(
        label="Je comprends, continuer",
        emoji="⚠️",
        style=discord.ButtonStyle.danger,
    )
    async def proceed(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self._disable()
        self.stop()

        await interaction.response.send_modal(
            ResetAllConfirmModal(
                campaign_id=self.campaign_id,
                year=self.year,
            )
        )


async def start_reset_all(
    interaction: discord.Interaction,
) -> None:
    cog = get_cog(
        interaction,
        "AdventAdminRewardsCommands",
    )

    if cog is None or interaction.guild_id is None:
        await send_error(
            interaction,
            "Le module administratif est indisponible.",
        )
        return

    try:
        campaign = await cog._campaign(
            interaction.guild_id,
            None,
        )
    except Exception as error:
        await send_error(
            interaction,
            str(error),
        )
        return

    counts = await cog.transactions.count_campaign_data(
        campaign.id
    )

    if counts["openings"] == 0 and counts["purchases"] == 0:
        await interaction.response.send_message(
            embed=base_embed(
                "Rien à réinitialiser",
                (
                    "Aucun membre n'a ouvert de case ni acheté dans la "
                    f"boutique pour la campagne **{campaign.year}**."
                ),
            ),
            ephemeral=True,
        )
        return

    warning = error_embed(
        "⚠️ Réinitialiser TOUT LE MONDE ?",
        (
            f"Tu es sur le point d'effacer les données de l'Avent "
            f"**{campaign.year}** de **{counts['members']} membre(s)** :\n\n"
            f"• **{counts['openings']}** case(s) ouverte(s) et les "
            "points gagnés\n"
            f"• **{counts['purchases']}** achat(s) de la boutique de "
            "l'Avent\n\n"
            "**Cette action est définitive et ne peut pas être "
            "annulée.**\n"
            "Les rôles et cosmétiques déjà distribués ne sont pas "
            "retirés. Les récompenses, la boutique et la configuration "
            "restent intactes.\n\n"
            "Si tu continues, il faudra encore taper **RÉINITIALISER** "
            "pour confirmer. Ce message expire dans 60 secondes."
        ),
    )

    await interaction.response.send_message(
        embed=warning,
        view=ResetAllWarningView(
            owner_id=interaction.user.id,
            campaign_id=campaign.id,
            year=campaign.year,
        ),
        ephemeral=True,
    )


REWARD_TYPE_CHOICES = (
    ("reward_message", "Message", "💬", "Un simple message surprise."),
    ("reward_points", "Points de l'Avent", "⭐", "Points pour la boutique de l'Avent."),
    ("reward_coins", "Pièces", "💰", "Pièces permanentes (boutique /boutique)."),
    ("reward_xp", "XP", "✨", "XP permanente, peut faire monter de niveau."),
    ("reward_cosmetic", "Cosmétique de profil", "🎨", "Ajouté à l'inventaire de /profil."),
    ("reward_role", "Rôle Discord", "🎭", "Un rôle donné à l'ouverture."),
    ("reward_random", "Aléatoire", "🎲", "Tirage entre plusieurs récompenses (JSON)."),
)


class RewardTypeSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Choisis le type de récompense…",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=label,
                    value=value,
                    emoji=emoji,
                    description=description,
                )
                for value, label, emoji, description in REWARD_TYPE_CHOICES
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        action = self.values[0]

        if action == "reward_role":
            await interaction.response.edit_message(
                embed=base_embed(
                    "🎭 Choisir un rôle",
                    "Sélectionne le rôle à donner dans cette case.",
                ),
                view=PickerView(
                    owner_id=interaction.user.id,
                    picker=AdminRoleSelect(
                        action="reward_role",
                    ),
                ),
            )
            return

        await interaction.response.send_modal(
            AdminModal(
                action=action,
            )
        )


class AdminActionSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label="Afficher la configuration",
                value="configuration",
                emoji="📋",
            ),
            discord.SelectOption(
                label="Initialiser une campagne",
                value="initialize",
                emoji="🆕",
            ),
            discord.SelectOption(
                label="Activer ou désactiver",
                value="toggle_enabled",
                emoji="🔌",
            ),
            discord.SelectOption(
                label="Modifier le canal",
                value="channel",
                emoji="📢",
            ),
            discord.SelectOption(
                label="Modifier le fuseau",
                value="timezone",
                emoji="🌍",
            ),
            discord.SelectOption(
                label="Modifier l'heure d'ouverture",
                value="hour",
                emoji="🕐",
            ),
            discord.SelectOption(
                label="Activer ou désactiver le rattrapage",
                value="toggle_catchup",
                emoji="🔁",
            ),
            discord.SelectOption(
                label="Limiter le rattrapage (jours)",
                value="catchup_days",
                emoji="📅",
                description=(
                    "Choisis combien de jours en arrière les membres "
                    "peuvent rattraper."
                ),
            ),
            discord.SelectOption(
                label="Activer les annonces",
                value="announcements_on",
                emoji="🔔",
            ),
            discord.SelectOption(
                label="Désactiver les annonces",
                value="announcements_off",
                emoji="🔕",
            ),
            discord.SelectOption(
                label="Liste des récompenses",
                value="reward_list",
                emoji="🎁",
            ),
            discord.SelectOption(
                label="Ajouter ou modifier une récompense",
                value="reward_add",
                emoji="🎁",
                description=(
                    "Message, points, pièces, XP, cosmétique, rôle "
                    "ou aléatoire."
                ),
            ),
            discord.SelectOption(
                label="Supprimer une récompense",
                value="reward_delete",
                emoji="🗑️",
            ),
            discord.SelectOption(
                label="Aperçu du calendrier",
                value="preview",
                emoji="👁️",
            ),
            discord.SelectOption(
                label="Publier le panneau public",
                value="publish",
                emoji="📌",
            ),
            discord.SelectOption(
                label="Consulter un membre",
                value="inspect_user",
                emoji="🔎",
            ),
            discord.SelectOption(
                label="Réinitialiser un membre",
                value="reset_user",
                emoji="⚠️",
            ),
            discord.SelectOption(
                label="Réinitialiser TOUT LE MONDE",
                value="reset_all",
                emoji="🧨",
                description=(
                    "Efface les cases et achats de tous les membres "
                    "(double confirmation)."
                ),
            ),
            discord.SelectOption(
                label="Ajouter un rôle à la boutique",
                value="shop_role",
                emoji="🎭",
                description="Vend un rôle Discord contre des points.",
            ),
            discord.SelectOption(
                label="Ajouter un cosmétique à la boutique",
                value="shop_cosmetic",
                emoji="✨",
                description="Vend un cosmétique du profil contre des points.",
            ),
            discord.SelectOption(
                label="Supprimer un article de la boutique",
                value="shop_delete",
                emoji="🚫",
            ),
        ]

        super().__init__(
            placeholder="Choisis une action administrative…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        action = self.values[0]

        if action == "reset_all":
            await start_reset_all(interaction)
            return

        if action == "catchup_days":
            await open_catchup_days_modal(interaction)
            return

        if action == "reward_add":
            await interaction.response.send_message(
                embed=base_embed(
                    "🎁 Type de récompense",
                    (
                        "Choisis ce que la case doit donner. "
                        "Si la case a déjà une récompense, elle "
                        "sera remplacée."
                    ),
                ),
                view=PickerView(
                    owner_id=interaction.user.id,
                    picker=RewardTypeSelect(),
                ),
                ephemeral=True,
            )
            return

        if action == "configuration":
            await invoke_command(
                interaction,
                "AdventAdminCommands",
                "show_configuration",
                None,
            )
            return

        if action == "toggle_enabled":
            admin_cog = get_cog(
                interaction,
                "AdventAdminCommands",
            )

            if (
                admin_cog is None
                or interaction.guild_id is None
            ):
                await send_error(
                    interaction,
                    "Le module administratif est indisponible.",
                )
                return

            try:
                campaign = await admin_cog._campaign(
                    interaction.guild_id,
                    None,
                )
            except Exception as error:
                await send_error(
                    interaction,
                    str(error),
                )
                return

            await invoke_command(
                interaction,
                "AdventAdminCommands",
                "set_enabled",
                not campaign.enabled,
                campaign.year,
            )
            return

        if action == "toggle_catchup":
            admin_cog = get_cog(
                interaction,
                "AdventAdminCommands",
            )

            if (
                admin_cog is None
                or interaction.guild_id is None
            ):
                await send_error(
                    interaction,
                    "Le module administratif est indisponible.",
                )
                return

            try:
                campaign = await admin_cog._campaign(
                    interaction.guild_id,
                    None,
                )
            except Exception as error:
                await send_error(
                    interaction,
                    str(error),
                )
                return

            new_mode = (
                CATCHUP_DISABLED
                if campaign.catchup_mode == CATCHUP_ENABLED
                else CATCHUP_ENABLED
            )

            choice = app_commands.Choice(
                name=(
                    "Activé"
                    if new_mode == CATCHUP_ENABLED
                    else "Désactivé"
                ),
                value=new_mode,
            )

            await invoke_command(
                interaction,
                "AdventAdminCommands",
                "set_catchup",
                choice,
                campaign.year,
            )
            return

        if action == "announcements_off":
            await invoke_command(
                interaction,
                "AdventAdminCommands",
                "set_announcements",
                False,
                None,
                None,
            )
            return

        if action == "reward_list":
            await invoke_command(
                interaction,
                "AdventAdminRewardsCommands",
                "list_rewards",
                None,
            )
            return

        if action == "preview":
            await invoke_command(
                interaction,
                "AdventAdminRewardsCommands",
                "preview",
                None,
            )
            return

        modal_actions = {
            "initialize",
            "timezone",
            "hour",
            "reward_message",
            "reward_points",
            "reward_random",
            "reward_delete",
            "shop_delete",
        }

        if action in modal_actions:
            await interaction.response.send_modal(
                AdminModal(
                    action=action,
                )
            )
            return


        if action == "shop_role":
            await interaction.response.send_message(
                embed=base_embed(
                    "🎭 Choisir un rôle",
                    (
                        "Sélectionne le rôle Discord à ajouter "
                        "à la boutique."
                    ),
                ),
                view=PickerView(
                    owner_id=interaction.user.id,
                    picker=AdminRoleSelect(
                        action="shop_role",
                    ),
                ),
                ephemeral=True,
            )
            return

        if action == "shop_cosmetic":
            await interaction.response.send_modal(
                ShopCosmeticModal()
            )
            return
        

        if action == "channel":
            picker = AdminChannelSelect(
                action="channel",
            )

        elif action == "publish":
            picker = AdminChannelSelect(
                action="publish",
            )

        elif action == "announcements_on":
            picker = AdminRoleSelect(
                action="announcements",
            )

        elif action == "reward_role":
            picker = AdminRoleSelect(
                action="reward_role",
            )

        elif action == "inspect_user":
            picker = AdminUserSelect(
                action="inspect_user",
            )

        elif action == "reset_user":
            picker = AdminUserSelect(
                action="reset_user",
            )

        else:
            await send_error(
                interaction,
                "Cette action n'est pas encore disponible.",
            )
            return

        embed = base_embed(
            "Sélection nécessaire",
            "Effectue ton choix dans le menu ci-dessous.",
        )

        await interaction.response.edit_message(
            embed=embed,
            view=PickerView(
                owner_id=interaction.user.id,
                picker=picker,
            ),
        )


class AdventAdminPanelView(discord.ui.View):
    def __init__(
        self,
        *,
        owner_id: int,
    ) -> None:
        super().__init__(
            timeout=600,
        )

        self.owner_id = owner_id
        self.add_item(
            AdminActionSelect()
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Panneau personnel",
                    (
                        "Ce panneau appartient à un autre "
                        "administrateur."
                    ),
                ),
                ephemeral=True,
            )
            return False

        permissions = getattr(
            interaction.user,
            "guild_permissions",
            None,
        )

        if (
            permissions is None
            or not permissions.administrator
        ):
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission refusée",
                    "Tu dois être administrateur.",
                ),
                ephemeral=True,
            )
            return False

        return True


class AdventAdminPanel(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    @app_commands.command(
        name="avent-admin",
        description="Ouvre le panneau administratif de l'Avent.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(
        administrator=True
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def advent_admin(
        self,
        interaction: discord.Interaction,
    ) -> None:
        embed = base_embed(
            "⚙️ Administration de l'Avent",
            (
                "Toutes les fonctions du calendrier sont "
                "regroupées ici.\n\n"
                "Choisis une action dans le menu déroulant."
            ),
        )

        embed.add_field(
            name="Campagne",
            value=(
                "Initialisation, activation, fuseau, heure, "
                "canal et rattrapage."
            ),
            inline=False,
        )
        embed.add_field(
            name="Récompenses",
            value=(
                "Messages, points, rôles, récompenses "
                "aléatoires et suppression."
            ),
            inline=False,
        )
        embed.add_field(
            name="Gestion",
            value=(
                "Publication, aperçu, membres et boutique."
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            view=AdventAdminPanelView(
                owner_id=interaction.user.id,
            ),
            ephemeral=True,
        )

class ShopCosmeticModal(
    discord.ui.Modal,
    title="Ajouter un cosmétique à la boutique",
):
    cosmetic_identifier = discord.ui.TextInput(
        label="Identifiant du cosmétique",
        placeholder="Exemple : fond-hiver-2026",
        min_length=1,
        max_length=50,
    )

    price = discord.ui.TextInput(
        label="Prix en points",
        placeholder="Exemple : 500",
        min_length=1,
        max_length=10,
    )

    minimum = discord.ui.TextInput(
        label="Cases minimum",
        placeholder="Entre 0 et 24",
        default="0",
        min_length=1,
        max_length=2,
    )

    emoji = discord.ui.TextInput(
        label="Emoji",
        placeholder="✨",
        default="✨",
        required=False,
        max_length=100,
    )

    message = discord.ui.TextInput(
        label="Message après l'achat",
        placeholder="Félicitations !",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            price = int(str(self.price))
            minimum = int(str(self.minimum))
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(
                    "Valeur invalide",
                    (
                        "Le prix et le nombre de cases "
                        "doivent être des nombres entiers."
                    ),
                ),
                ephemeral=True,
            )
            return

        if price < 0 or price > 1_000_000:
            await interaction.response.send_message(
                embed=error_embed(
                    "Prix invalide",
                    (
                        "Le prix doit être compris "
                        "entre 0 et 1 000 000."
                    ),
                ),
                ephemeral=True,
            )
            return

        if minimum < 0 or minimum > 24:
            await interaction.response.send_message(
                embed=error_embed(
                    "Condition invalide",
                    (
                        "Le nombre de cases doit être "
                        "compris entre 0 et 24."
                    ),
                ),
                ephemeral=True,
            )
            return

        shop_cog = interaction.client.get_cog(
            "AdventShop"
        )

        if shop_cog is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Boutique indisponible",
                    (
                        "Le module de la boutique "
                        "n'est pas chargé."
                    ),
                ),
                ephemeral=True,
            )
            return

        command = getattr(
            shop_cog,
            "configure_cosmetic_item",
            None,
        )
        callback = getattr(
            command,
            "callback",
            None,
        )

        if callback is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Commande introuvable",
                    (
                        "La commande de configuration "
                        "des cosmétiques est introuvable."
                    ),
                ),
                ephemeral=True,
            )
            return

        await callback(
            shop_cog,
            interaction,
            str(self.cosmetic_identifier).strip(),
            price,
            minimum,
            str(self.message).strip(),
            str(self.emoji).strip() or "✨",
            None,
        )
