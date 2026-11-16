from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import discord

from bot.extensions.advent_shop import AdventShopView
from bot.features.advent import avatar_service
from bot.features.advent.commands import AdventCommands
from bot.features.advent.image_generator import AdventImageGenerator
from bot.features.advent.models import AdventCampaign, CalendarState
from bot.features.advent.transaction_repository import AdventTransactionRepository


def make_campaign() -> AdventCampaign:
    return AdventCampaign(
        id=1,
        guild_id=1,
        year=2026,
        title="Calendrier de l'Avent",
        start_date=date(2026, 12, 1),
        end_date=date(2026, 12, 24),
        timezone="Europe/Paris",
        opening_hour=0,
        catchup_mode="enabled",
        channel_id=None,
        announcement_role_id=None,
        announcements_enabled=False,
        enabled=True,
        day_order=tuple(range(1, 25)),
    )


def make_state(available_days: set[int]) -> CalendarState:
    return CalendarState(
        campaign=make_campaign(),
        today=date(2026, 12, 3),
        current_day=3,
        opened_days=frozenset(),
        missed_days=frozenset(),
        available_days=frozenset(available_days),
        future_days=frozenset(range(4, 25)),
        total_points=0,
    )


class RecordingResponse:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def defer(self, **kwargs: object) -> None:
        self.events.append("defer")

    async def send_message(self, *args: object, **kwargs: object) -> None:
        self.events.append("send_message")

    def is_done(self) -> bool:
        return "defer" in self.events


class RecordingFollowup:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.views: list[object] = []

    async def send(self, *args: object, **kwargs: object) -> None:
        self.events.append("followup")
        self.views.append(kwargs.get("view"))


def make_cog(events: list[str], available_days: set[int]) -> AdventCommands:
    async def get_campaign(guild_id: int) -> AdventCampaign:
        events.append("database")
        return make_campaign()

    async def get_state(**kwargs: object) -> CalendarState:
        events.append("database")
        return make_state(available_days)

    service = SimpleNamespace(
        get_campaign_for_display=get_campaign,
        get_calendar_state=get_state,
    )
    cog = AdventCommands(
        SimpleNamespace(),  # type: ignore[arg-type]
        service=service,  # type: ignore[arg-type]
        image_generator=SimpleNamespace(),  # type: ignore[arg-type]
    )

    async def fake_open_case(interaction: object, **kwargs: object) -> None:
        events.append("open_case")

    cog._open_case = fake_open_case  # type: ignore[method-assign]
    return cog


def make_interaction(events: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        guild=SimpleNamespace(id=1),
        user=SimpleNamespace(id=42),
        response=RecordingResponse(events),
        followup=RecordingFollowup(events),
    )


async def test_open_button_answers_discord_before_querying_the_database() -> None:
    events: list[str] = []
    cog = make_cog(events, {3})

    await cog.handle_open_button(make_interaction(events))  # type: ignore[arg-type]

    assert events[0] == "defer"
    assert events[-1] == "open_case"
    assert "send_message" not in events


async def test_catchup_menu_is_sent_as_a_followup_after_defer() -> None:
    events: list[str] = []
    cog = make_cog(events, {1, 2, 3})
    interaction = make_interaction(events)

    await cog.handle_open_button(interaction)  # type: ignore[arg-type]

    assert events == ["defer", "database", "database", "followup"]
    assert isinstance(interaction.followup.views[0], discord.ui.View)


async def test_avatar_download_failure_does_not_crash() -> None:
    class BrokenAsset:
        def replace(self, **kwargs: object) -> BrokenAsset:
            return self

        async def read(self) -> bytes:
            raise discord.DiscordException("CDN indisponible")

    user = SimpleNamespace(id=1, display_avatar=BrokenAsset())

    assert await avatar_service.read_avatar(user) is None  # type: ignore[arg-type]


async def test_calendar_filename_is_ascii_for_any_nickname() -> None:
    generator = AdventImageGenerator()

    for nickname in ("Léa 🦊", "🎄🎄", "Renard_42"):
        rendered = await generator.render(make_state({3}), nickname)
        assert rendered.filename.isascii()
        assert rendered.filename.endswith(".png")


async def test_advent_leaderboard_filters_departed_members() -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeDatabase:
        async def fetch(self, query: str, *args: object) -> list[object]:
            calls.append((query, args))
            return []

    repository = AdventTransactionRepository(FakeDatabase())  # type: ignore[arg-type]
    await repository.leaderboard(1, 10, [5, 6])

    query, args = calls[0]
    assert args == (1, 10, [5, 6])
    assert "user_id = ANY($3::BIGINT[])" in query


def test_bought_role_can_be_restored_from_the_advent_shop() -> None:
    view = AdventShopView(
        cog=SimpleNamespace(),  # type: ignore[arg-type]
        owner_id=1,
        guild_id=1,
        campaign_id=1,
    )
    items = [
        {
            "id": 1,
            "identifier": "role-noel",
            "display_name": "Rôle de Noël",
            "emoji": "🎁",
            "item_type": "role",
            "price": 500,
            "min_openings": 0,
        },
        {
            "id": 2,
            "identifier": "badge-noel",
            "display_name": "Badge de Noël",
            "emoji": "🎖️",
            "item_type": "profile_cosmetic",
            "price": 500,
            "min_openings": 0,
        },
    ]

    view.update_components(
        items=items,
        purchased_item_ids={1, 2},
        balance=0,
        openings=0,
    )
    assert not view.buy_button.disabled
    assert view.buy_button.label == "Restaurer le rôle"

    view.selected_identifier = "badge-noel"
    view.update_components(
        items=items,
        purchased_item_ids={1, 2},
        balance=0,
        openings=0,
    )
    assert view.buy_button.disabled
    assert view.buy_button.label == "Déjà acheté"


# ---------- Calendrier désactivé dans /avent-admin ----------


def make_disabled_cog() -> AdventCommands:
    from dataclasses import replace

    async def get_campaign(guild_id: int) -> AdventCampaign:
        return replace(make_campaign(), enabled=False)

    return AdventCommands(
        SimpleNamespace(),  # type: ignore[arg-type]
        service=SimpleNamespace(get_campaign_for_display=get_campaign),  # type: ignore[arg-type]
        image_generator=SimpleNamespace(),  # type: ignore[arg-type]
    )


def make_member(*, administrator: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        guild_permissions=discord.Permissions(administrator=administrator),
    )


async def test_disabled_calendar_is_closed_to_members() -> None:
    import pytest

    from bot.features.advent.exceptions import CampaignDisabled

    cog = make_disabled_cog()
    interaction = SimpleNamespace(
        guild=SimpleNamespace(id=1),
        user=make_member(administrator=False),
    )

    with pytest.raises(CampaignDisabled, match="fermé"):
        await cog._get_open_campaign(interaction)  # type: ignore[arg-type]


async def test_disabled_calendar_stays_visible_to_admins() -> None:
    cog = make_disabled_cog()
    interaction = SimpleNamespace(
        guild=SimpleNamespace(id=1),
        user=make_member(administrator=True),
    )

    campaign = await cog._get_open_campaign(interaction)  # type: ignore[arg-type]

    assert campaign.enabled is False
