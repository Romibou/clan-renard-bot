from __future__ import annotations

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
        channel = self.values[0]

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

        elif self.action == "shop_configure":
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
                label="Ajouter une récompense message",
                value="reward_message",
                emoji="💬",
            ),
            discord.SelectOption(
                label="Ajouter une récompense points",
                value="reward_points",
                emoji="⭐",
            ),
            discord.SelectOption(
                label="Ajouter une récompense rôle",
                value="reward_role",
                emoji="🎭",
            ),
            discord.SelectOption(
                label="Ajouter une récompense aléatoire",
                value="reward_random",
                emoji="🎲",
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
                label="Ajouter un article à la boutique",
                value="shop_configure",
                emoji="🛍️",
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

        elif action == "shop_configure":
            picker = AdminRoleSelect(
                action="shop_configure",
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
