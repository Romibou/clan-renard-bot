from __future__ import annotations

from types import SimpleNamespace

from bot.extensions import ping


def test_helpers() -> None:
    assert ping.rate(50) == "🟢" and ping.rate(200) == "🟡" and ping.rate(900) == "🔴"
    assert ping.format_uptime(125) == "2 min"
    assert ping.format_uptime(3 * 3600 + 120) == "3 h 2 min"
    assert ping.format_uptime(2 * 86400 + 5 * 3600) == "2 j 5 h"


async def test_ping_replies_privately() -> None:
    async def fetchval(query):
        return 1

    bot = SimpleNamespace(latency=0.042, database=SimpleNamespace(require_pool=lambda: SimpleNamespace(fetchval=fetchval)))
    cog = ping.PingCog(bot)
    sent: list = []
    edits: list = []

    async def send_message(content, **kwargs):
        sent.append(kwargs)

    async def edit_original_response(**kwargs):
        edits.append(kwargs)

    interaction = SimpleNamespace(response=SimpleNamespace(send_message=send_message),
                                  edit_original_response=edit_original_response)
    await ping.PingCog.ping.callback(cog, interaction)

    assert sent[0]["ephemeral"]
    text = edits[0]["embed"].description
    assert "42 ms" in text and "Base de données" in text and "En ligne depuis" in text


async def test_database_down() -> None:
    cog = ping.PingCog(SimpleNamespace(latency=0.1, database=None))
    assert await cog.database_latency() is None
