"""
SQLAlchemy ORM 模型导出
"""
from .base import Base
from .affection import (
    UserAffection,
    AffectionInteraction,
    UserConversationHistory,
    UserDiversity
)
from .memory import (
    Memory,
    MemoryEmbedding,
    MemorySummary
)
from .psychological import (
    CompositePsychologicalState,
    PsychologicalStateComponent,
    PsychologicalStateHistory,
    PersonaDiversityScore,
    PersonaAttributeWeight,
    PersonaEvolutionSnapshot
)
from .social_relation import (
    SocialRelation,
    UserSocialProfile,
    UserSocialRelationComponent,
    SocialRelationHistory
)
from .social_analysis import (
    SocialRelationAnalysisResult,
    SocialNetworkNode,
    SocialNetworkEdge
)
from .learning import (
    PersonaLearningReview,
    StyleLearningReview,
    StyleLearningPattern,
    InteractionRecord,
    LearningBatch,
    LearningSession,
    LearningReinforcementFeedback,
    LearningOptimizationLog
)
from .expression import (
    ExpressionPattern,
    ExpressionGenerationResult,
    AdaptiveResponseTemplate
)
from .performance import (
    LearningPerformanceHistory
)
from .message import (
    RawMessage,
    FilteredMessage,
    BotMessage,
    ConversationContext,
    ConversationTopicClustering,
    ConversationQualityMetrics,
    ContextSimilarityCache
)
from .jargon import (
    Jargon,
    JargonUsageFrequency
)
from .conversation_goal import (
    ConversationGoal
)
from .reinforcement import (
    ReinforcementLearningResult,
    PersonaFusionHistory,
    StrategyOptimizationResult
)
from .knowledge_graph import (
    KGEntity,
    KGRelation,
    KGParagraphHash
)
from .exemplar import (
    Exemplar
)

__all__ = [
    'Base',
    # 好感度系统
    'UserAffection',
    'AffectionInteraction',
    'UserConversationHistory',
    'UserDiversity',
    # 记忆系统
    'Memory',
    'MemoryEmbedding',
    'MemorySummary',
    # 心理状态系统
    'CompositePsychologicalState',
    'PsychologicalStateComponent',
    'PsychologicalStateHistory',
    'PersonaDiversityScore',
    'PersonaAttributeWeight',
    'PersonaEvolutionSnapshot',
    # 社交关系系统
    'SocialRelation',
    'UserSocialProfile',
    'UserSocialRelationComponent',
    'SocialRelationHistory',
    # 社交分析
    'SocialRelationAnalysisResult',
    'SocialNetworkNode',
    'SocialNetworkEdge',
    # 学习系统
    'PersonaLearningReview',
    'StyleLearningReview',
    'StyleLearningPattern',
    'InteractionRecord',
    'LearningBatch',
    'LearningSession',
    'LearningReinforcementFeedback',
    'LearningOptimizationLog',
    # 表达模式
    'ExpressionPattern',
    'ExpressionGenerationResult',
    'AdaptiveResponseTemplate',
    # 性能记录
    'LearningPerformanceHistory',
    # 消息系统
    'RawMessage',
    'FilteredMessage',
    'BotMessage',
    'ConversationContext',
    'ConversationTopicClustering',
    'ConversationQualityMetrics',
    'ContextSimilarityCache',
    # 黑话系统
    'Jargon',
    'JargonUsageFrequency',
    # 对话目标系统
    'ConversationGoal',
    # 强化学习系统
    'ReinforcementLearningResult',
    'PersonaFusionHistory',
    'StrategyOptimizationResult',
    # 知识图谱系统
    'KGEntity',
    'KGRelation',
    'KGParagraphHash',
    # Exemplar library
    'Exemplar',
]
