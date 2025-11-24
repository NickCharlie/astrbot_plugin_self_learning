"""
数据导出格式化服务
用于将插件内部数据转换为标准JSON格式，供外部系统（如liyn-web）使用

设计原则：
1. 通用性：支持多种数据类型的导出（情绪、好感度、学习数据等）
2. 扩展性：便于未来添加新的数据类型
3. 统一格式：所有导出数据遵循统一的响应结构
4. 安全性：数据过滤和权限控制
"""
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from astrbot.api import logger

from ..config import PluginConfig
from ..core.patterns import AsyncServiceBase
from ..core.interfaces import IDataStorage
from .affection_manager import AffectionManager, MoodType, InteractionType


class DataExportType(Enum):
    """数据导出类型枚举"""
    EMOTION = "emotion"  # 情绪数据
    AFFECTION = "affection"  # 好感度数据
    LEARNING_STATS = "learning_stats"  # 学习统计数据
    STYLE_PATTERNS = "style_patterns"  # 风格模式数据
    SOCIAL_RELATIONS = "social_relations"  # 社交关系数据
    MESSAGE_STATS = "message_stats"  # 消息统计数据
    COMPREHENSIVE = "comprehensive"  # 综合数据（包含所有）


@dataclass
class EmotionData:
    """情绪数据结构"""
    group_id: str
    mood_type: str  # happy, sad, excited, calm, angry, anxious, playful, serious, nostalgic, curious
    mood_intensity: float  # 0.0 - 1.0
    mood_description: str
    start_time: float
    end_time: Optional[float]
    is_active: bool
    created_at: str


@dataclass
class UserAffectionData:
    """用户好感度数据结构"""
    user_id: str
    group_id: str
    affection_level: int  # 0-100
    last_interaction: float
    interaction_count: int
    last_updated: float
    created_at: str


@dataclass
class GroupAffectionSummary:
    """群组好感度汇总数据"""
    group_id: str
    total_affection: int
    max_total_affection: int  # 250
    user_count: int
    avg_affection: float
    top_users: List[Dict[str, Any]]  # 前5名用户
    last_updated: float


@dataclass
class StandardResponse:
    """标准响应数据结构 - 所有导出数据都遵循此格式"""
    success: bool
    timestamp: float
    data_type: str  # 数据类型：emotion, affection, learning_stats等
    group_id: Optional[str]  # 群组ID（如果适用）
    user_id: Optional[str]  # 用户ID（如果适用）
    data: Optional[Dict[str, Any]]  # 实际数据内容
    metadata: Optional[Dict[str, Any]]  # 元数据（统计信息等）
    message: Optional[str]
    error: Optional[str]


class DataExportFormatter(AsyncServiceBase):
    """通用数据导出格式化服务

    职责：
    1. 统一数据导出接口
    2. 支持多种数据类型的格式化
    3. 提供数据过滤和权限控制
    4. 便于未来扩展新的数据类型
    """

    def __init__(
        self,
        config: PluginConfig,
        database_manager: IDataStorage,
        affection_manager: Optional[AffectionManager] = None
    ):
        super().__init__("data_export_formatter")
        self.config = config
        self.db_manager = database_manager
        self.affection_manager = affection_manager

        # 数据导出处理器注册表（使用策略模式）
        self._exporters: Dict[DataExportType, Callable] = {}

    async def _do_start(self) -> bool:
        """启动服务并注册数据导出处理器"""
        # 注册内置数据导出处理器
        self._register_builtin_exporters()

        self._logger.info("通用数据导出格式化服务启动成功")
        return True

    async def _do_stop(self) -> bool:
        """停止服务"""
        return True

    def _register_builtin_exporters(self):
        """注册内置的数据导出处理器"""
        self._exporters[DataExportType.EMOTION] = self._export_emotion_data
        self._exporters[DataExportType.AFFECTION] = self._export_affection_data
        self._exporters[DataExportType.LEARNING_STATS] = self._export_learning_stats
        self._exporters[DataExportType.STYLE_PATTERNS] = self._export_style_patterns
        self._exporters[DataExportType.SOCIAL_RELATIONS] = self._export_social_relations
        self._exporters[DataExportType.MESSAGE_STATS] = self._export_message_stats
        self._exporters[DataExportType.COMPREHENSIVE] = self._export_comprehensive_data

    def register_custom_exporter(
        self,
        export_type: str,
        exporter_func: Callable
    ):
        """
        注册自定义数据导出处理器（用于扩展）

        Args:
            export_type: 自定义的导出类型名称
            exporter_func: 导出处理函数，签名应为 async def func(group_id, **kwargs) -> Dict
        """
        try:
            # 创建动态枚举值（如果不存在）
            custom_type = f"custom_{export_type}"
            self._exporters[custom_type] = exporter_func
            self._logger.info(f"注册自定义导出处理器: {export_type}")
        except Exception as e:
            self._logger.error(f"注册自定义导出处理器失败: {e}")

    async def export_data(
        self,
        data_type: str,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> StandardResponse:
        """
        通用数据导出接口

        Args:
            data_type: 数据类型（emotion, affection, learning_stats等）
            group_id: 群组ID（可选）
            user_id: 用户ID（可选）
            **kwargs: 其他参数，传递给具体的导出处理器

        Returns:
            StandardResponse: 标准响应格式的数据
        """
        try:
            # 查找对应的导出处理器
            exporter = None

            # 尝试匹配枚举类型
            for export_enum in DataExportType:
                if export_enum.value == data_type:
                    exporter = self._exporters.get(export_enum)
                    break

            # 尝试匹配自定义类型
            if not exporter:
                custom_key = f"custom_{data_type}"
                exporter = self._exporters.get(custom_key)

            if not exporter:
                return StandardResponse(
                    success=False,
                    timestamp=time.time(),
                    data_type=data_type,
                    group_id=group_id,
                    user_id=user_id,
                    data=None,
                    metadata=None,
                    message=None,
                    error=f"不支持的数据类型: {data_type}"
                )

            # 调用导出处理器
            result_data = await exporter(
                group_id=group_id,
                user_id=user_id,
                **kwargs
            )

            return StandardResponse(
                success=True,
                timestamp=time.time(),
                data_type=data_type,
                group_id=group_id,
                user_id=user_id,
                data=result_data.get('data'),
                metadata=result_data.get('metadata'),
                message="数据导出成功",
                error=None
            )

        except Exception as e:
            self._logger.error(f"导出数据失败 (type={data_type}, group={group_id}): {e}", exc_info=True)
            return StandardResponse(
                success=False,
                timestamp=time.time(),
                data_type=data_type,
                group_id=group_id,
                user_id=user_id,
                data=None,
                metadata=None,
                message=None,
                error=f"数据导出失败: {str(e)}"
            )

    # ==================== 内置导出处理器 ====================

    def _format_timestamp(self, timestamp: float) -> str:
        """格式化时间戳为ISO 8601格式"""
        return datetime.fromtimestamp(timestamp).isoformat()

    async def _export_emotion_data(
        self,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """导出情绪数据"""
        if not self.affection_manager:
            return {"data": None, "metadata": {"error": "好感度管理器未初始化"}}

        if not group_id:
            return {"data": None, "metadata": {"error": "需要提供群组ID"}}

        emotion_data = await self.get_current_emotion(group_id)

        return {
            "data": asdict(emotion_data) if emotion_data else None,
            "metadata": {
                "has_active_emotion": emotion_data is not None if emotion_data else False
            }
        }

    async def _export_affection_data(
        self,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """导出好感度数据"""
        if not group_id:
            return {"data": None, "metadata": {"error": "需要提供群组ID"}}

        limit = kwargs.get('limit', 100)

        # 如果指定了用户ID，只返回该用户的数据
        if user_id:
            user_affection = await self.db_manager.get_user_affection(group_id, user_id)
            return {
                "data": {
                    "user_affection": user_affection,
                    "interaction_history": await self._get_user_interaction_history(group_id, user_id, limit=10)
                },
                "metadata": {"query_type": "single_user"}
            }

        # 否则返回所有用户的数据
        affection_list = await self.get_user_affections(group_id, limit)
        group_summary = await self.get_group_affection_summary(group_id)

        return {
            "data": {
                "user_affections": [asdict(a) for a in affection_list],
                "group_summary": asdict(group_summary) if group_summary else None
            },
            "metadata": {
                "total_users": len(affection_list),
                "query_type": "group_level"
            }
        }

    async def _export_learning_stats(
        self,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """导出学习统计数据"""
        try:
            stats = {}

            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 获取消息统计
                if group_id:
                    await cursor.execute('''
                        SELECT COUNT(*) as total,
                               COUNT(DISTINCT sender_id) as unique_users
                        FROM raw_messages
                        WHERE group_id = ?
                    ''', (group_id,))
                else:
                    await cursor.execute('''
                        SELECT COUNT(*) as total,
                               COUNT(DISTINCT sender_id) as unique_users
                        FROM raw_messages
                    ''')

                row = await cursor.fetchone()
                stats['total_messages'] = row[0] if row else 0
                stats['unique_users'] = row[1] if row else 0

                # 获取学习会话统计
                await cursor.execute('''
                    SELECT COUNT(*) as session_count
                    FROM learning_sessions
                ''' + (' WHERE group_id = ?' if group_id else ''), (group_id,) if group_id else ())

                row = await cursor.fetchone()
                stats['learning_sessions'] = row[0] if row else 0

                await cursor.close()

            return {"data": stats, "metadata": {"data_source": "database"}}

        except Exception as e:
            self._logger.error(f"导出学习统计失败: {e}")
            return {"data": None, "metadata": {"error": str(e)}}

    async def _export_style_patterns(
        self,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """导出风格模式数据"""
        # 这里可以根据实际需求扩展
        return {"data": {"message": "风格模式导出功能待实现"}, "metadata": {}}

    async def _export_social_relations(
        self,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """导出社交关系数据"""
        # 这里可以根据实际需求扩展
        return {"data": {"message": "社交关系导出功能待实现"}, "metadata": {}}

    async def _export_message_stats(
        self,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """导出消息统计数据"""
        # 这里可以根据实际需求扩展
        return {"data": {"message": "消息统计导出功能待实现"}, "metadata": {}}

    async def _export_comprehensive_data(
        self,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """导出综合数据（包含所有类型）"""
        comprehensive = {
            "emotion": await self._export_emotion_data(group_id, user_id, **kwargs),
            "affection": await self._export_affection_data(group_id, user_id, **kwargs),
            "learning_stats": await self._export_learning_stats(group_id, user_id, **kwargs)
        }

        return {
            "data": comprehensive,
            "metadata": {
                "included_types": ["emotion", "affection", "learning_stats"],
                "comprehensive_export": True
            }
        }

    # ==================== 辅助方法（保持原有实现）====================
        """获取当前群组的情绪状态"""
        try:
            current_mood = await self.affection_manager.get_current_mood(group_id)

            if not current_mood or not current_mood.is_active():
                self._logger.debug(f"群组 {group_id} 没有活跃的情绪状态")
                return None

            return EmotionData(
                group_id=group_id,
                mood_type=current_mood.mood_type.value,
                mood_intensity=current_mood.intensity,
                mood_description=current_mood.description,
                start_time=current_mood.start_time,
                end_time=current_mood.start_time + current_mood.duration_hours * 3600,
                is_active=current_mood.is_active(),
                created_at=self._format_timestamp(current_mood.start_time)
            )

        except Exception as e:
            self._logger.error(f"获取群组 {group_id} 情绪状态失败: {e}")
            return None

    async def get_user_affections(self, group_id: str, limit: int = 100) -> List[UserAffectionData]:
        """获取群组内用户好感度列表"""
        try:
            affection_list = []

            # 从数据库获取用户好感度数据
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                await cursor.execute('''
                    SELECT
                        user_id,
                        group_id,
                        affection_level,
                        last_interaction,
                        interaction_count,
                        last_updated,
                        created_at
                    FROM user_affection
                    WHERE group_id = ?
                    ORDER BY affection_level DESC
                    LIMIT ?
                ''', (group_id, limit))

                rows = await cursor.fetchall()

                for row in rows:
                    affection_list.append(UserAffectionData(
                        user_id=row[0],
                        group_id=row[1],
                        affection_level=row[2],
                        last_interaction=row[3],
                        interaction_count=row[4],
                        last_updated=row[5],
                        created_at=row[6]
                    ))

                await cursor.close()

            return affection_list

        except Exception as e:
            self._logger.error(f"获取群组 {group_id} 用户好感度列表失败: {e}")
            return []

    async def get_group_affection_summary(self, group_id: str) -> Optional[GroupAffectionSummary]:
        """获取群组好感度汇总信息"""
        try:
            # 使用affection_manager获取汇总数据
            affection_status = await self.affection_manager.get_affection_status(group_id)

            if not affection_status:
                return None

            return GroupAffectionSummary(
                group_id=group_id,
                total_affection=affection_status['total_affection'],
                max_total_affection=affection_status['max_total_affection'],
                user_count=affection_status['user_count'],
                avg_affection=affection_status['avg_affection'],
                top_users=affection_status['top_users'][:5],  # 前5名
                last_updated=time.time()
            )

        except Exception as e:
            self._logger.error(f"获取群组 {group_id} 好感度汇总失败: {e}")
            return None

    async def format_emotion_affection_data(
        self,
        group_id: str,
        include_emotion: bool = True,
        include_affection: bool = True,
        include_summary: bool = True
    ) -> EmotionAffectionResponse:
        """
        格式化情绪和好感度数据为标准JSON响应

        Args:
            group_id: 群组ID
            include_emotion: 是否包含情绪数据
            include_affection: 是否包含用户好感度数据
            include_summary: 是否包含群组汇总数据

        Returns:
            EmotionAffectionResponse: 标准化响应数据
        """
        try:
            current_emotion = None
            user_affections = []
            group_summary = None

            # 获取当前情绪
            if include_emotion:
                emotion_data = await self.get_current_emotion(group_id)
                if emotion_data:
                    current_emotion = asdict(emotion_data)

            # 获取用户好感度列表
            if include_affection:
                affection_list = await self.get_user_affections(group_id)
                user_affections = [asdict(affection) for affection in affection_list]

            # 获取群组汇总
            if include_summary:
                summary_data = await self.get_group_affection_summary(group_id)
                if summary_data:
                    group_summary = asdict(summary_data)

            return EmotionAffectionResponse(
                success=True,
                timestamp=time.time(),
                group_id=group_id,
                current_emotion=current_emotion,
                user_affections=user_affections,
                group_summary=group_summary,
                message="数据获取成功",
                error=None
            )

        except Exception as e:
            self._logger.error(f"格式化群组 {group_id} 数据失败: {e}", exc_info=True)
            return EmotionAffectionResponse(
                success=False,
                timestamp=time.time(),
                group_id=group_id,
                current_emotion=None,
                user_affections=[],
                group_summary=None,
                message=None,
                error=f"数据获取失败: {str(e)}"
            )

    async def get_all_groups_emotion_affection(self) -> Dict[str, Any]:
        """获取所有活跃群组的情绪和好感度数据"""
        try:
            # 获取所有活跃群组
            active_groups = await self._get_active_groups()

            groups_data = []
            for group_id in active_groups:
                group_data = await self.format_emotion_affection_data(
                    group_id,
                    include_emotion=True,
                    include_affection=True,
                    include_summary=True
                )
                groups_data.append(asdict(group_data))

            return {
                "success": True,
                "timestamp": time.time(),
                "total_groups": len(groups_data),
                "groups": groups_data,
                "message": "所有群组数据获取成功",
                "error": None
            }

        except Exception as e:
            self._logger.error(f"获取所有群组数据失败: {e}", exc_info=True)
            return {
                "success": False,
                "timestamp": time.time(),
                "total_groups": 0,
                "groups": [],
                "message": None,
                "error": f"数据获取失败: {str(e)}"
            }

    async def _get_active_groups(self) -> List[str]:
        """获取所有活跃群组ID列表"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 获取最近7天内有消息的群组
                cutoff_time = time.time() - (86400 * 7)
                await cursor.execute('''
                    SELECT DISTINCT group_id
                    FROM raw_messages
                    WHERE timestamp > ? AND group_id IS NOT NULL AND group_id != ''
                    ORDER BY timestamp DESC
                ''', (cutoff_time,))

                rows = await cursor.fetchall()
                await cursor.close()

                return [row[0] for row in rows]

        except Exception as e:
            self._logger.error(f"获取活跃群组列表失败: {e}")
            return []

    async def get_user_emotion_affection(
        self,
        group_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """获取指定用户在指定群组的情绪和好感度数据"""
        try:
            # 获取群组情绪
            emotion_data = await self.get_current_emotion(group_id)

            # 获取用户好感度
            user_affection = await self.db_manager.get_user_affection(group_id, user_id)

            # 获取用户最近的交互历史
            interaction_history = await self._get_user_interaction_history(
                group_id, user_id, limit=10
            )

            return {
                "success": True,
                "timestamp": time.time(),
                "group_id": group_id,
                "user_id": user_id,
                "current_emotion": asdict(emotion_data) if emotion_data else None,
                "user_affection": user_affection,
                "interaction_history": interaction_history,
                "message": "用户数据获取成功",
                "error": None
            }

        except Exception as e:
            self._logger.error(f"获取用户 {user_id} 在群组 {group_id} 的数据失败: {e}")
            return {
                "success": False,
                "timestamp": time.time(),
                "group_id": group_id,
                "user_id": user_id,
                "current_emotion": None,
                "user_affection": None,
                "interaction_history": [],
                "message": None,
                "error": f"数据获取失败: {str(e)}"
            }

    async def _get_user_interaction_history(
        self,
        group_id: str,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取用户交互历史记录"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                await cursor.execute('''
                    SELECT
                        change_amount,
                        previous_level,
                        new_level,
                        change_reason,
                        bot_mood,
                        timestamp,
                        created_at
                    FROM affection_history
                    WHERE group_id = ? AND user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (group_id, user_id, limit))

                rows = await cursor.fetchall()
                await cursor.close()

                history = []
                for row in rows:
                    history.append({
                        "change_amount": row[0],
                        "previous_level": row[1],
                        "new_level": row[2],
                        "change_reason": row[3],
                        "bot_mood": row[4],
                        "timestamp": row[5],
                        "created_at": row[6]
                    })

                return history

        except Exception as e:
            self._logger.error(f"获取用户 {user_id} 交互历史失败: {e}")
            return []
