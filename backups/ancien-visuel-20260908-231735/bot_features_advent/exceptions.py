from __future__ import annotations


class AdventError(RuntimeError):
    """Erreur métier pouvant être affichée à un utilisateur."""


class CampaignNotConfigured(AdventError):
    pass


class CampaignDisabled(AdventError):
    pass


class CampaignNotStarted(AdventError):
    pass


class CampaignFinished(AdventError):
    pass


class DayAlreadyOpened(AdventError):
    pass


class DayNotAvailable(AdventError):
    pass


class RewardConfigurationError(AdventError):
    pass
