"""
对话目标系统相关的 ORM 模型
会话级动态目标管理
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, BigInteger, JSON
from .base import Base


class ConversationGoal(Base):
    """对话目标表 - 会话级目标跟踪"""
    __tablename__ = 'conversation_goals'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 会话标识 (group_id + user_id + date hash)
    session_id = Column(String(100), nullable=False, unique=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    group_id = Column(String(255), nullable=False, index=True)

    # 最终目标 (JSON格式)
    # {
    #   "type": "emotional_support",
    #   "name": "情感支持",
    #   "detected_at": "2026-01-17T10:00:00",
    #   "confidence": 0.85,
    #   "topic": "工作压力",
    #   "topic_status": "active"
    # }
    final_goal = Column(JSON, nullable=False)

    # 当前阶段 (JSON格式)
    # {
    #   "index": 1,
    #   "task": "深入倾听用户诉说",
    #   "strategy": "开放式提问",
    #   "adjusted_at": "2026-01-17T10:05:00",
    #   "adjustment_reason": "用户开始详细描述问题"
    # }
    current_stage = Column(JSON, nullable=False)

    # 阶段历史 (JSON数组)
    # [{"task": "初步共情", "completed_at": "...", "effectiveness": 0.8}]
    stage_history = Column(JSON, default=list)

    # 规划的阶段列表 (JSON数组)
    # ["深入倾听用户诉说", "识别核心压力源", "提供具体建议", "鼓励行动"]
    planned_stages = Column(JSON, nullable=False)

    # 对话历史 (JSON数组) - 最近20轮
    # [{"role": "user", "content": "...", "timestamp": "..."}]
    conversation_history = Column(JSON, default=list)

    # 目标切换记录 (JSON数组)
    # [{"from": "qa", "to": "emotional_support", "reason": "...", "timestamp": "..."}]
    goal_switches = Column(JSON, default=list)

    # 指标数据 (JSON格式)
    # {
    #   "rounds": 5,
    #   "completion_signals": 2,
    #   "user_engagement": 0.75,
    #   "goal_progress": 0.4
    # }
    metrics = Column(JSON, nullable=False)

    # 状态
    status = Column(String(20), nullable=False, default='active', index=True)  # active/completed/paused

    # 时间戳
    created_at = Column(BigInteger, nullable=False)
    last_updated = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_conv_goal_session', 'session_id'),
        Index('idx_conv_goal_user_group', 'user_id', 'group_id'),
        Index('idx_conv_goal_status', 'status'),
        Index('idx_conv_goal_created', 'created_at'),
    )

    def __repr__(self):
        goal_type = self.final_goal.get('type', 'unknown') if self.final_goal else 'unknown'
        return f"<ConversationGoal(session={self.session_id}, goal={goal_type}, status={self.status})>"