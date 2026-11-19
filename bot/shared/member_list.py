"""
Listes de membres en tableau aligné (bloc de code), avec pages.

Utilisé par « Donner aux membres actuels » (/bienvenue-admin) et par
/membres-role. Le tableau reste assez étroit pour ne pas passer à la
ligne dans un embed : n°, nom du compte (pas le pseudo du serveur),
ID et date d'arrivée.
"""

from __future__ import annotations

import io
from typing import Any

import discord

MEMBERS_PER_PAGE = 15
NAME_WIDTH = 20
# Largeur d'un bloc de code dans un embed Discord avant retour à la ligne.
TABLE_MAX_WIDTH = 50


def short(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def join_date(member: Any, short_year: bool = False) -> str:
    joined = getattr(member, "joined_at", None)
    return joined.strftime("%d/%m/%y" if short_year else "%d/%m/%Y") if joined else "—"


def sort_by_join(members: list[Any]) -> list[Any]:
    """Les plus anciens membres d'abord, ceux sans date à la fin."""
    return sorted(
        members,
        key=lambda member: (getattr(member, "joined_at", None) is None, getattr(member, "joined_at", None) or 0),
    )


def member_table(members: list[Any], start: int = 0) -> str:
    """Tableau aligné et compact : n°, nom du compte, ID, arrivée."""
    if not members:
        return "Aucun membre."

    number_width = len(str(start + len(members)))
    name_width = max(6, min(NAME_WIDTH, max(len(member.name) for member in members)))
    id_width = max(2, max(len(str(member.id)) for member in members))
    total = number_width + 1 + name_width + 1 + id_width + 1 + 10
    short_year = total > TABLE_MAX_WIDTH
    date_width = 8 if short_year else 10

    def row(number: str, name: str, user_id: str, date: str) -> str:
        return f"{number:>{number_width}} {name:<{name_width}} {user_id:<{id_width}} {date}".rstrip()

    lines = [row("#", "Compte", "ID", "Arrivée")]
    lines.append("─" * (number_width + name_width + id_width + date_width + 3))

    for number, member in enumerate(members, start + 1):
        lines.append(
            row(str(number), short(member.name, name_width), str(member.id), join_date(member, short_year))
        )

    return "\n".join(lines)


def member_list_file(members: list[Any], header: str, filename: str) -> discord.File:
    """Liste complète en .txt (noms entiers, avec le pseudo du serveur en plus)."""
    rows = [
        f"{number:>4}  {member.name:<32}  {member.id:<19}  {join_date(member):<10}  {member.display_name}"
        for number, member in enumerate(members, 1)
    ]
    table = f"{'#':>4}  {'Compte':<32}  {'ID':<19}  {'Arrivée':<10}  Pseudo sur le serveur\n" + "\n".join(rows)
    content = f"{header}\n\n{table}\n"
    return discord.File(io.BytesIO(content.encode("utf-8")), filename=filename)


class MemberPagesView(discord.ui.View):
    """
    Base des listes de membres : pages ◀️ ▶️ et bouton 📄 Liste complète.

    Les sous-classes définissent `embed()` et `list_file()`.
    """

    def __init__(self, owner_id: int, members: list[Any], *, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.set_members(members)

    def set_members(self, members: list[Any]) -> None:
        self.members = sort_by_join(members)
        self.page = 0
        self.pages = max(1, -(-len(self.members) // MEMBERS_PER_PAGE))
        self.update_buttons()

    def page_members(self) -> tuple[list[Any], int]:
        start = self.page * MEMBERS_PER_PAGE
        return self.members[start:start + MEMBERS_PER_PAGE], start

    def table(self) -> str:
        shown, start = self.page_members()
        return f"```\n{member_table(shown, start)}\n```"

    def footer(self) -> str:
        return f"Page {self.page + 1}/{self.pages} · triés par date d'arrivée · 📄 pour la liste complète"

    def update_buttons(self) -> None:
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.pages - 1
        paged = self.pages > 1

        for button in (self.previous_page, self.next_page):
            if paged and button not in self.children:
                self.add_item(button)
            elif not paged and button in self.children:
                self.remove_item(button)

    def embed(self) -> discord.Embed:
        raise NotImplementedError

    def list_file(self) -> discord.File:
        raise NotImplementedError

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="Liste complète", emoji="📄", style=discord.ButtonStyle.secondary, row=0)
    async def full_list(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(file=self.list_file(), ephemeral=True)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.pages - 1, self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)
