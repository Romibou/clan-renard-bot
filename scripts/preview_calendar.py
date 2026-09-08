from __future__ import annotations

import argparse
import asyncio
from datetime import date
from pathlib import Path

from bot.features.advent.image_generator import (
    AdventImageGenerator,
)
from bot.features.advent.models import (
    AdventCampaign,
    CalendarState,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_preview_state(
    year: int,
) -> CalendarState:
    campaign = AdventCampaign(
        id=1,
        guild_id=1,
        year=year,
        title="Calendrier de l'Avent",
        start_date=date(year, 12, 1),
        end_date=date(year, 12, 24),
        timezone="Europe/Paris",
        opening_hour=0,
        catchup_mode="disabled",
        channel_id=None,
        announcement_role_id=None,
        announcements_enabled=False,
        enabled=True,
        day_order=(
            7, 18, 2, 24, 11, 15,
            3, 20, 9, 14, 1, 22,
            16, 5, 21, 10, 13, 8,
            17, 4, 23, 6, 19, 12,
        ),
    )

    return CalendarState(
        campaign=campaign,
        today=date(year, 12, 8),
        current_day=8,
        opened_days=frozenset(
            {1, 2, 3, 5, 6}
        ),
        missed_days=frozenset(
            {4, 7}
        ),
        available_days=frozenset(
            {8}
        ),
        future_days=frozenset(
            range(9, 25)
        ),
        total_points=650,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Génère une prévisualisation locale du "
            "calendrier de Clan Renard."
        )
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2026,
    )
    parser.add_argument(
        "--name",
        default="Membre du Clan",
    )
    arguments = parser.parse_args()

    generator = AdventImageGenerator(
        PROJECT_ROOT
    )
    rendered = await generator.render(
        build_preview_state(arguments.year),
        arguments.name,
        preview=True,
    )

    output_directory = (
        PROJECT_ROOT / "generated"
    )
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_directory
        / "apercu-calendrier.png"
    )
    output_path.write_bytes(
        rendered.buffer.getvalue()
    )

    print(
        f"Aperçu créé : {output_path}"
    )


if __name__ == "__main__":
    asyncio.run(main())
