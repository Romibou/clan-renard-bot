from bot.features.advent.models import AdventReward
from bot.features.advent.reward_service import RewardService


def test_points_reward() -> None:
    service = RewardService()
    reward = AdventReward(
        id=1,
        campaign_id=1,
        day=1,
        reward_type="points",
        reward_data={
            "points": 150,
            "message": "Tu remportes 150 points !",
        },
    )

    resolved = service.resolve(reward)

    assert resolved.points == 150
    assert resolved.role_id is None
    assert resolved.reward_type == "points"


def test_default_reward() -> None:
    service = RewardService()
    resolved = service.resolve(None)

    assert resolved.points == 0
    assert resolved.reward_type == "message"
    assert resolved.external_status == "not_required"
