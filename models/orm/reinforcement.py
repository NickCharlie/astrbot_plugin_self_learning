"""强化学习相关的ORM模型"""
from sqlalchemy import Column, Integer, String, Float, Text, BigInteger, DateTime
from sqlalchemy.sql import func
from .base import Base


class ReinforcementLearningResult(Base):
    """强化学习结果表"""
    __tablename__ = 'reinforcement_learning_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(Float, nullable=False)
    replay_analysis = Column(Text, nullable=True)
    optimization_strategy = Column(Text, nullable=True)
    reinforcement_feedback = Column(Text, nullable=True)
    next_action = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'timestamp': self.timestamp,
            'replay_analysis': self.replay_analysis,
            'optimization_strategy': self.optimization_strategy,
            'reinforcement_feedback': self.reinforcement_feedback,
            'next_action': self.next_action,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PersonaFusionHistory(Base):
    """人格融合历史表"""
    __tablename__ = 'persona_fusion_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(Float, nullable=False)
    base_persona_hash = Column(BigInteger, nullable=True)
    incremental_hash = Column(BigInteger, nullable=True)
    fusion_result = Column(Text, nullable=True)
    compatibility_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=func.now())

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'timestamp': self.timestamp,
            'base_persona_hash': self.base_persona_hash,
            'incremental_hash': self.incremental_hash,
            'fusion_result': self.fusion_result,
            'compatibility_score': self.compatibility_score,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class StrategyOptimizationResult(Base):
    """策略优化结果表"""
    __tablename__ = 'strategy_optimization_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(Float, nullable=False)
    strategy_type = Column(String(100), nullable=True)
    optimization_details = Column(Text, nullable=True)
    performance_metrics = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'group_id': self.group_id,
            'timestamp': self.timestamp,
            'strategy_type': self.strategy_type,
            'optimization_details': self.optimization_details,
            'performance_metrics': self.performance_metrics,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
