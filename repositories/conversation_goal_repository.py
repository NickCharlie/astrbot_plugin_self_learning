"""
对话目标仓储 - 数据访问层
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.orm.conversation_goal import ConversationGoal
from astrbot.api import logger


class ConversationGoalRepository:
    """对话目标仓储"""

    def __init__(self, session: AsyncSession):
        """
        初始化仓储

        Args:
            session: SQLAlchemy异步会话
        """
        self.session = session

    async def get_by_session_id(self, session_id: str) -> Optional[ConversationGoal]:
        """
        根据会话ID获取对话目标

        Args:
            session_id: 会话ID

        Returns:
            ConversationGoal实例或None
        """
        stmt = select(ConversationGoal).where(ConversationGoal.session_id == session_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_goal_by_user(
        self,
        user_id: str,
        group_id: str
    ) -> Optional[ConversationGoal]:
        """
        获取用户的活跃对话目标

        Args:
            user_id: 用户ID
            group_id: 群组ID

        Returns:
            ConversationGoal实例或None
        """
        # 查询24小时内的活跃会话
        cutoff_time = int((datetime.now() - timedelta(hours=24)).timestamp() * 1000)

        stmt = select(ConversationGoal).where(
            and_(
                ConversationGoal.user_id == user_id,
                ConversationGoal.group_id == group_id,
                ConversationGoal.status == 'active',
                ConversationGoal.created_at >= cutoff_time
            )
        ).order_by(ConversationGoal.created_at.desc())

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        session_id: str,
        user_id: str,
        group_id: str,
        final_goal: dict,
        current_stage: dict,
        planned_stages: list,
        conversation_history: list = None,
        metrics: dict = None
    ) -> ConversationGoal:
        """
        创建新的对话目标

        Args:
            session_id: 会话ID
            user_id: 用户ID
            group_id: 群组ID
            final_goal: 最终目标数据
            current_stage: 当前阶段数据
            planned_stages: 规划的阶段列表
            conversation_history: 对话历史
            metrics: 指标数据

        Returns:
            创建的ConversationGoal实例
        """
        now = int(datetime.now().timestamp() * 1000)

        goal = ConversationGoal(
            session_id=session_id,
            user_id=user_id,
            group_id=group_id,
            final_goal=final_goal,
            current_stage=current_stage,
            planned_stages=planned_stages,
            conversation_history=conversation_history or [],
            stage_history=[],
            goal_switches=[],
            metrics=metrics or {
                "rounds": 0,
                "completion_signals": 0,
                "user_engagement": 0.5,
                "goal_progress": 0.0
            },
            status='active',
            created_at=now,
            last_updated=now
        )

        self.session.add(goal)
        await self.session.flush()

        logger.info(f"创建对话目标: session={session_id}, user={user_id}, group={group_id}")
        return goal

    async def get_or_create(
        self,
        session_id: str,
        user_id: str,
        group_id: str,
        final_goal: dict,
        current_stage: dict,
        planned_stages: list,
        conversation_history: list = None,
        metrics: dict = None
    ) -> tuple[ConversationGoal, bool]:
        """
        获取或创建对话目标 (并发安全)

        使用策略:
        1. 先尝试查询已存在的记录
        2. 如果不存在,尝试创建
        3. 如果创建时遇到唯一键冲突(并发竞争),再次查询并返回

        Args:
            session_id: 会话ID
            user_id: 用户ID
            group_id: 群组ID
            final_goal: 最终目标数据
            current_stage: 当前阶段数据
            planned_stages: 规划的阶段列表
            conversation_history: 对话历史
            metrics: 指标数据

        Returns:
            tuple[ConversationGoal, bool]: (对话目标实例, 是否新创建)
        """
        from sqlalchemy.exc import IntegrityError

        # 1. 先尝试查询已存在的记录
        existing_goal = await self.get_by_session_id(session_id)
        if existing_goal:
            logger.debug(f"找到已存在的会话: session={session_id}")
            return existing_goal, False

        # 2. 尝试创建新记录
        try:
            new_goal = await self.create(
                session_id=session_id,
                user_id=user_id,
                group_id=group_id,
                final_goal=final_goal,
                current_stage=current_stage,
                planned_stages=planned_stages,
                conversation_history=conversation_history,
                metrics=metrics
            )
            logger.info(f"成功创建新会话: session={session_id}")
            return new_goal, True

        except IntegrityError as e:
            # 3. 遇到唯一键冲突 (并发竞争)
            logger.warning(f"检测到并发创建冲突: session={session_id}, 错误={str(e)[:100]}")

            # 3.1 回滚当前事务 (关键步骤!)
            await self.session.rollback()
            logger.debug(f"已回滚事务: session={session_id}")

            # 3.2 重新查询已存在的记录
            existing_goal = await self.get_by_session_id(session_id)
            if existing_goal:
                logger.info(f"并发冲突解决: 返回已存在的会话 session={session_id}")
                return existing_goal, False
            else:
                # 极端情况: 记录被删除或其他异常
                logger.error(f"并发冲突后未找到记录: session={session_id}")
                raise RuntimeError(f"并发冲突后记录丢失: session_id={session_id}")

        except Exception as e:
            # 其他异常,直接向上抛出
            logger.error(f"创建会话失败: session={session_id}, 错误={e}")
            raise

    async def update(self, goal: ConversationGoal) -> ConversationGoal:
        """
        更新对话目标

        Args:
            goal: ConversationGoal实例

        Returns:
            更新后的实例
        """
        goal.last_updated = int(datetime.now().timestamp() * 1000)
        await self.session.flush()
        return goal

    async def delete_by_session_id(self, session_id: str) -> bool:
        """
        删除对话目标

        Args:
            session_id: 会话ID

        Returns:
            是否成功删除
        """
        stmt = delete(ConversationGoal).where(ConversationGoal.session_id == session_id)
        result = await self.session.execute(stmt)
        await self.session.flush()

        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"删除对话目标: session={session_id}")

        return deleted

    async def get_all_active_goals(self) -> List[ConversationGoal]:
        """
        获取所有活跃的对话目标

        Returns:
            ConversationGoal列表
        """
        stmt = select(ConversationGoal).where(ConversationGoal.status == 'active')
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_goals_by_user(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[ConversationGoal]:
        """
        获取用户的对话目标历史

        Args:
            user_id: 用户ID
            limit: 返回数量限制

        Returns:
            ConversationGoal列表
        """
        stmt = select(ConversationGoal).where(
            ConversationGoal.user_id == user_id
        ).order_by(ConversationGoal.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def cleanup_expired_goals(self, hours: int = 24) -> int:
        """
        清理过期的对话目标

        Args:
            hours: 过期时间(小时)

        Returns:
            清理的数量
        """
        cutoff_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

        stmt = delete(ConversationGoal).where(
            or_(
                ConversationGoal.created_at < cutoff_time,
                and_(
                    ConversationGoal.status == 'completed',
                    ConversationGoal.last_updated < cutoff_time
                )
            )
        )

        result = await self.session.execute(stmt)
        await self.session.flush()

        count = result.rowcount
        if count > 0:
            logger.info(f"清理过期对话目标: {count}个")

        return count

    async def get_goal_statistics(self) -> dict:
        """
        获取对话目标统计信息

        Returns:
            统计数据字典
        """
        all_goals = await self.get_all_active_goals()

        total_sessions = len(all_goals)
        active_sessions = sum(1 for g in all_goals if g.status == 'active')
        completed_sessions = sum(1 for g in all_goals if g.status == 'completed')

        goal_type_stats = {}
        goal_switches_count = 0

        for goal in all_goals:
            goal_type = goal.final_goal.get('type') if goal.final_goal else None

            if goal_type:
                if goal_type not in goal_type_stats:
                    goal_type_stats[goal_type] = {"total": 0, "completed": 0}
                goal_type_stats[goal_type]["total"] += 1
                if goal.status == 'completed':
                    goal_type_stats[goal_type]["completed"] += 1

            goal_switches_count += len(goal.goal_switches) if goal.goal_switches else 0

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "completed_sessions": completed_sessions,
            "by_type": goal_type_stats,
            "total_goal_switches": goal_switches_count,
            "avg_switches_per_session": round(goal_switches_count / total_sessions, 2) if total_sessions > 0 else 0
        }