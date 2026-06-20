"""
MaiBot式表达模式学习器 - 实现场景-表达映射的细粒度学习
基于MaiBot的expression_learner.py思路，实现场景化的语言风格学习
"""
import time
import json
import random
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from astrbot.api import logger

from ...core.interfaces import MessageData, ServiceLifecycle
from ...core.framework_llm_adapter import FrameworkLLMAdapter
from ...config import PluginConfig
from ...exceptions import ExpressionLearningError, ModelAccessError
from ...utils.json_utils import safe_parse_llm_json
from ...utils.persona_selection import normalize_persona_scope
from ..database import DatabaseManager


@dataclass
class ExpressionPattern:
    """表达模式数据结构"""
    situation: str # 场景描述，如"对某件事表示十分惊叹"
    expression: str # 表达方式，如"我嘞个xxxx"
    weight: float # 权重（使用频率）
    last_active_time: float # 最后活跃时间
    create_time: float # 创建时间
    group_id: str # 所属群组ID
    persona_id: str = "default" # 所属 Bot/人格隔离ID
    user_id: Optional[str] = None # 可选用户维度；None 表示群组级模式
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExpressionPattern':
        return cls(**data)


class ExpressionPatternLearner:
    """
    MaiBot式表达模式学习器
    实现场景-表达映射的细粒度学习，完全参考MaiBot的设计思路
    采用单例模式确保全局唯一实例
    """
    
    # MaiBot的配置参数
    MAX_EXPRESSION_COUNT = 300 # 最大表达式数量
    DECAY_DAYS = 15 # 15天衰减周期
    DECAY_MIN = 0.01 # 最小衰减值
    MIN_MESSAGES_FOR_LEARNING = 5 # 触发学习所需的最少消息数
    MIN_LEARNING_INTERVAL = 300 # 最短学习时间间隔（秒）
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: PluginConfig = None, db_manager: DatabaseManager = None, context=None, llm_adapter=None):
        # 防止重复初始化
        if self._initialized:
            return
            
        self.config = config
        self.db_manager = db_manager
        
        # 优先使用传入的llm_adapter，否则尝试创建新的
        if llm_adapter:
            self.llm_adapter = llm_adapter
        elif context:
            # 使用正确的context创建FrameworkLLMAdapter
            self.llm_adapter = FrameworkLLMAdapter(context)
            if config:
                self.llm_adapter.initialize_providers(config)
        elif config:
            # 旧的方式，可能会有问题
            self.llm_adapter = FrameworkLLMAdapter(config)
        else:
            self.llm_adapter = None
        
        self._status = ServiceLifecycle.CREATED
        
        # 维护每个群组/人格隔离 scope 的上次学习时间
        self.last_learning_times: Dict[str, float] = {}

        # 数据库表初始化标志（将在 start() 中异步初始化）
        self._table_initialized = False

        self._initialized = True

    @staticmethod
    def _normalize_user_scope(
        user_id: Optional[str],
        fallback: Optional[str] = None,
    ) -> Optional[str]:
        value = user_id if user_id is not None else fallback
        value = str(value or "").strip()
        if not value or value == "bot":
            return None
        return value

    @staticmethod
    def _expression_scope_key(
        group_id: str,
        persona_id: str,
        user_id: Optional[str] = None,
    ) -> str:
        return f"{group_id}:{persona_id}:{user_id or 'group-level'}"
    
    @classmethod
    def get_instance(cls, config: PluginConfig = None, db_manager: DatabaseManager = None, context=None, llm_adapter=None) -> 'ExpressionPatternLearner':
        """获取单例实例，支持延迟初始化"""
        if cls._instance is None:
            cls._instance = cls(config, db_manager, context, llm_adapter)
        elif not cls._initialized or (cls._instance.llm_adapter is None and (context or llm_adapter)):
            # 如果实例存在但未正确初始化，或者现在有更好的初始化参数，重新初始化
            logger.info("重新初始化ExpressionPatternLearner单例，提供更好的参数")
            cls._initialized = False
            cls._instance.__init__(config, db_manager, context, llm_adapter)
        return cls._instance
    
    async def _init_expression_patterns_table(self):
        """表达模式表由 ORM (models/orm/expression.py) 在引擎启动时自动创建"""
        self._table_initialized = True
    
    async def start(self) -> bool:
        """启动服务"""
        # 初始化数据库表
        if self.db_manager and not self._table_initialized:
            await self._init_expression_patterns_table()

        self._status = ServiceLifecycle.RUNNING
        logger.info("ExpressionPatternLearner服务已启动")
        return True
    
    async def stop(self) -> bool:
        """停止服务"""
        self._status = ServiceLifecycle.STOPPED
        logger.info("ExpressionPatternLearner服务已停止")
        return True
    
    def should_trigger_learning(self, group_id: str, recent_messages: List[MessageData]) -> bool:
        """
        检查是否应该触发学习 - 只检查消息数量（已移除时间间隔限制）

        Args:
            group_id: 群组ID
            recent_messages: 最近的消息列表

        Returns:
            bool: 是否应该触发学习
        """
        # 检查消息数量（至少5条消息）
        if len(recent_messages) < 5:
            logger.debug(f"群组 {group_id} 消息数量不足: {len(recent_messages)} < 5")
            return False

        return True
    
    async def trigger_learning_for_group(
        self,
        group_id: str,
        recent_messages: List[MessageData],
        persona_id: str = "default",
        user_id: Optional[str] = None,
    ) -> bool:
        """
        为指定群组触发表达模式学习
        
        Args:
            group_id: 群组ID
            recent_messages: 最近的消息列表
            
        Returns:
            bool: 是否成功学习到新模式
        """
        if not self.should_trigger_learning(group_id, recent_messages):
            return False
        
        try:
            persona_id = normalize_persona_scope(persona_id)
            user_scope = self._normalize_user_scope(user_id)
            learning_scope = self._expression_scope_key(group_id, persona_id, user_scope)
            logger.info(
                f"为群组 {group_id} / 人格 {persona_id} 触发表达模式学习，"
                f"消息数量: {len(recent_messages)}"
            )
            
            # 学习表达模式
            learned_patterns = await self.learn_expression_patterns(
                recent_messages,
                group_id,
                persona_id=persona_id,
                user_id=user_scope,
            )
            
            if learned_patterns:
                # 保存到数据库
                await self._save_expression_patterns(
                    learned_patterns,
                    group_id,
                    persona_id=persona_id,
                    user_id=user_scope,
                )
                
                # 应用时间衰减
                await self._apply_time_decay(group_id, persona_id=persona_id, user_id=user_scope)
                
                # 限制最大数量
                await self._limit_max_expressions(group_id, persona_id=persona_id, user_id=user_scope)
                
                # 更新学习时间
                self.last_learning_times[learning_scope] = time.time()
                
                logger.info(f"群组 {group_id} 表达模式学习完成，学到 {len(learned_patterns)} 个新模式")
                return True
            else:
                logger.warning(f"群组 {group_id} 表达模式学习未获得有效结果")
                return False
                
        except Exception as e:
            logger.error(f"群组 {group_id} 表达模式学习失败: {e}")
            return False
    
    async def learn_expression_patterns(
        self,
        messages: List[MessageData],
        group_id: str,
        persona_id: str = "default",
        user_id: Optional[str] = None,
    ) -> List[ExpressionPattern]:
        """
        学习表达模式 - 从原始消息中直接提取 A/B 对话对（不调用LLM）

        Args:
            messages: 消息列表
            group_id: 群组ID

        Returns:
            学习到的表达模式列表
        """
        try:
            # 直接从消息中提取对话对作为 few-shot 样本（不调用LLM）
            patterns = self._extract_few_shot_pairs(
                messages,
                group_id,
                persona_id=persona_id,
                user_id=user_id,
            )

            if patterns:
                logger.info(f"从消息中提取到 {len(patterns)} 个 few-shot 对话对 (group: {group_id})")
            else:
                logger.debug(f"未从消息中提取到对话对 (group: {group_id})")

            return patterns

        except Exception as e:
            logger.error(f"学习表达模式失败: {e}")
            raise ExpressionLearningError(f"表达模式学习失败: {e}")

    def _extract_few_shot_pairs(
        self,
        messages: List[MessageData],
        group_id: str,
        persona_id: str = "default",
        user_id: Optional[str] = None,
    ) -> List[ExpressionPattern]:
        """
        从原始消息中提取用户-bot 对话对作为 few-shot 样本。
        寻找「用户发言 → bot回复」的连续对，直接作为 situation/expression 保存。
        """
        pairs = []
        current_time = time.time()
        persona_id = normalize_persona_scope(persona_id)
        user_id = self._normalize_user_scope(user_id)

        for i in range(len(messages) - 1):
            msg = messages[i]
            next_msg = messages[i + 1]

            # 兼容字典和对象
            if hasattr(msg, 'sender_id'):
                msg_is_bot = msg.sender_id == "bot"
                msg_content = (getattr(msg, 'message', '') or '').strip()
                next_is_bot = next_msg.sender_id == "bot"
                next_content = (getattr(next_msg, 'message', '') or '').strip()
            else:
                msg_is_bot = msg.get('sender_id') == "bot"
                msg_content = msg.get('message', '').strip()
                next_is_bot = next_msg.get('sender_id') == "bot"
                next_content = next_msg.get('message', '').strip()

            # 用户发言 → bot回复
            if not msg_is_bot and next_is_bot and msg_content and next_content:
                # 过滤过短或纯链接/图片/@的消息
                if len(msg_content) < 3 or len(next_content) < 3:
                    continue
                if msg_content.startswith(('[', 'http', '@')):
                    continue
                if next_content.startswith(('[', 'http', '@')):
                    continue
                if '@' in msg_content or '@' in next_content:
                    continue

                pairs.append(ExpressionPattern(
                    situation=msg_content[:50],
                    expression=next_content[:100],
                    weight=1.0,
                    last_active_time=current_time,
                    create_time=current_time,
                    group_id=group_id,
                    persona_id=persona_id,
                    user_id=user_id,
                ))

        return pairs

    # ---- 以下为旧版 LLM 分析代码，已停用 ----

    # def _build_anonymous_chat_context(self, messages: List[MessageData]) -> str:
    #     """
    #     构建匿名化的聊天上下文 - 参考MaiBot的build_anonymous_messages
    #     """
    #     context_lines = []
    #     for msg in messages:
    #         if hasattr(msg, 'sender_id'):
    #             is_bot = msg.sender_id == "bot"
    #             sender = msg.sender_name or msg.sender_id or 'Unknown'
    #             content = msg.message.strip() if msg.message else ''
    #             timestamp = msg.timestamp
    #         else:
    #             is_bot = msg.get('sender_id') == "bot"
    #             sender = msg.get('sender_name') or msg.get('sender_id') or 'Unknown'
    #             content = msg.get('message', '').strip()
    #             timestamp = msg.get('timestamp', time.time())
    #         if content and not content.startswith('[') and not content.startswith('http'):
    #             timestamp_str = datetime.fromtimestamp(timestamp).strftime("%H:%M")
    #             context_lines.append(f"{timestamp_str} {sender}: {content}")
    #     return '\n'.join(context_lines)

    # def _generate_fallback_expression_patterns(self, messages): ...
    # def _parse_expression_response(self, response, group_id): ...
    
    async def _save_expression_patterns(
        self,
        patterns: List[ExpressionPattern],
        group_id: str,
        persona_id: str = "default",
        user_id: Optional[str] = None,
    ):
        """保存表达模式到数据库（ORM 版本）"""
        try:
            from sqlalchemy import desc, select
            from ...models.orm.expression import ExpressionPattern as ExpressionPatternORM
            persona_id = normalize_persona_scope(persona_id)
            user_id = self._normalize_user_scope(user_id)

            async with self.db_manager.get_session() as session:
                for pattern in patterns:
                    pattern_persona_id = normalize_persona_scope(
                        getattr(pattern, "persona_id", None),
                        fallback=persona_id,
                    )
                    pattern_user_id = self._normalize_user_scope(
                        getattr(pattern, "user_id", None),
                        fallback=user_id,
                    )
                    # 查找是否已存在相似模式
                    stmt = select(ExpressionPatternORM).where(
                        ExpressionPatternORM.situation == pattern.situation,
                        ExpressionPatternORM.expression == pattern.expression,
                        ExpressionPatternORM.group_id == group_id,
                        ExpressionPatternORM.persona_id == pattern_persona_id,
                        ExpressionPatternORM.user_id.is_(None)
                        if pattern_user_id is None
                        else ExpressionPatternORM.user_id == pattern_user_id,
                    ).order_by(
                        desc(ExpressionPatternORM.weight),
                        desc(ExpressionPatternORM.last_active_time),
                        desc(ExpressionPatternORM.id),
                    )
                    result = await session.execute(stmt)
                    matches = list(result.scalars().all())
                    existing = matches[0] if matches else None
                    if len(matches) > 1:
                        logger.warning(
                            "发现重复表达模式记录，已复用权重最高记录: "
                            f"group_id={group_id}, situation={pattern.situation!r}, "
                            f"expression={pattern.expression!r}, "
                            f"persona_id={pattern_persona_id}, "
                            f"user_id={pattern_user_id or 'group-level'}, count={len(matches)}"
                        )

                    if existing:
                        # 更新现有模式，权重增加，50%概率替换内容
                        existing.weight += 1.0
                        existing.last_active_time = pattern.last_active_time
                        if random.random() < 0.5:
                            existing.situation = pattern.situation
                            existing.expression = pattern.expression
                    else:
                        # 插入新模式
                        new_record = ExpressionPatternORM(
                            situation=pattern.situation,
                            expression=pattern.expression,
                            weight=pattern.weight,
                            last_active_time=pattern.last_active_time,
                            create_time=pattern.create_time,
                            group_id=pattern.group_id,
                            persona_id=pattern_persona_id,
                            user_id=pattern_user_id,
                        )
                        session.add(new_record)

                await session.commit()
                logger.info(f" 保存了 {len(patterns)} 个表达模式到数据库（群组: {group_id}）")

        except Exception as e:
            logger.error(f"保存表达模式失败: {e}", exc_info=True)
            raise ExpressionLearningError(f"保存表达模式失败: {e}")
    
    async def _apply_time_decay(
        self,
        group_id: str,
        persona_id: str = "default",
        user_id: Optional[str] = None,
    ):
        """应用时间衰减 - 完全参考MaiBot的衰减机制（ORM 版本）"""
        try:
            from sqlalchemy import select, delete
            from ...models.orm.expression import ExpressionPattern as ExpressionPatternORM
            persona_id = normalize_persona_scope(persona_id)
            user_id = self._normalize_user_scope(user_id)

            current_time = time.time()
            updated_count = 0
            deleted_count = 0

            async with self.db_manager.get_session() as session:
                # 获取所有该群组的表达模式
                stmt = select(ExpressionPatternORM).where(
                    ExpressionPatternORM.group_id == group_id,
                    ExpressionPatternORM.persona_id == persona_id,
                    ExpressionPatternORM.user_id.is_(None)
                    if user_id is None
                    else ExpressionPatternORM.user_id == user_id,
                )
                result = await session.execute(stmt)
                patterns = result.scalars().all()

                ids_to_delete = []
                for pattern in patterns:
                    # 计算时间差（天）
                    time_diff_days = (current_time - pattern.last_active_time) / (24 * 3600)

                    # 计算衰减值
                    decay_value = self._calculate_decay_factor(time_diff_days)
                    new_weight = max(self.DECAY_MIN, pattern.weight - decay_value)

                    if new_weight <= self.DECAY_MIN:
                        ids_to_delete.append(pattern.id)
                        deleted_count += 1
                    else:
                        pattern.weight = new_weight
                        updated_count += 1

                # 批量删除权重过低的模式
                if ids_to_delete:
                    await session.execute(
                        delete(ExpressionPatternORM).where(
                            ExpressionPatternORM.id.in_(ids_to_delete)
                        )
                    )

                await session.commit()

                if updated_count > 0 or deleted_count > 0:
                    logger.info(f"群组 {group_id} 时间衰减完成：更新了 {updated_count} 个，删除了 {deleted_count} 个表达模式")

        except Exception as e:
            logger.error(f"应用时间衰减失败: {e}", exc_info=True)
    
    def _calculate_decay_factor(self, time_diff_days: float) -> float:
        """
        计算衰减因子 - 完全参考MaiBot的衰减算法
        当时间差为0天时，衰减值为0（最近活跃的不衰减）
        当时间差为15天或更长时，衰减值为0.01（高衰减）
        使用二次函数进行曲线插值
        """
        if time_diff_days <= 0:
            return 0.0 # 刚激活的表达式不衰减
        
        if time_diff_days >= self.DECAY_DAYS:
            return 0.01 # 长时间未活跃的表达式大幅衰减
        
        # 使用二次函数插值：在0-15天之间从0衰减到0.01
        a = 0.01 / (self.DECAY_DAYS ** 2)
        decay = a * (time_diff_days ** 2)
        
        return min(0.01, decay)
    
    async def _limit_max_expressions(
        self,
        group_id: str,
        persona_id: str = "default",
        user_id: Optional[str] = None,
    ):
        """限制最大表达模式数量（ORM 版本）"""
        try:
            from sqlalchemy import select, func, delete, asc
            from ...models.orm.expression import ExpressionPattern as ExpressionPatternORM
            persona_id = normalize_persona_scope(persona_id)
            user_id = self._normalize_user_scope(user_id)

            async with self.db_manager.get_session() as session:
                # 统计当前数量
                count_stmt = select(func.count()).select_from(ExpressionPatternORM).where(
                    ExpressionPatternORM.group_id == group_id,
                    ExpressionPatternORM.persona_id == persona_id,
                    ExpressionPatternORM.user_id.is_(None)
                    if user_id is None
                    else ExpressionPatternORM.user_id == user_id,
                )
                count = (await session.execute(count_stmt)).scalar() or 0

                if count > self.MAX_EXPRESSION_COUNT:
                    excess_count = count - self.MAX_EXPRESSION_COUNT

                    # 查询权重最小的 ID
                    ids_stmt = (
                        select(ExpressionPatternORM.id)
                        .where(
                            ExpressionPatternORM.group_id == group_id,
                            ExpressionPatternORM.persona_id == persona_id,
                            ExpressionPatternORM.user_id.is_(None)
                            if user_id is None
                            else ExpressionPatternORM.user_id == user_id,
                        )
                        .order_by(asc(ExpressionPatternORM.weight))
                        .limit(excess_count)
                    )
                    result = await session.execute(ids_stmt)
                    ids_to_delete = [row[0] for row in result.fetchall()]

                    if ids_to_delete:
                        await session.execute(
                            delete(ExpressionPatternORM).where(
                                ExpressionPatternORM.id.in_(ids_to_delete)
                            )
                        )
                        await session.commit()
                        logger.info(f"群组 {group_id} 删除了 {len(ids_to_delete)} 个权重最小的表达模式")

        except Exception as e:
            logger.error(f"限制表达模式数量失败: {e}", exc_info=True)
    
    async def get_expression_patterns(
        self,
        group_id: str,
        limit: int = 10,
        persona_id: str = "default",
        user_id: Optional[str] = None,
    ) -> List[ExpressionPattern]:
        """获取群组的表达模式（ORM 版本）"""
        try:
            from sqlalchemy import select, desc
            from ...models.orm.expression import ExpressionPattern as ExpressionPatternORM
            persona_id = normalize_persona_scope(persona_id)
            user_id = self._normalize_user_scope(user_id)

            async with self.db_manager.get_session() as session:
                stmt = (
                    select(ExpressionPatternORM)
                    .where(
                        ExpressionPatternORM.group_id == group_id,
                        ExpressionPatternORM.persona_id == persona_id,
                        ExpressionPatternORM.user_id.is_(None)
                        if user_id is None
                        else ExpressionPatternORM.user_id == user_id,
                    )
                    .order_by(desc(ExpressionPatternORM.weight))
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                return [
                    ExpressionPattern(
                        situation=row.situation,
                        expression=row.expression,
                        weight=row.weight,
                        last_active_time=row.last_active_time,
                        create_time=row.create_time,
                        group_id=row.group_id,
                        persona_id=row.persona_id,
                        user_id=row.user_id,
                    )
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"获取表达模式失败: {e}", exc_info=True)
            return []
    
    async def format_expression_patterns_for_prompt(
        self,
        group_id: str,
        limit: int = 5,
        persona_id: str = "default",
        user_id: Optional[str] = None,
    ) -> str:
        """
        格式化表达模式用于prompt
        
        Returns:
            格式化的表达模式字符串，用于插入到对话prompt中
        """
        patterns = await self.get_expression_patterns(
            group_id,
            limit,
            persona_id=persona_id,
            user_id=user_id,
        )
        
        if not patterns:
            return ""
        
        lines = ["学到的表达习惯："]
        for pattern in patterns:
            lines.append(f"- 当{pattern.situation}时，可以{pattern.expression}")
        
        return "\n".join(lines)
