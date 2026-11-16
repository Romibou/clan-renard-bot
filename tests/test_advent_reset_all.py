from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import discord

from bot.features.advent.admin_panel import (
    AdminActionSelect,
    ResetAllConfirmModal,
    ResetAllWarningView,
    normalize_confirmation,
    start_reset_all,
)
from bot.features.advent.transaction_repository import AdventTransactionRepository


class Recorder:
    """Réponse Discord factice qui note ce qui est envoyé."""

    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.modals: list[object] = []
        self.done = False

    async def send_message(self, *args: object, **kwargs: object) -> None:
        self.done = True
        self.messages.append(kwargs)

    async def send_modal(self, modal: object) -> None:
        self.done = True
        self.modals.append(modal)

    async def edit_message(self, **kwargs: object) -> None:
        self.done = True
        self.messages.append(kwargs)

    async def defer(self, **kwargs: object) -> None:
        self.done = True

    def is_done(self) -> bool:
        return self.done


class FakeTransactions:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts
        self.reset_calls: list[int] = []

    async def count_campaign_data(self, campaign_id: int) -> dict[str, int]:
        return self.counts

    async def reset_all(self, campaign_id: int) -> dict[str, int]:
        self.reset_calls.append(campaign_id)
        return {"openings": 12, "purchases": 3}


def make_interaction(
    transactions: FakeTransactions,
    *,
    user_id: int = 1,
) -> SimpleNamespace:
    async def get_campaign(guild_id: int, year: int | None) -> SimpleNamespace:
        return SimpleNamespace(id=5, year=2026)

    async def audit(*args: object, **kwargs: object) -> None:
        return None

    cog = SimpleNamespace(
        transactions=transactions,
        _campaign=get_campaign,
        _audit=audit,
    )
    followups: list[dict[str, object]] = []

    async def followup_send(*args: object, **kwargs: object) -> None:
        followups.append(kwargs)

    return SimpleNamespace(
        guild_id=1,
        user=SimpleNamespace(id=user_id),
        client=SimpleNamespace(get_cog=lambda name: cog),
        response=Recorder(),
        followup=SimpleNamespace(send=followup_send),
        followups=followups,
    )


def embed_text(message: dict[str, object]) -> str:
    embed = message["embed"]
    assert isinstance(embed, discord.Embed)
    return f"{embed.title}\n{embed.description}"


def test_confirmation_word_accepts_accents_and_case() -> None:
    for text in ("RÉINITIALISER", "réinitialiser", "  Reinitialiser "):
        assert normalize_confirmation(text) == "REINITIALISER"

    assert normalize_confirmation("REINITIALISE") != "REINITIALISER"


def test_reset_all_is_in_the_admin_menu() -> None:
    values = [option.value for option in AdminActionSelect().options]

    assert "reset_user" in values
    assert "reset_all" in values
    assert len(values) <= 25


async def test_start_shows_a_warning_with_counts_and_deletes_nothing() -> None:
    transactions = FakeTransactions({"members": 8, "openings": 40, "purchases": 2})
    interaction = make_interaction(transactions)

    await start_reset_all(interaction)  # type: ignore[arg-type]

    message = interaction.response.messages[0]
    text = embed_text(message)
    assert "8 membre(s)" in text
    assert "40" in text
    assert "RÉINITIALISER" in text
    assert isinstance(message["view"], ResetAllWarningView)
    assert transactions.reset_calls == []


async def test_start_with_no_data_says_nothing_to_reset() -> None:
    transactions = FakeTransactions({"members": 0, "openings": 0, "purchases": 0})
    interaction = make_interaction(transactions)

    await start_reset_all(interaction)  # type: ignore[arg-type]

    assert "Rien à réinitialiser" in embed_text(interaction.response.messages[0])
    assert "view" not in interaction.response.messages[0]


async def test_warning_buttons_only_work_for_the_admin_who_started() -> None:
    view = ResetAllWarningView(owner_id=1, campaign_id=5, year=2026)
    intruder = make_interaction(FakeTransactions({}), user_id=2)

    assert await view.interaction_check(intruder) is False  # type: ignore[arg-type]


async def test_cancel_deletes_nothing() -> None:
    transactions = FakeTransactions({})
    view = ResetAllWarningView(owner_id=1, campaign_id=5, year=2026)
    interaction = make_interaction(transactions)

    await view.cancel.callback(interaction)  # type: ignore[arg-type]

    assert "annulée" in embed_text(interaction.response.messages[0])
    assert transactions.reset_calls == []


async def test_continue_only_opens_the_confirmation_form() -> None:
    transactions = FakeTransactions({})
    view = ResetAllWarningView(owner_id=1, campaign_id=5, year=2026)
    interaction = make_interaction(transactions)

    await view.proceed.callback(interaction)  # type: ignore[arg-type]

    assert isinstance(interaction.response.modals[0], ResetAllConfirmModal)
    assert transactions.reset_calls == []


async def test_wrong_word_deletes_nothing() -> None:
    transactions = FakeTransactions({})
    modal = ResetAllConfirmModal(campaign_id=5, year=2026)
    modal.confirmation._value = "oui"  # type: ignore[attr-defined]
    interaction = make_interaction(transactions)

    await modal.on_submit(interaction)  # type: ignore[arg-type]

    assert "Aucune donnée" in embed_text(interaction.response.messages[0])
    assert transactions.reset_calls == []


async def test_right_word_resets_everyone() -> None:
    transactions = FakeTransactions({})
    modal = ResetAllConfirmModal(campaign_id=5, year=2026)
    modal.confirmation._value = "Réinitialiser"  # type: ignore[attr-defined]
    interaction = make_interaction(transactions)

    await modal.on_submit(interaction)  # type: ignore[arg-type]

    assert transactions.reset_calls == [5]
    assert "12" in embed_text(interaction.followups[0])


async def test_repository_reset_all_targets_only_the_campaign() -> None:
    executed: list[tuple[str, tuple[object, ...]]] = []

    class FakeConnection:
        async def execute(self, query: str, *args: object) -> str:
            executed.append((" ".join(query.split()), args))
            return "DELETE 4"

        async def fetchval(self, query: str, *args: object) -> bool:
            return True

    class FakeDatabase:
        @asynccontextmanager
        async def transaction(self):
            yield FakeConnection()

    repository = AdventTransactionRepository(FakeDatabase())  # type: ignore[arg-type]

    deleted = await repository.reset_all(5)

    assert deleted == {"openings": 4, "purchases": 4}
    assert executed[0] == ("DELETE FROM advent_openings WHERE campaign_id = $1", (5,))
    assert executed[1] == (
        "DELETE FROM advent_shop_purchases_v2 WHERE campaign_id = $1",
        (5,),
    )

