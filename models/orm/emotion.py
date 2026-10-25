"""
情绪与学习联动相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from .base import Base


class LearningGateDailyStat(Base):
    """情绪学习闸门每日统计表

    按天、按群聚合 EmotionLearningGate 的判定结果，用于情绪板块的
    走向分析与闸门遥测。因子均值由 factor_sum_json 除以样本数得出。
    """
    __tablename__ = 'learning_gate_daily_stats'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stat_date = Column(String(10), nullable=False)  # YYYY-MM-DD（插件本地日期）
    group_id = Column(String(255), nullable=False)
    accepted_count = Column(Integer, default=0, nullable=False)
    skipped_count = Column(Integer, default=0, nullable=False)
    total_score = Column(Float, default=0.0, nullable=False)  # 加权分总和
    total_count = Column(Integer, default=0, nullable=False)  # 判定样本数
    factor_sum_json = Column(Text)  # JSON：各因子分值总和 {"affection": 0, ...}
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('stat_date', 'group_id', name='uq_gate_stat_date_group'),
        Index('idx_gate_stat_date', 'stat_date'),
        Index('idx_gate_stat_group', 'group_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'stat_date': self.stat_date,
            'group_id': self.group_id,
            'accepted_count': self.accepted_count,
            'skipped_count': self.skipped_count,
            'total_score': self.total_score,
            'total_count': self.total_count,
            'factor_sum_json': self.factor_sum_json,
        }
