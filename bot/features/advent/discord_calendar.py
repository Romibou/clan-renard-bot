from __future__ import annotations

import discord

from bot.features.advent.avatar_service import read_avatar
from bot.features.advent.image_generator import (
    AdventImageGenerator,
)
from bot.features.advent.models import CalendarState
from bot.features.advent.presentation import calendar_embed
from bot.features.advent.views import AdventView


async def build_calendar_response(
    *,
    state: CalendarState,
    member: discord.Member | discord.User,
    image_generator: AdventImageGenerator,
    preview: bool = False,
) -> tuple[discord.Embed, discord.File, AdventView]:
    avatar_bytes = await read_avatar(member)

    rendered = await image_generator.render(
        state,
        member.display_name,
        avatar_bytes=avatar_bytes,
        preview=preview,
    )

    file = discord.File(
        rendered.buffer,
        filename=rendered.filename,
    )
    embed = calendar_embed(
        state,
        member,
        filename=rendered.filename,
    )

    return embed, file, AdventView()
