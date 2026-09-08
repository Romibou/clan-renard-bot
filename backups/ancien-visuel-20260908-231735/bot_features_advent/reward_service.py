from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Sequence

from bot.features.advent.constants import (
    REWARD_MESSAGE,
    REWARD_POINTS,
    REWARD_RANDOM,
    REWARD_ROLE,
    VALID_REWARD_TYPES,
)
from bot.features.advent.exceptions import (
    RewardConfigurationError,
)
from bot.features.advent.models import AdventReward


@dataclass(frozen=True, slots=True)
class ResolvedReward:
    reward_type: str
    snapshot: dict[str, Any]
    message: str
    points: int
    role_id: int | None
    external_status: str


class RewardService:
    def resolve(
        self,
        reward: AdventReward | None,
    ) -> ResolvedReward:
        if reward is None:
            return ResolvedReward(
                reward_type=REWARD_MESSAGE,
                snapshot={
                    "message": (
                        "Tu as ouvert la case, mais aucune récompense "
                        "particulière n'avait été configurée."
                    )
                },
                message=(
                    "🎁 Tu as ouvert ta case du jour ! "
                    "Aucune récompense particulière n'était configurée."
                ),
                points=0,
                role_id=None,
                external_status="not_required",
            )

        return self._resolve_definition(
            reward.reward_type,
            reward.reward_data,
        )

    def _resolve_definition(
        self,
        reward_type: str,
        data: dict[str, Any],
    ) -> ResolvedReward:
        if reward_type not in VALID_REWARD_TYPES:
            raise RewardConfigurationError(
                f"Type de récompense inconnu : {reward_type}"
            )

        if reward_type == REWARD_RANDOM:
            return self._resolve_random(data)

        if reward_type == REWARD_MESSAGE:
            message = str(
                data.get(
                    "message",
                    "Tu as trouvé une surprise de Clan Renard !",
                )
            ).strip()

            if not message:
                raise RewardConfigurationError(
                    "Le message de récompense est vide."
                )

            return ResolvedReward(
                reward_type=REWARD_MESSAGE,
                snapshot={"message": message},
                message=f"🎁 {message}",
                points=0,
                role_id=None,
                external_status="not_required",
            )

        if reward_type == REWARD_POINTS:
            try:
                points = int(data.get("points", 0))
            except (TypeError, ValueError) as error:
                raise RewardConfigurationError(
                    "Le nombre de points est invalide."
                ) from error

            if points < 0:
                raise RewardConfigurationError(
                    "Les points ne peuvent pas être négatifs."
                )

            message = str(
                data.get(
                    "message",
                    f"Tu remportes **{points} points** !",
                )
            ).strip()

            return ResolvedReward(
                reward_type=REWARD_POINTS,
                snapshot={
                    "points": points,
                    "message": message,
                },
                message=f"✨ {message}",
                points=points,
                role_id=None,
                external_status="not_required",
            )

        if reward_type == REWARD_ROLE:
            try:
                role_id = int(data["role_id"])
            except (KeyError, TypeError, ValueError) as error:
                raise RewardConfigurationError(
                    "L'identifiant du rôle est absent ou invalide."
                ) from error

            message = str(
                data.get(
                    "message",
                    "Tu remportes un rôle spécial !",
                )
            ).strip()

            return ResolvedReward(
                reward_type=REWARD_ROLE,
                snapshot={
                    "role_id": role_id,
                    "message": message,
                },
                message=f"🦊 {message}",
                points=0,
                role_id=role_id,
                external_status="pending",
            )

        raise RewardConfigurationError(
            f"Type non pris en charge : {reward_type}"
        )

    def _resolve_random(
        self,
        data: dict[str, Any],
    ) -> ResolvedReward:
        choices = data.get("choices")

        if not isinstance(choices, Sequence) or isinstance(
            choices,
            (str, bytes),
        ):
            raise RewardConfigurationError(
                "Une récompense aléatoire doit contenir une liste "
                "nommée « choices »."
            )

        valid_choices: list[dict[str, Any]] = []
        weights: list[float] = []

        for choice in choices:
            if not isinstance(choice, dict):
                continue

            choice_type = str(choice.get("type", "")).strip()
            choice_data = choice.get("data", {})
            raw_weight = choice.get("weight", 1)

            if choice_type == REWARD_RANDOM:
                continue

            if choice_type not in VALID_REWARD_TYPES:
                continue

            if not isinstance(choice_data, dict):
                continue

            try:
                weight = float(raw_weight)
            except (TypeError, ValueError):
                continue

            if weight <= 0:
                continue

            valid_choices.append(
                {
                    "type": choice_type,
                    "data": choice_data,
                }
            )
            weights.append(weight)

        if not valid_choices:
            raise RewardConfigurationError(
                "La récompense aléatoire ne contient aucun choix valide."
            )

        selected = random.choices(
            valid_choices,
            weights=weights,
            k=1,
        )[0]

        resolved = self._resolve_definition(
            selected["type"],
            selected["data"],
        )

        snapshot = dict(resolved.snapshot)
        snapshot["selected_from_random"] = True

        return ResolvedReward(
            reward_type=resolved.reward_type,
            snapshot=snapshot,
            message=resolved.message,
            points=resolved.points,
            role_id=resolved.role_id,
            external_status=resolved.external_status,
        )

    @staticmethod
    def describe(
        reward_type: str,
        reward_data: dict[str, Any],
    ) -> str:
        if reward_type == REWARD_MESSAGE:
            return str(
                reward_data.get("message", "Message surprise")
            )

        if reward_type == REWARD_POINTS:
            return f"{int(reward_data.get('points', 0))} points"

        if reward_type == REWARD_ROLE:
            role_id = reward_data.get("role_id", "?")
            return f"Rôle Discord <@&{role_id}>"

        if reward_type == REWARD_RANDOM:
            choices = reward_data.get("choices", [])
            count = len(choices) if isinstance(choices, list) else 0
            return f"Récompense aléatoire ({count} possibilité(s))"

        return "Récompense inconnue"
