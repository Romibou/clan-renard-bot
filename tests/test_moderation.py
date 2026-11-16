from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import discord
import pytest

from bot.features.moderation import automod as automod_module
from bot.features.moderation.automod import AutomodCog, clean_words, desired_rules
from bot.features.moderation.cog import ModerationCog
from bot.features.moderation.core import (
    BAN,
    FINE,
    KICK,
    MUTE,
    WARN,
    case_embed,
    dm_embed,
    escalation_to_text,
    format_duration,
    hierarchy_error,
    next_step,
    parse_escalation,
    parse_sanction_duration,
    step_for,
    steps_from_json,
    steps_to_json,
)
from bot.features.moderation.panel import panel_embed

UTC = timezone.utc


# ---------------------------------------------------------------
# Durées et échelle
# ---------------------------------------------------------------


def test_format_duration() -> None:
    assert format_duration(3600) == "1 h"
    assert format_duration(90_061) == "1 j 1 h"
    assert format_duration(None) == "définitive"


def test_parse_sanction_duration() -> None:
    assert parse_sanction_duration("2h", maximum=timedelta(days=28)) == timedelta(hours=2)
    assert parse_sanction_duration("", maximum=timedelta(days=28)) is None

    with pytest.raises(ValueError, match="trop longue"):
        parse_sanction_duration("30j", maximum=timedelta(days=28))

    with pytest.raises(ValueError, match="incomprise"):
        parse_sanction_duration("demain", maximum=timedelta(days=28))


def test_escalation_parsing_round_trip() -> None:
    steps = parse_escalation("3 = mute 1h\n5 avertissements -> kick\n7 = ban 7j\n\n9 = ban")

    assert [(step.warns, step.action) for step in steps] == [
        (3, MUTE),
        (5, KICK),
        (7, BAN),
        (9, BAN),
    ]
    assert steps[0].duration == timedelta(hours=1)
    assert steps[3].duration is None
    assert steps[3].describe() == "bannissement définitif"
    assert parse_escalation(escalation_to_text(steps)) == steps
    assert steps_from_json(steps_to_json(steps)) == steps


@pytest.mark.parametrize("text", ["3 = mute", "trois = kick", "3 = timeout 1h", "0 = kick"])
def test_escalation_rejects_invalid_lines(text: str) -> None:
    with pytest.raises(ValueError):
        parse_escalation(text)


def test_step_lookup() -> None:
    steps = parse_escalation("3 = mute 1h\n5 = kick")

    assert step_for(steps, 3).action == MUTE
    assert step_for(steps, 4) is None
    assert next_step(steps, 3).warns == 5
    assert next_step(steps, 5) is None


# ---------------------------------------------------------------
# Hiérarchie
# ---------------------------------------------------------------


class Role:
    def __init__(self, position: int) -> None:
        self.position = position

    def __ge__(self, other: Role) -> bool:
        return self.position >= other.position


def make_guild(bot_position: int = 50) -> SimpleNamespace:
    guild = SimpleNamespace(owner_id=1)
    guild.me = SimpleNamespace(id=999, top_role=Role(bot_position), guild=guild)
    return guild


def member(guild: SimpleNamespace, member_id: int, position: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=member_id,
        top_role=Role(position),
        guild=guild,
        mention=f"<@{member_id}>",
    )


def test_hierarchy_rules() -> None:
    guild = make_guild(bot_position=50)
    moderator = member(guild, 10, 40)

    assert hierarchy_error(moderator, member(guild, 20, 10), needs_bot_power=True) is None
    assert "toi-même" in hierarchy_error(moderator, moderator, needs_bot_power=False)
    assert "propriétaire" in hierarchy_error(moderator, member(guild, 1, 5), needs_bot_power=False)
    assert "supérieur au tien" in hierarchy_error(moderator, member(guild, 30, 40), needs_bot_power=False)
    assert "moi-même" in hierarchy_error(moderator, guild.me, needs_bot_power=False)

    owner = member(guild, 1, 60)
    above_bot = member(guild, 30, 55)
    assert hierarchy_error(owner, above_bot, needs_bot_power=False) is None
    assert "au mien" in hierarchy_error(owner, above_bot, needs_bot_power=True)


# ---------------------------------------------------------------
# Messages
# ---------------------------------------------------------------


def make_case(**values: Any) -> dict[str, Any]:
    case = {
        "id": 12,
        "guild_id": 1,
        "user_id": 20,
        "moderator_id": 10,
        "action": WARN,
        "reason": "Spam",
        "duration_seconds": None,
        "expires_at": None,
        "amount": None,
        "active": True,
        "revoked_at": None,
        "appeal_status": None,
        "created_at": datetime(2026, 11, 16, tzinfo=UTC),
    }
    case.update(values)
    return case


def test_case_and_dm_embeds() -> None:
    embed = case_embed(make_case(action=MUTE, duration_seconds=3600))
    fields = {field.name: field.value for field in embed.fields}

    assert "n°12" in embed.title
    assert fields["Durée"] == "1 h"

    automatic = case_embed(make_case(moderator_id=None))
    assert "automatique" in automatic.fields[1].value

    dm = dm_embed(make_case(action=FINE, amount=1500), "Clan Renard", appeal_possible=True)
    assert "amende" in dm.description
    assert "1 500 pièces" in dm.description
    assert "contester" in dm.description

    no_appeal = dm_embed(make_case(), "Clan Renard", appeal_possible=False)
    assert "contester" not in no_appeal.description


# ---------------------------------------------------------------
# Logique des sanctions (avec une fausse base)
# ---------------------------------------------------------------


class FakeRepository:
    def __init__(self, escalation: str = "2 = mute 1h") -> None:
        self.cases: dict[int, dict[str, Any]] = {}
        self.settings = {
            "log_channel_id": None,
            "appeal_channel_id": 77,
            "warn_expiry_days": 30,
            "escalation": steps_to_json(parse_escalation(escalation)),
            "automod": {},
            "automod_rule_ids": {},
        }

    async def get_settings(self, guild_id: int) -> dict[str, Any]:
        return self.settings

    async def create_case(self, **values: Any) -> dict[str, Any]:
        case_id = len(self.cases) + 1
        duration = values.pop("duration", None)
        case = make_case(
            id=case_id,
            moderator_id=values.pop("moderator_id"),
            duration_seconds=int(duration.total_seconds()) if duration else None,
            expires_at=datetime.now(UTC) + duration if duration else None,
            **{key: value for key, value in values.items() if key != "guild_id"},
        )
        self.cases[case_id] = case
        return dict(case)

    async def delete_case(self, case_id: int) -> None:
        self.cases.pop(case_id)

    async def set_amount(self, case_id: int, amount: int) -> None:
        self.cases[case_id]["amount"] = amount

    async def active_warn_count(self, guild_id: int, user_id: int, days: int) -> int:
        return sum(
            1
            for case in self.cases.values()
            if case["user_id"] == user_id and case["action"] == WARN and case["revoked_at"] is None
        )

    async def get_case(self, case_id: int) -> dict[str, Any] | None:
        return dict(self.cases[case_id]) if case_id in self.cases else None

    async def revoke_case(self, case_id: int, *, revoked_by: int | None, reason: str):
        case = self.cases[case_id]

        if case["revoked_at"] is not None:
            return None

        case["revoked_at"] = datetime.now(UTC)
        case["active"] = False
        return dict(case)


class FakeTarget:
    def __init__(self, user_id: int = 20, position: int = 5) -> None:
        self.id = user_id
        self.top_role = Role(position)
        self.timeouts: list[timedelta | None] = []
        self.dms: list[discord.Embed] = []
        self.kicked = False

    async def timeout(self, duration: timedelta | None, *, reason: str) -> None:
        self.timeouts.append(duration)

    async def kick(self, *, reason: str) -> None:
        self.kicked = True

    async def send(self, *, embed: discord.Embed, view: Any = None) -> None:
        self.dms.append(embed)

    def is_timed_out(self) -> bool:
        return bool(self.timeouts and self.timeouts[-1])


def make_cog(repository: FakeRepository) -> ModerationCog:
    cog = ModerationCog.__new__(ModerationCog)
    cog.bot = SimpleNamespace(database=None, get_user=lambda user_id: None)
    cog.repository = repository  # type: ignore[assignment]
    return cog


@pytest.fixture
def patched_member(monkeypatch: pytest.MonkeyPatch) -> None:
    # Le cog vérifie isinstance(..., discord.Member) : FakeTarget en tient lieu.
    monkeypatch.setattr(discord, "Member", FakeTarget)


async def test_warn_escalates_to_an_automatic_mute(patched_member: None) -> None:
    repository = FakeRepository("2 = mute 1h")
    cog = make_cog(repository)
    guild = SimpleNamespace(id=1, name="Clan Renard", me=SimpleNamespace(top_role=Role(50)))
    target = FakeTarget()

    first, info = await cog.sanction(guild=guild, target=target, moderator=None, action=WARN, reason="Spam")
    assert first["id"] == 1
    assert info["escalation"] is None
    assert info["dm_sent"] is True

    second, info = await cog.sanction(guild=guild, target=target, moderator=None, action=WARN, reason="Encore")
    escalation = info["escalation"]
    assert escalation["warns"] == 2
    assert escalation["case"]["action"] == MUTE
    assert target.timeouts == [timedelta(hours=1)]
    assert "automatique" in repository.cases[3]["reason"]


async def test_refused_action_leaves_no_case(patched_member: None) -> None:
    repository = FakeRepository()
    cog = make_cog(repository)
    guild = SimpleNamespace(id=1, name="Clan Renard", me=SimpleNamespace(top_role=Role(50)))

    class Untouchable(FakeTarget):
        async def timeout(self, duration, *, reason):
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "nope")

    case, info = await cog.sanction(
        guild=guild,
        target=Untouchable(),
        moderator=None,
        action=MUTE,
        reason="Test",
        duration=timedelta(minutes=5),
    )

    assert case is None
    assert "refusé" in info["error"]
    assert repository.cases == {}


async def test_kick_warns_the_member_before_kicking(patched_member: None) -> None:
    repository = FakeRepository()
    cog = make_cog(repository)
    guild = SimpleNamespace(id=1, name="Clan Renard", me=SimpleNamespace(top_role=Role(50)))
    events: list[str] = []

    class Tracked(FakeTarget):
        async def send(self, *, embed, view=None):
            events.append("dm")

        async def kick(self, *, reason):
            events.append("kick")

    case, _ = await cog.sanction(guild=guild, target=Tracked(), moderator=None, action=KICK, reason="Bye")

    assert events == ["dm", "kick"]
    assert case["active"] is False


async def test_pardon_removes_a_warn_from_the_count(patched_member: None) -> None:
    repository = FakeRepository("5 = kick")
    cog = make_cog(repository)
    guild = SimpleNamespace(id=1, name="Clan Renard", me=SimpleNamespace(top_role=Role(50)), get_member=lambda user_id: None)
    target = FakeTarget()

    case, _ = await cog.sanction(guild=guild, target=target, moderator=None, action=WARN, reason="Spam")
    assert await repository.active_warn_count(1, 20, 30) == 1

    revoked, problem = await cog.revoke(guild, case["id"], moderator=None, reason="Erreur")
    assert problem is None and revoked["revoked_at"] is not None
    assert await repository.active_warn_count(1, 20, 30) == 0

    again, problem = await cog.revoke(guild, case["id"], moderator=None, reason="Encore")
    assert again is None and "déjà annulée" in problem


async def test_appeal_rules(patched_member: None) -> None:
    repository = FakeRepository()
    cog = make_cog(repository)
    guild = SimpleNamespace(id=1, name="Clan Renard", me=SimpleNamespace(top_role=Role(50)))
    case, _ = await cog.sanction(guild=guild, target=FakeTarget(), moderator=None, action=WARN, reason="Spam")

    assert await cog.appeal_problem(case["id"], 20) is None
    assert "introuvable" in await cog.appeal_problem(case["id"], 21)

    repository.cases[case["id"]]["appeal_status"] = "pending"
    assert "déjà contesté" in await cog.appeal_problem(case["id"], 20)

    repository.settings["appeal_channel_id"] = None
    repository.cases[case["id"]]["appeal_status"] = None
    assert "plus acceptées" in await cog.appeal_problem(case["id"], 20)


# ---------------------------------------------------------------
# AutoMod et anti-spam
# ---------------------------------------------------------------


def test_clean_words() -> None:
    assert clean_words("Mot1, mot1,  mot2\nmot3,, ") == ["mot1", "mot2", "mot3"]
    assert clean_words("x" * 61) == []


def test_desired_rules() -> None:
    rules = desired_rules({"invites": True, "words": ["abc"], "mention_limit": 0})

    assert rules["invites"]["trigger"].regex_patterns
    assert rules["words"]["trigger"].keyword_filter == ["abc"]
    assert rules["mentions"] is None

    mentions = desired_rules({"mention_limit": 6})["mentions"]
    assert mentions["trigger"].mention_limit == 6


async def test_antispam_mutes_after_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    sanctions: list[dict[str, Any]] = []

    class FakeModeration:
        async def sanction(self, **values: Any):
            sanctions.append(values)
            return None, {}

    moderation = FakeModeration()
    bot = SimpleNamespace(get_cog=lambda name: moderation)
    cog = AutomodCog(bot)  # type: ignore[arg-type]

    async def settings(guild_id: int) -> dict[str, Any]:
        return {"automod": {"spam_messages": 3, "spam_seconds": 8, "spam_mute_minutes": 5}}

    cog.settings = settings  # type: ignore[method-assign]
    monkeypatch.setattr(automod_module.discord, "Member", SimpleNamespace)

    author = SimpleNamespace(
        id=20,
        bot=False,
        guild_permissions=discord.Permissions.none(),
        is_timed_out=lambda: False,
    )
    channel = SimpleNamespace(id=5)

    async def delete_messages(messages):
        channel.deleted = len(messages)

    channel.delete_messages = delete_messages
    message = SimpleNamespace(
        guild=SimpleNamespace(id=1),
        author=author,
        webhook_id=None,
        channel=channel,
    )

    for _ in range(2):
        await cog.on_message(message)

    assert sanctions == []

    await cog.on_message(message)

    assert sanctions[0]["action"] == MUTE
    assert sanctions[0]["duration"] == timedelta(minutes=5)
    assert channel.deleted == 3


def test_panel_embed_summarises_the_settings() -> None:
    embed = panel_embed(
        {
            "log_channel_id": 5,
            "appeal_channel_id": None,
            "warn_expiry_days": 30,
            "escalation": steps_to_json(parse_escalation("3 = mute 1h")),
            "automod": {
                "invites": True,
                "words": ["a", "b"],
                "mention_limit": 0,
                "spam_messages": 6,
                "spam_seconds": 8,
                "spam_mute_minutes": 10,
            },
        }
    )
    text = "\n".join(f"{field.name}\n{field.value}" for field in embed.fields)

    assert "<#5>" in text
    assert "Désactivées" in text
    assert "**3** → exclusion de 1 h" in text
    assert "2 mot(s)" in text
    assert "6 messages en 8 s" in text
