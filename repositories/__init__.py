"""
Repository 层 - 数据访问对象
提供对数据库的统一访问接口
"""

from .base_repository import BaseRepository

# 好感度相关
from .affection_repository import (
    AffectionRepository,
    InteractionRepository,
    ConversationHistoryRepository,
    DiversityRepository
)

# 记忆相关
from .memory_repository import (
    MemoryRepository,
    MemoryEmbeddingRepository,
    MemorySummaryRepository
)

# 心理状态相关
from .psychological_repository import (
    PsychologicalStateRepository,
    PsychologicalComponentRepository,
    PsychologicalHistoryRepository
)

# 社交关系相关
from .social_repository import (
    SocialProfileRepository,
    SocialRelationComponentRepository,
    SocialRelationHistoryRepository
)

# 学习系统相关
from .learning_repository import (
    PersonaLearningReviewRepository,
    StyleLearningReviewRepository,
    StyleLearningPatternRepository,
    InteractionRecordRepository,
    LearningBatchRepository,
    LearningSessionRepository,
    LearningReinforcementFeedbackRepository,
    LearningOptimizationLogRepository
)

# 人格系统相关
from .persona_repository import (
    PersonaDiversityScoreRepository,
    PersonaAttributeWeightRepository,
    PersonaEvolutionSnapshotRepository
)

__all__ = [
    # 基础
    'BaseRepository',

    # 好感度系统 (4个)
    'AffectionRepository',
    'InteractionRepository',
    'ConversationHistoryRepository',
    'DiversityRepository',

    # 记忆系统 (3个)
    'MemoryRepository',
    'MemoryEmbeddingRepository',
    'MemorySummaryRepository',

    # 心理状态系统 (3个)
    'PsychologicalStateRepository',
    'PsychologicalComponentRepository',
    'PsychologicalHistoryRepository',

    # 社交关系系统 (3个)
    'SocialProfileRepository',
    'SocialRelationComponentRepository',
    'SocialRelationHistoryRepository',

    # 学习系统 (8个)
    'PersonaLearningReviewRepository',
    'StyleLearningReviewRepository',
    'StyleLearningPatternRepository',
    'InteractionRecordRepository',
    'LearningBatchRepository',
    'LearningSessionRepository',
    'LearningReinforcementFeedbackRepository',
    'LearningOptimizationLogRepository',

    # 人格系统 (3个)
    'PersonaDiversityScoreRepository',
    'PersonaAttributeWeightRepository',
    'PersonaEvolutionSnapshotRepository',
]
