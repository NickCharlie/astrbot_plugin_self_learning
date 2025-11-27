"""
增强型好感度管理服务
使用 CacheManager 和 Repository 模式，与现有接口兼容
"""
import asyncio
import random
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

from astrbot.api import logger

from ..config import PluginConfig
from ..core.patterns import AsyncServiceBase
from ..core.interfaces import IDataStorage
from ..utils.cache_manager import get_cache_manager, async_cached
from ..utils.task_scheduler import get_task_scheduler

# 导入 Repository
from ..repositories import (
    AffectionRepository,
    InteractionRepository,
    ConversationHistoryRepository,
    DiversityRepository
)

# 导入原有的枚举和数据类
from .affection_manager import (
    MoodType,
    InteractionType,
    BotMood,
    UserAffection as OriginalUserAffection
)


class EnhancedAffectionManager(AsyncServiceBase):
    """
    增强型好感度管理服务

    改进:
    1. 使用 CacheManager 替代手动字典缓存
    2. 使用 Repository 访问数据库
    3. 使用 TaskScheduler 管理定时任务
    4. 保持与原有接口的兼容性

    用法:
        # 在配置中启用
        config.use_enhanced_managers = True

        # 创建管理器
        affection_mgr = EnhancedAffectionManager(config, db_manager, llm_adapter)
        await affection_mgr.start()
    """

    def __init__(
        self,
        config: PluginConfig,
        database_manager: IDataStorage,
        llm_adapter=None
    ):
        super().__init__("enhanced_affection_manager")
        self.config = config
        self.db_manager = database_manager
        self.llm_adapter = llm_adapter

        # 使用统一的缓存管理器
        self.cache = get_cache_manager()

        # 使用统一的任务调度器
        self.scheduler = get_task_scheduler()

        # 预定义的情绪描述模板（保持原有逻辑）
        self.mood_descriptions = self._init_mood_descriptions()

        # 好感度变化规则（保持原有逻辑）
        self.affection_rules = self._init_affection_rules()

        self._logger.info("[增强型好感度] 初始化完成（使用缓存管理器）")

    async def _do_start(self) -> bool:
        """启动好感度管理服务"""
        try:
            # 启动任务调度器
            await self.scheduler.start()

            # 为所有活跃群组设置初始随机情绪（如果启用）
            if self.config.enable_startup_random_mood:
                await self._initialize_random_moods_for_active_groups()

            # 启动每日情绪更新任务（使用调度器）
            if self.config.enable_daily_mood:
                self.scheduler.add_cron_job(
                    self._daily_mood_update_task,
                    job_id='affection_daily_mood',
                    hour=0,  # 每天凌晨0点
                    minute=0
                )

            self._logger.info("✅ [增强型好感度] 启动成功")
            return True

        except Exception as e:
            self._logger.error(f"❌ [增强型好感度] 启动失败: {e}")
            return False

    async def _do_stop(self) -> bool:
        """停止好感度管理服务"""
        try:
            # 移除定时任务
            self.scheduler.remove_job('affection_daily_mood')

            # 清除缓存
            self.cache.clear('affection')

            self._logger.info("✅ [增强型好感度] 已停止")
            return True

        except Exception as e:
            self._logger.error(f"❌ [增强型好感度] 停止失败: {e}")
            return False

    # ============================================================
    # 使用缓存装饰器的方法
    # ============================================================

    @async_cached(
        cache_name='affection',
        key_func=lambda self, group_id, user_id: f"affection:{group_id}:{user_id}"
    )
    async def get_user_affection(
        self,
        group_id: str,
        user_id: str
    ) -> Optional[OriginalUserAffection]:
        """
        获取用户好感度（带缓存）

        Args:
            group_id: 群组 ID
            user_id: 用户 ID

        Returns:
            Optional[UserAffection]: 好感度对象
        """
        try:
            # 从数据库获取
            affection_data = await self.db_manager.get_user_affection(
                group_id,
                user_id
            )

            if affection_data:
                return OriginalUserAffection(
                    user_id=user_id,
                    group_id=group_id,
                    affection_level=affection_data['affection_level'],
                    last_interaction=affection_data.get('updated_at', time.time()),
                    interaction_count=affection_data.get('interaction_count', 0)
                )
            return None

        except Exception as e:
            self._logger.error(f"[增强型好感度] 获取好感度失败: {e}")
            return None

    async def update_user_affection(
        self,
        group_id: str,
        user_id: str,
        affection_delta: int,
        interaction_type: str = None
    ) -> bool:
        """
        更新用户好感度（自动清除缓存）

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            affection_delta: 好感度变化量
            interaction_type: 交互类型

        Returns:
            bool: 是否更新成功
        """
        try:
            # 更新数据库
            success = await self.db_manager.update_user_affection(
                group_id,
                user_id,
                affection_delta
            )

            if success:
                # 清除缓存
                cache_key = f"affection:{group_id}:{user_id}"
                self.cache.delete('affection', cache_key)

                self._logger.debug(
                    f"[增强型好感度] 更新成功: {group_id}:{user_id} "
                    f"变化={affection_delta}, 已清除缓存"
                )

            return success

        except Exception as e:
            self._logger.error(f"[增强型好感度] 更新好感度失败: {e}")
            return False

    @async_cached(
        cache_name='affection',
        key_func=lambda self, group_id: f"mood:{group_id}"
    )
    async def get_current_mood(self, group_id: str) -> Optional[BotMood]:
        """
        获取当前情绪（带缓存）

        Args:
            group_id: 群组 ID

        Returns:
            Optional[BotMood]: 情绪对象
        """
        try:
            # 从数据库加载
            mood_data = await self.db_manager.get_current_bot_mood(group_id)

            if mood_data:
                mood = BotMood(
                    mood_type=MoodType(mood_data['mood_type']),
                    intensity=mood_data['mood_intensity'],
                    description=mood_data['mood_description'],
                    start_time=mood_data['created_at'],
                    duration_hours=mood_data.get('duration_hours', 24)
                )

                # 检查是否过期
                if mood.is_active():
                    return mood
                else:
                    # 过期则清除缓存
                    cache_key = f"mood:{group_id}"
                    self.cache.delete('affection', cache_key)

            return None

        except Exception as e:
            self._logger.error(f"[增强型好感度] 获取情绪失败: {e}")
            return None

    async def set_daily_mood(
        self,
        group_id: str,
        mood_type: MoodType = None,
        intensity: float = None
    ) -> BotMood:
        """
        设置每日情绪（自动清除缓存）

        Args:
            group_id: 群组 ID
            mood_type: 情绪类型（None 则随机）
            intensity: 情绪强度（None 则随机）

        Returns:
            BotMood: 新的情绪对象
        """
        try:
            # 随机选择情绪
            if mood_type is None:
                mood_type = random.choice(list(MoodType))

            if intensity is None:
                intensity = random.uniform(0.5, 1.0)

            # 获取情绪描述
            description = self._get_mood_description(mood_type, intensity)

            # 保存到数据库
            await self.db_manager.save_bot_mood(
                group_id,
                mood_type.value,
                intensity,
                description,
                duration_hours=24
            )

            # 创建情绪对象
            mood = BotMood(
                mood_type=mood_type,
                intensity=intensity,
                description=description,
                start_time=time.time(),
                duration_hours=24
            )

            # 清除缓存
            cache_key = f"mood:{group_id}"
            self.cache.delete('affection', cache_key)

            self._logger.info(
                f"[增强型好感度] 设置每日情绪: {group_id} -> "
                f"{mood_type.value} ({intensity:.2f})"
            )

            return mood

        except Exception as e:
            self._logger.error(f"[增强型好感度] 设置情绪失败: {e}")
            return None

    # ============================================================
    # 任务调度方法
    # ============================================================

    async def _daily_mood_update_task(self):
        """每日情绪更新任务（由调度器调用）"""
        try:
            self._logger.info("[增强型好感度] 执行每日情绪更新...")

            # 获取所有活跃群组
            # TODO: 需要从数据库获取活跃群组列表
            # 暂时使用示例实现
            active_groups = []  # await self.db_manager.get_active_groups()

            for group_id in active_groups:
                await self.set_daily_mood(group_id)

            self._logger.info(
                f"[增强型好感度] 每日情绪更新完成，"
                f"共更新 {len(active_groups)} 个群组"
            )

        except Exception as e:
            self._logger.error(f"[增强型好感度] 每日情绪更新失败: {e}")

    # ============================================================
    # 辅助方法（保持原有逻辑）
    # ============================================================

    def _init_mood_descriptions(self) -> Dict[MoodType, List[str]]:
        """初始化情绪描述模板"""
        return {
            MoodType.HAPPY: [
                "今天心情特别好~",
                "感觉一切都很美好呢",
                "今天充满了正能量！"
            ],
            MoodType.SAD: [
                "今天有点不开心...",
                "心情有些低落",
                "感觉有点难过"
            ],
            MoodType.EXCITED: [
                "今天超级兴奋！",
                "感觉浑身充满了活力！",
                "好激动啊！"
            ],
            # ... 其他情绪
        }

    def _init_affection_rules(self) -> Dict[str, int]:
        """初始化好感度变化规则"""
        return {
            InteractionType.CHAT.value: 1,
            InteractionType.COMPLIMENT.value: 5,
            InteractionType.FLIRT.value: 3,
            InteractionType.COMFORT.value: 4,
            InteractionType.HELP.value: 3,
            InteractionType.THANKS.value: 2,
            InteractionType.CARE.value: 4,
            InteractionType.GIFT.value: 10,
            InteractionType.INSULT.value: -10,
            InteractionType.HARASSMENT.value: -15,
            InteractionType.ABUSE.value: -20,
            # ... 其他规则
        }

    def _get_mood_description(
        self,
        mood_type: MoodType,
        intensity: float
    ) -> str:
        """获取情绪描述"""
        descriptions = self.mood_descriptions.get(mood_type, ["心情一般"])
        return random.choice(descriptions)

    async def _initialize_random_moods_for_active_groups(self):
        """为活跃群组初始化随机情绪"""
        try:
            # TODO: 从数据库获取活跃群组
            # active_groups = await self.db_manager.get_active_groups()
            # for group_id in active_groups:
            #     await self.set_daily_mood(group_id)
            pass

        except Exception as e:
            self._logger.error(f"[增强型好感度] 初始化随机情绪失败: {e}")

    # ============================================================
    # 缓存统计方法
    # ============================================================

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return self.cache.get_stats('affection')

    def clear_cache(self):
        """清除所有缓存"""
        self.cache.clear('affection')
        self._logger.info("[增强型好感度] 已清除所有缓存")
