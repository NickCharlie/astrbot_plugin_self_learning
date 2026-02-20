"""Domain Facade modules for decoupled data access."""

from ._base import BaseFacade
from .affection_facade import AffectionFacade
from .admin_facade import AdminFacade
from .expression_facade import ExpressionFacade
from .jargon_facade import JargonFacade
from .learning_facade import LearningFacade
from .message_facade import MessageFacade
from .metrics_facade import MetricsFacade
from .persona_facade import PersonaFacade
from .psychological_facade import PsychologicalFacade
from .reinforcement_facade import ReinforcementFacade
from .social_facade import SocialFacade

__all__ = [
    "BaseFacade",
    "AffectionFacade",
    "AdminFacade",
    "ExpressionFacade",
    "JargonFacade",
    "LearningFacade",
    "MessageFacade",
    "MetricsFacade",
    "PersonaFacade",
    "PsychologicalFacade",
    "ReinforcementFacade",
    "SocialFacade",
]
