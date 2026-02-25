"""
增强型心理状态管理器
使用 CacheManager、Repository 和 TaskScheduler，与现有接口兼容
"""
import time
import json
import random
from typing import Dict, List, Optional, Any
from datetime import datetime

from astrbot.api import logger

from ...config import PluginConfig
from ...core.patterns import AsyncServiceBase
from ...core.interfaces import IDataStorage
from ...core.framework_llm_adapter import FrameworkLLMAdapter
from ...utils.cache_manager import get_cache_manager, async_cached
from ...utils.task_scheduler import get_task_scheduler

# 导入 Repository
from ...repositories import (
    PsychologicalStateRepository,
    PsychologicalComponentRepository,
    PsychologicalHistoryRepository
)

# 导入原有的模型和枚举
from ...models.psychological_state import (
    EmotionPositiveType, EmotionNegativeType, EmotionNeutralType,
    AttentionState, ThinkingState, MemoryState,
    WillStrengthState, ActionTendencyState, GoalOrientationState,
    SelfAcceptanceState, PersonalityTendencyState,
    SocialAttitudeState, SocialBehaviorState,
    EnergyState, InterestMotivationState,
    PsychologicalStateComponent, CompositePsychologicalState
)


class EnhancedPsychologicalStateManager(AsyncServiceBase):
    """
    增强型心理状态管理器

    改进:
    1. 使用 CacheManager 缓存心理状态
    2. 使用 Repository 访问数据库
    3. 使用 TaskScheduler 管理自动衰减和时间驱动任务
    4. 保持与原有接口的兼容性

    用法:
        # 创建管理器
        state_mgr = EnhancedPsychologicalStateManager(config, db_manager, llm_adapter)
        await state_mgr.start()
    """

    def __init__(
        self,
        config: PluginConfig,
        database_manager: IDataStorage,
        llm_adapter: Optional[FrameworkLLMAdapter] = None,
        affection_manager=None
    ):
        super().__init__("enhanced_psychological_state_manager")
        self.config = config
        self.db_manager = database_manager
        self.llm_adapter = llm_adapter
        self.affection_manager = affection_manager

        # 使用统一的缓存管理器
        self.cache = get_cache_manager()

        # 使用统一的任务调度器
        self.scheduler = get_task_scheduler()

        # 状态自然衰减速率配置（保持原有逻辑）
        self.decay_rates = {
            "情绪": 0.02,
            "认知": 0.01,
            "意志": 0.015,
            "自我认知": 0.005,
            "社交": 0.015,
            "精力": 0.03,
            "兴趣": 0.01
        }

        # 时间段对心理状态的影响规则（保持原有逻辑）
        self.time_based_rules = self._init_time_based_rules()

        self._logger.info("[增强型心理状态] 初始化完成（使用缓存管理器和任务调度器）")

    async def _do_start(self) -> bool:
        """启动心理状态管理服务"""
        try:
            # 启动任务调度器
            await self.scheduler.start()

            # 加载所有群组的当前心理状态
            await self._load_all_states()

            # 使用任务调度器替代 asyncio.create_task

            # 添加状态自动衰减任务（每30分钟执行一次）
            self.scheduler.add_interval_job(
                self._auto_decay_task,
                job_id='psychological_auto_decay',
                minutes=30
            )

            # 添加时间驱动的状态变化任务（每小时执行一次）
            self.scheduler.add_interval_job(
                self._time_driven_state_change_task,
                job_id='psychological_time_driven',
                hours=1
            )

            # 添加定期保存状态任务（每2小时）
            self.scheduler.add_interval_job(
                self._auto_save_states_task,
                job_id='psychological_auto_save',
                hours=2
            )

            # 添加定期清理历史任务（每天凌晨3点）
            self.scheduler.add_cron_job(
                self._cleanup_history_task,
                job_id='psychological_cleanup',
                hour=3,
                minute=0
            )

            self._logger.info(" [增强型心理状态] 启动成功")
            return True

        except Exception as e:
            self._logger.error(f" [增强型心理状态] 启动失败: {e}", exc_info=True)
            return False

    async def _do_stop(self) -> bool:
        """停止心理状态管理服务"""
        try:
            # 保存所有当前状态
            await self._save_all_states()

            # 移除所有定时任务
            self.scheduler.remove_job('psychological_auto_decay')
            self.scheduler.remove_job('psychological_time_driven')
            self.scheduler.remove_job('psychological_auto_save')
            self.scheduler.remove_job('psychological_cleanup')

            # 清除缓存
            self.cache.clear('state')

            self._logger.info(" [增强型心理状态] 已停止")
            return True

        except Exception as e:
            self._logger.error(f" [增强型心理状态] 停止失败: {e}")
            return False

    # 使用缓存装饰器的方法

    @async_cached(
        cache_name='state',
        key_func=lambda self, group_id, user_id: f"state:{group_id}:{user_id}"
    )
    async def get_current_state(
        self,
        group_id: str,
        user_id: str = ""
    ) -> Optional[CompositePsychologicalState]:
        """
        获取当前心理状态（带缓存）

        Args:
            group_id: 群组 ID
            user_id: 用户 ID（空字符串表示群组级别）

        Returns:
            Optional[CompositePsychologicalState]: 心理状态对象
        """
        try:
            # 从数据库获取
            if hasattr(self.db_manager, 'get_session'):
                # 新的 SQLAlchemy 版本
                async with self.db_manager.get_session() as session:
                    state_repo = PsychologicalStateRepository(session)
                    component_repo = PsychologicalComponentRepository(session)

                    # 获取状态
                    state = await state_repo.get_or_create(group_id, user_id)
                    if state is None:
                        self._logger.warning(
                            f"[增强型心理状态] 无法获取或创建状态: {group_id}:{user_id}"
                        )
                        return None

                    # 获取组件
                    components = await component_repo.get_components(state.id)

                    # 转换为 CompositePsychologicalState
                    state_components = []
                    for comp in components:
                        state_components.append(PsychologicalStateComponent(
                            category=comp.category,
                            state_type=comp.state_type,
                            value=comp.value,
                            threshold=comp.threshold,
                            description=comp.description or "",
                            start_time=float(comp.start_time) if comp.start_time else time.time()
                        ))

                    composite_state = CompositePsychologicalState(
                        group_id=group_id,
                        state_id=f"{group_id}:{user_id}",
                        components=state_components,
                        overall_state=getattr(state, 'overall_state', 'neutral'),
                        state_intensity=getattr(state, 'state_intensity', 0.5),
                        last_transition_time=getattr(state, 'last_transition_time', None)
                    )

                    return composite_state
            else:
                # 降级到原有实现
                self._logger.debug("[增强型心理状态] 使用原有数据库加载方式")
                return None

        except Exception as e:
            self._logger.error(f"[增强型心理状态] 获取状态失败: {e}")
            return None

    async def update_state(
        self,
        group_id: str,
        user_id: str,
        dimension: str,
        new_state_type: Any,
        new_value: float,
        trigger_event: str = None
    ) -> bool:
        """
        更新心理状态（自动清除缓存）

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            dimension: 维度名称
            new_state_type: 新状态类型
            new_value: 新状态值
            trigger_event: 触发事件

        Returns:
            bool: 是否更新成功
        """
        try:
            if hasattr(self.db_manager, 'get_session'):
                async with self.db_manager.get_session() as session:
                    state_repo = PsychologicalStateRepository(session)
                    component_repo = PsychologicalComponentRepository(session)
                    history_repo = PsychologicalHistoryRepository(session)

                    # 获取或创建状态
                    state = await state_repo.get_or_create(group_id, user_id)
                    if state is None:
                        self._logger.warning(
                            f"[增强型心理状态] 无法获取或创建状态: {group_id}:{user_id}"
                        )
                        return False

                    # 更新组件
                    await component_repo.update_component(
                        state.id,
                        dimension,
                        new_value,
                        group_id=group_id,
                        state_id_str=f"{group_id}:{user_id}"
                    )

                    # 记录历史
                    await history_repo.add_history(
                        state.id,
                        from_state=state.overall_state,
                        to_state=str(new_state_type),
                        trigger_event=trigger_event,
                        intensity_change=0.0,
                        group_id=group_id,
                        category=dimension
                    )

                    # 清除缓存
                    cache_key = f"state:{group_id}:{user_id}"
                    self.cache.delete('state', cache_key)

                    self._logger.debug(
                        f"[增强型心理状态] 更新成功: {group_id}:{user_id} "
                        f"{dimension} -> {new_state_type}, 已清除缓存"
                    )

                    return True

            return False

        except Exception as e:
            self._logger.error(f"[增强型心理状态] 更新状态失败: {e}")
            return False

    async def get_state_prompt_injection(
        self,
        group_id: str,
        user_id: str = ""
    ) -> str:
        """
        生成心理状态的prompt注入内容

        Args:
            group_id: 群组 ID
            user_id: 用户 ID

        Returns:
            str: Prompt 注入内容
        """
        try:
            state = await self.get_current_state(group_id, user_id)

            if not state:
                return ""

            # 生成注入内容（保持原有逻辑）
            injection_parts = []

            # 添加整体状态描述
            injection_parts.append(f"当前整体心理状态: {state.overall_state}")

            # 添加各维度状态
            components = state.components if isinstance(state.components, list) else []
            for component in components:
                dimension = getattr(component, 'category', '') or getattr(component, 'state_type', '')
                value = getattr(component, 'value', 0.0)
                state_type = getattr(component, 'state_type', '')
                injection_parts.append(
                    f"{dimension}: {state_type} "
                    f"(强度: {value:.2f})"
                )

            return "\n".join(injection_parts)

        except Exception as e:
            self._logger.error(f"[增强型心理状态] 生成注入内容失败: {e}")
            return ""

    # 任务调度方法

    async def _auto_decay_task(self):
        """状态自动衰减任务（由调度器调用）"""
        try:
            self._logger.debug("[增强型心理状态] 执行自动衰减...")

            # TODO: 实现状态衰减逻辑
            # 遍历所有活跃状态，根据 decay_rates 进行衰减

            self._logger.debug("[增强型心理状态] 自动衰减完成")

        except Exception as e:
            self._logger.error(f"[增强型心理状态] 自动衰减失败: {e}")

    async def _time_driven_state_change_task(self):
        """时间驱动的状态变化任务（由调度器调用）"""
        try:
            self._logger.debug("[增强型心理状态] 执行时间驱动状态变化...")

            # 获取当前小时
            current_hour = datetime.now().hour

            # 查找匹配的时间规则
            for rule in self.time_based_rules:
                time_range = rule['time_range']
                if time_range[0] <= current_hour < time_range[1]:
                    self._logger.debug(
                        f"[增强型心理状态] 匹配时间规则: {rule['description']}"
                    )
                    # TODO: 应用规则到所有活跃状态
                    break

            self._logger.debug("[增强型心理状态] 时间驱动状态变化完成")

        except Exception as e:
            self._logger.error(f"[增强型心理状态] 时间驱动状态变化失败: {e}")

    async def _auto_save_states_task(self):
        """自动保存状态任务（由调度器调用）"""
        try:
            self._logger.debug("[增强型心理状态] 执行自动保存...")

            await self._save_all_states()

            self._logger.debug("[增强型心理状态] 自动保存完成")

        except Exception as e:
            self._logger.error(f"[增强型心理状态] 自动保存失败: {e}")

    async def _cleanup_history_task(self):
        """清理历史记录任务（由调度器调用）"""
        try:
            self._logger.info("[增强型心理状态] 执行历史清理...")

            if hasattr(self.db_manager, 'get_session'):
                async with self.db_manager.get_session() as session:
                    history_repo = PsychologicalHistoryRepository(session)

                    # TODO: 获取所有状态ID并清理30天前的历史
                    # 示例实现
                    # for state_id in state_ids:
                    # deleted = await history_repo.clean_old_history(state_id, days=30)

            self._logger.info("[增强型心理状态] 历史清理完成")

        except Exception as e:
            self._logger.error(f"[增强型心理状态] 清理历史失败: {e}")

    # 辅助方法（保持原有逻辑）

    def _init_time_based_rules(self) -> List[Dict[str, Any]]:
        """初始化基于时间的状态变化规则"""
        return [
            {
                "time_range": (0, 5),
                "states": [
                    ("精力", EnergyState.SLEEPY, 0.7, "凌晨时分非常困倦"),
                    ("认知", AttentionState.SCATTERED, 0.6, "注意力涣散"),
                    ("情绪", EmotionNeutralType.CALM, 0.5, "夜深人静心情平静")
                ],
                "description": "深夜时分，困倦且注意力不集中"
            },
            {
                "time_range": (9, 11),
                "states": [
                    ("精力", EnergyState.VIGOROUS, 0.7, "精力充沛"),
                    ("认知", AttentionState.FOCUSED, 0.7, "注意力集中"),
                    ("情绪", EmotionPositiveType.MOTIVATED, 0.6, "充满干劲")
                ],
                "description": "上午精力旺盛，状态最佳"
            },
            # ... 其他时间规则
        ]

    async def _load_all_states(self):
        """加载所有群组的心理状态"""
        try:
            # TODO: 从数据库加载所有活跃群组的状态
            self._logger.debug("[增强型心理状态] 加载所有状态...")

        except Exception as e:
            self._logger.error(f"[增强型心理状态] 加载状态失败: {e}")

    async def _save_all_states(self):
        """保存所有心理状态到数据库"""
        try:
            # TODO: 保存所有状态到数据库
            self._logger.debug("[增强型心理状态] 保存所有状态...")

        except Exception as e:
            self._logger.error(f"[增强型心理状态] 保存状态失败: {e}")

    # 缓存统计方法

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return self.cache.get_stats('state')

    def clear_cache(self):
        """清除所有缓存"""
        self.cache.clear('state')
        self._logger.info("[增强型心理状态] 已清除所有缓存")
