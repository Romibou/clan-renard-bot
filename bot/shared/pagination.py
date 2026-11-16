from __future__ import annotations

import math
from typing import Any

import discord

# Un menu déroulant Discord contient au maximum 25 choix.
SELECT_PAGE_SIZE = 25


def count_pages(
    item_count: int,
) -> int:
    return max(
        1,
        math.ceil(item_count / SELECT_PAGE_SIZE),
    )


def resolve_page(
    identifiers: list[str],
    selected: str | None,
    page: int,
) -> tuple[int, str | None]:
    """
    Retourne la page à afficher et l'article sélectionné.

    - L'article sélectionné existe : on affiche sa page.
    - Sinon : on garde la page demandée (bornée) et on sélectionne
      son premier article.
    """
    if not identifiers:
        return 0, None

    if selected in identifiers:
        return (
            identifiers.index(selected) // SELECT_PAGE_SIZE,
            selected,
        )

    page = min(
        max(page, 0),
        count_pages(len(identifiers)) - 1,
    )

    return page, identifiers[page * SELECT_PAGE_SIZE]


class PageButton(discord.ui.Button):
    def __init__(
        self,
        *,
        delta: int,
        row: int,
    ) -> None:
        self.delta = delta

        super().__init__(
            emoji="◀️" if delta < 0 else "▶️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        view: Any = self.view
        await view.change_page(interaction, self.delta)


class PageIndicator(discord.ui.Button):
    def __init__(
        self,
        *,
        row: int,
    ) -> None:
        super().__init__(
            label="Page 1/1",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=row,
        )


class PaginatedSelectMixin:
    """
    Ajoute des pages à une vue dont le menu déroulant liste plus de
    25 articles.

    La vue doit posséder `selected_identifier` et une méthode
    `async refresh(interaction)` qui reconstruit l'affichage.
    Les boutons de page n'apparaissent que s'il y a plus d'une page.
    """

    selected_identifier: str | None

    def setup_pagination(
        self,
        *,
        row: int,
    ) -> None:
        self.page = 0
        self.page_count = 1
        self.item_identifiers: list[str] = []
        self.previous_page_button = PageButton(delta=-1, row=row)
        self.page_indicator = PageIndicator(row=row)
        self.next_page_button = PageButton(delta=1, row=row)

    def apply_pagination(
        self,
        identifiers: list[str],
    ) -> slice:
        """
        Met à jour la page et les boutons, puis retourne la tranche
        d'articles à placer dans le menu déroulant.
        """
        view: Any = self

        self.item_identifiers = identifiers
        self.page, self.selected_identifier = resolve_page(
            identifiers,
            self.selected_identifier,
            self.page,
        )
        self.page_count = count_pages(len(identifiers))

        buttons = (
            self.previous_page_button,
            self.page_indicator,
            self.next_page_button,
        )

        for button in buttons:
            view.remove_item(button)

        if self.page_count > 1:
            self.previous_page_button.disabled = self.page <= 0
            self.next_page_button.disabled = (
                self.page >= self.page_count - 1
            )
            self.page_indicator.label = (
                f"Page {self.page + 1}/{self.page_count}"
            )

            for button in buttons:
                view.add_item(button)

        start = self.page * SELECT_PAGE_SIZE

        return slice(start, start + SELECT_PAGE_SIZE)

    async def change_page(
        self,
        interaction: discord.Interaction,
        delta: int,
    ) -> None:
        view: Any = self

        page = min(
            max(self.page + delta, 0),
            self.page_count - 1,
        )

        if self.item_identifiers:
            self.page = page
            self.selected_identifier = self.item_identifiers[
                page * SELECT_PAGE_SIZE
            ]

        await view.refresh(interaction)
