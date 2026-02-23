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

# 消息与对话系统相关
from .message_repository import (
    ConversationContextRepository,
    ConversationTopicClusteringRepository,
    ConversationQualityMetricsRepository,
    ContextSimilarityCacheRepository
)

# 黑话与表达系统相关
from .jargon_repository import (
    JargonRepository
)
from .jargon_expression_repository import (
    JargonUsageFrequencyRepository,
    ExpressionGenerationResultRepository,
    AdaptiveResponseTemplateRepository
)

# --- Phase 1 新增 Repository ---

# 原始消息/筛选消息/Bot消息
from .raw_message_repository import RawMessageRepository
from .filtered_message_repository import FilteredMessageRepository
from .bot_message_repository import BotMessageRepository

# 用户画像/偏好
from .user_profile_repository import UserProfileRepository
from .user_preferences_repository import UserPreferencesRepository

# 情绪画像 / 风格画像 / Bot 情绪
from .emotion_profile_repository import EmotionProfileRepository
from .style_profile_repository import StyleProfileRepository
from .bot_mood_repository import BotMoodRepository

# 人格备份
from .persona_backup_repository import PersonaBackupRepository

# 知识图谱
from .knowledge_graph_repository import (
    KnowledgeEntityRepository,
    KnowledgeRelationRepository,
    KnowledgeParagraphHashRepository
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

    # 消息与对话系统 (4个)
    'ConversationContextRepository',
    'ConversationTopicClusteringRepository',
    'ConversationQualityMetricsRepository',
    'ContextSimilarityCacheRepository',

    # 黑话与表达系统 (4个)
    'JargonRepository',
    'JargonUsageFrequencyRepository',
    'ExpressionGenerationResultRepository',
    'AdaptiveResponseTemplateRepository',

    # --- Phase 1 新增 (12个) ---

    # 消息三层 (3个)
    'RawMessageRepository',
    'FilteredMessageRepository',
    'BotMessageRepository',

    # 用户画像/偏好 (2个)
    'UserProfileRepository',
    'UserPreferencesRepository',

    # 情绪/风格/情绪状态 (3个)
    'EmotionProfileRepository',
    'StyleProfileRepository',
    'BotMoodRepository',

    # 人格备份 (1个)
    'PersonaBackupRepository',

    # 知识图谱 (3个)
    'KnowledgeEntityRepository',
    'KnowledgeRelationRepository',
    'KnowledgeParagraphHashRepository',
]
