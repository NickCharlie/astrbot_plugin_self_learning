"""
消息相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, Index, BigInteger, LargeBinary, ForeignKey, DateTime
from sqlalchemy.sql import func
from .base import Base


class RawMessage(Base):
    """原始消息表"""
    __tablename__ = 'raw_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(String(255), nullable=False, index=True)
    sender_name = Column(String(255))
    message = Column(Text, nullable=False)
    group_id = Column(String(255), index=True)
    timestamp = Column(BigInteger, nullable=False)
    platform = Column(String(100))
    message_id = Column(String(255), nullable=True)  # 可能在旧表中不存在
    reply_to = Column(String(255), nullable=True)    # 可能在旧表中不存在
    created_at = Column(BigInteger, nullable=False)
    processed = Column(Boolean, default=False)

    __table_args__ = (
        Index('idx_raw_timestamp', 'timestamp'),
        Index('idx_raw_sender', 'sender_id'),
        Index('idx_raw_processed', 'processed'),
        Index('idx_raw_group', 'group_id'),
    )


class FilteredMessage(Base):
    """筛选后消息表"""
    __tablename__ = 'filtered_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_message_id = Column(Integer)
    message = Column(Text, nullable=False)
    sender_id = Column(String(255), nullable=False, index=True)
    group_id = Column(String(255), index=True)
    timestamp = Column(BigInteger, nullable=False)
    confidence = Column(Float)
    quality_scores = Column(Text)  # JSON 字符串，存储多个质量分数（与传统 database_manager 保持一致）
    filter_reason = Column(Text)
    created_at = Column(BigInteger, nullable=False)
    processed = Column(Boolean, default=False)

    __table_args__ = (
        Index('idx_filtered_timestamp', 'timestamp'),
        Index('idx_filtered_sender', 'sender_id'),
        Index('idx_filtered_processed', 'processed'),
        Index('idx_filtered_group', 'group_id'),
    )


class BotMessage(Base):
    """Bot消息表"""
    __tablename__ = 'bot_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    message = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_bot_timestamp', 'timestamp'),
        Index('idx_bot_group', 'group_id'),
    )


class ConversationContext(Base):
    """对话上下文表 - 记录对话的上下文信息和状态"""
    __tablename__ = 'conversation_context'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    context_window = Column(Text, nullable=False)  # JSON - 最近N条消息
    topic = Column(String(255), nullable=True)  # 当前话题
    sentiment = Column(String(100), nullable=True)  # 情感倾向
    context_embedding = Column(LargeBinary, nullable=True)  # BLOB - 向量嵌入
    last_updated = Column(Float, nullable=False)  # Unix timestamp
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_context_group', 'group_id'),
        Index('idx_context_user', 'user_id'),
        Index('idx_context_updated', 'last_updated'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'user_id': self.user_id,
            'context_window': self.context_window,
            'topic': self.topic,
            'sentiment': self.sentiment,
            'last_updated': self.last_updated,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ConversationTopicClustering(Base):
    """对话主题聚类表 - 记录话题聚类结果"""
    __tablename__ = 'conversation_topic_clustering'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    cluster_id = Column(String(255), nullable=False, index=True)
    topic_keywords = Column(Text, nullable=False)  # JSON - 主题关键词列表
    message_count = Column(Integer, default=0)
    representative_messages = Column(Text, nullable=True)  # JSON - 代表性消息
    cluster_center = Column(LargeBinary, nullable=True)  # BLOB - 聚类中心向量
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_topic_group', 'group_id'),
        Index('idx_topic_cluster', 'cluster_id'),
        Index('idx_topic_count', 'message_count'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'cluster_id': self.cluster_id,
            'topic_keywords': self.topic_keywords,
            'message_count': self.message_count,
            'representative_messages': self.representative_messages,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ConversationQualityMetrics(Base):
    """对话质量指标表 - 记录消息的质量评估"""
    __tablename__ = 'conversation_quality_metrics'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey('bot_messages.id'), nullable=False, index=True)
    coherence_score = Column(Float, nullable=True)  # 连贯性分数
    relevance_score = Column(Float, nullable=True)  # 相关性分数
    engagement_score = Column(Float, nullable=True)  # 互动度分数
    sentiment_alignment = Column(Float, nullable=True)  # 情感一致性分数
    calculated_at = Column(Float, nullable=False)  # Unix timestamp
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_quality_group', 'group_id'),
        Index('idx_quality_message', 'message_id'),
        Index('idx_quality_calculated', 'calculated_at'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'message_id': self.message_id,
            'coherence_score': self.coherence_score,
            'relevance_score': self.relevance_score,
            'engagement_score': self.engagement_score,
            'sentiment_alignment': self.sentiment_alignment,
            'calculated_at': self.calculated_at,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ContextSimilarityCache(Base):
    """上下文相似度缓存表 - 缓存上下文之间的相似度计算结果"""
    __tablename__ = 'context_similarity_cache'

    id = Column(Integer, primary_key=True, autoincrement=True)
    context_hash_1 = Column(String(255), nullable=False, index=True)
    context_hash_2 = Column(String(255), nullable=False, index=True)
    similarity_score = Column(Float, nullable=False)
    calculation_method = Column(String(100), nullable=True)  # 计算方法（cosine, euclidean, etc.）
    cached_at = Column(Float, nullable=False)  # Unix timestamp
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_similarity_hash1', 'context_hash_1'),
        Index('idx_similarity_hash2', 'context_hash_2'),
        Index('idx_similarity_hashes', 'context_hash_1', 'context_hash_2'),  # 复合索引
        Index('idx_similarity_cached', 'cached_at'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'context_hash_1': self.context_hash_1,
            'context_hash_2': self.context_hash_2,
            'similarity_score': self.similarity_score,
            'calculation_method': self.calculation_method,
            'cached_at': self.cached_at,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

