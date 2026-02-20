"""
训练数据导出服务
将对话数据导出为标准的大模型微调格式 (JSONL)

设计原则:
1. 数据聚合: 关联用户消息和Bot回复,构建完整对话对
2. 格式标准化: 转换为OpenAI/Claude微调训练格式
3. 质量筛选: 可选的质量过滤机制
4. 批量导出: 支持按时间范围、群组、质量阈值等条件导出
"""
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from astrbot.api import logger
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.patterns import AsyncServiceBase
from ...models.orm.message import RawMessage, BotMessage, FilteredMessage
from ...repositories.base_repository import BaseRepository


class ConversationPair:
    """对话对数据结构"""

    def __init__(
        self,
        user_message: str,
        bot_response: str,
        user_id: str,
        group_id: str,
        user_timestamp: int,
        bot_timestamp: int,
        quality_score: Optional[float] = None,
        metadata: Optional[Dict] = None
    ):
        self.user_message = user_message
        self.bot_response = bot_response
        self.user_id = user_id
        self.group_id = group_id
        self.user_timestamp = user_timestamp
        self.bot_timestamp = bot_timestamp
        self.quality_score = quality_score
        self.metadata = metadata or {}

    def to_training_format(
        self,
        system_prompt: Optional[str] = None,
        include_metadata: bool = False
    ) -> Dict[str, Any]:
        """
        转换为训练格式

        Args:
            system_prompt: 系统提示词 (可选)
            include_metadata: 是否包含元数据

        Returns:
            标准训练格式的字典
        """
        messages = []

        # 添加system角色 (如果提供)
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        # 添加用户消息
        messages.append({
            "role": "user",
            "content": self.user_message
        })

        # 添加助手回复
        messages.append({
            "role": "assistant",
            "content": self.bot_response
        })

        result = {"messages": messages}

        # 可选: 添加元数据 (用于分析,不用于训练)
        if include_metadata:
            result["metadata"] = {
                "user_id": self.user_id,
                "group_id": self.group_id,
                "user_timestamp": self.user_timestamp,
                "bot_timestamp": self.bot_timestamp,
                "quality_score": self.quality_score,
                **self.metadata
            }

        return result


class TrainingDataExporter(AsyncServiceBase):
    """
    训练数据导出服务

    功能:
    1. 从数据库中提取对话对 (用户消息 + Bot回复)
    2. 按时间顺序关联消息
    3. 可选的质量筛选
    4. 导出为JSONL格式
    5. 支持从远程数据库导出
    """

    def __init__(self, database_manager, is_remote: bool = False):
        """
        初始化训练数据导出器

        Args:
            database_manager: SQLAlchemyDatabaseManager实例
            is_remote: 是否为远程数据库连接
        """
        super().__init__("training_data_exporter")
        self.db_manager = database_manager
        self.is_remote = is_remote

        # 配置参数
        self.max_time_gap_seconds = 300  # 用户消息和Bot回复的最大时间差 (5分钟)
        self.min_message_length = 2  # 最小消息长度
        self.max_message_length = 2000  # 最大消息长度

    @classmethod
    async def create_from_remote_db(
        cls,
        database_url: str,
        echo: bool = False
    ) -> 'TrainingDataExporter':
        """
        从远程数据库创建导出器 (工厂方法)

        Args:
            database_url: 远程数据库连接URL
                - MySQL: "mysql+aiomysql://user:pass@host:port/dbname"
                - PostgreSQL: "postgresql+asyncpg://user:pass@host:port/dbname"
            echo: 是否打印SQL语句 (调试用)

        Returns:
            TrainingDataExporter实例

        Examples:
            # MySQL云端数据库
            exporter = await TrainingDataExporter.create_from_remote_db(
                "mysql+aiomysql://user:password@云端IP:3306/database"
            )
            await exporter.start()

            # PostgreSQL云端数据库
            exporter = await TrainingDataExporter.create_from_remote_db(
                "postgresql+asyncpg://user:password@云端IP:5432/database"
            )
        """
        from ...core.database.engine import DatabaseEngine
        from ..database import SQLAlchemyDatabaseManager

        # 创建远程数据库引擎
        logger.info(f"连接远程数据库: {cls._mask_database_url(database_url)}")
        engine = DatabaseEngine(database_url, echo=echo)

        # 创建数据库管理器
        # 注意: 这里使用临时配置，因为远程数据库不需要完整的PluginConfig
        class RemoteDBConfig:
            """远程数据库临时配置"""
            def __init__(self, db_url):
                self.database_url = db_url
                self.enable_auto_migration = False  # 远程数据库不自动迁移

        config = RemoteDBConfig(database_url)
        db_manager = SQLAlchemyDatabaseManager.__new__(SQLAlchemyDatabaseManager)
        db_manager.config = config
        db_manager.engine = engine
        db_manager._logger = logger

        # 创建导出器
        exporter = cls(db_manager, is_remote=True)
        logger.info("✅ 远程数据库连接成功")

        return exporter

    @staticmethod
    def _mask_database_url(url: str) -> str:
        """隐藏数据库URL中的密码"""
        if '@' in url:
            parts = url.split('@')
            if ':' in parts[0]:
                prefix = parts[0].rsplit(':', 1)[0]
                return f"{prefix}:****@{parts[1]}"
        return url

    async def _do_start(self) -> bool:
        """启动服务"""
        self._logger.info("训练数据导出服务启动成功")
        return True

    async def _do_stop(self) -> bool:
        """停止服务"""
        return True

    async def extract_conversation_pairs(
        self,
        group_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        min_quality_score: Optional[float] = None,
        limit: Optional[int] = None
    ) -> List[ConversationPair]:
        """
        提取对话对

        Args:
            group_id: 群组ID (可选,不指定则提取所有群组)
            start_time: 开始时间戳 (毫秒,可选)
            end_time: 结束时间戳 (毫秒,可选)
            min_quality_score: 最小质量分数 (可选,0-1)
            limit: 最大返回数量 (可选)

        Returns:
            对话对列表
        """
        try:
            async with self.db_manager.get_session() as session:
                # 1. 查询用户消息
                user_messages = await self._fetch_user_messages(
                    session, group_id, start_time, end_time, min_quality_score
                )

                if not user_messages:
                    self._logger.info("未找到符合条件的用户消息")
                    return []

                self._logger.info(f"查询到 {len(user_messages)} 条用户消息")

                # 2. 查询Bot回复
                bot_responses = await self._fetch_bot_responses(
                    session, group_id, start_time, end_time
                )

                if not bot_responses:
                    self._logger.info("未找到符合条件的Bot回复")
                    return []

                self._logger.info(f"查询到 {len(bot_responses)} 条Bot回复")

                # 3. 关联消息对
                conversation_pairs = self._match_message_pairs(
                    user_messages, bot_responses
                )

                self._logger.info(f"成功匹配 {len(conversation_pairs)} 个对话对")

                # 4. 应用限制
                if limit and len(conversation_pairs) > limit:
                    conversation_pairs = conversation_pairs[:limit]

                return conversation_pairs

        except Exception as e:
            self._logger.error(f"提取对话对失败: {e}", exc_info=True)
            return []

    async def _fetch_user_messages(
        self,
        session: AsyncSession,
        group_id: Optional[str],
        start_time: Optional[int],
        end_time: Optional[int],
        min_quality_score: Optional[float]
    ) -> List[Tuple]:
        """
        查询用户消息

        Returns:
            (message_id, sender_id, group_id, message, timestamp, quality_score)
        """
        # 如果需要质量筛选,使用filtered_messages表
        if min_quality_score is not None:
            stmt = select(
                FilteredMessage.id,
                FilteredMessage.sender_id,
                FilteredMessage.group_id,
                FilteredMessage.message,
                FilteredMessage.timestamp,
                FilteredMessage.confidence
            ).where(
                and_(
                    FilteredMessage.confidence >= min_quality_score,
                    func.length(FilteredMessage.message) >= self.min_message_length,
                    func.length(FilteredMessage.message) <= self.max_message_length
                )
            )
        else:
            # 否则使用raw_messages表
            stmt = select(
                RawMessage.id,
                RawMessage.sender_id,
                RawMessage.group_id,
                RawMessage.message,
                RawMessage.timestamp
            ).where(
                and_(
                    func.length(RawMessage.message) >= self.min_message_length,
                    func.length(RawMessage.message) <= self.max_message_length
                )
            )

        # 添加过滤条件
        conditions = []

        if group_id:
            if min_quality_score is not None:
                conditions.append(FilteredMessage.group_id == group_id)
            else:
                conditions.append(RawMessage.group_id == group_id)

        if start_time:
            if min_quality_score is not None:
                conditions.append(FilteredMessage.timestamp >= start_time)
            else:
                conditions.append(RawMessage.timestamp >= start_time)

        if end_time:
            if min_quality_score is not None:
                conditions.append(FilteredMessage.timestamp <= end_time)
            else:
                conditions.append(RawMessage.timestamp <= end_time)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # 按时间排序
        if min_quality_score is not None:
            stmt = stmt.order_by(FilteredMessage.timestamp)
        else:
            stmt = stmt.order_by(RawMessage.timestamp)

        result = await session.execute(stmt)
        rows = result.fetchall()

        # 如果使用raw_messages,添加None作为quality_score
        if min_quality_score is None:
            rows = [(*row, None) for row in rows]

        return rows

    async def _fetch_bot_responses(
        self,
        session: AsyncSession,
        group_id: Optional[str],
        start_time: Optional[int],
        end_time: Optional[int]
    ) -> List[Tuple]:
        """
        查询Bot回复

        Returns:
            (message_id, group_id, message, timestamp)
        """
        stmt = select(
            BotMessage.id,
            BotMessage.group_id,
            BotMessage.message,
            BotMessage.timestamp
        ).where(
            and_(
                func.length(BotMessage.message) >= self.min_message_length,
                func.length(BotMessage.message) <= self.max_message_length
            )
        )

        # 添加过滤条件
        conditions = []

        if group_id:
            conditions.append(BotMessage.group_id == group_id)

        if start_time:
            conditions.append(BotMessage.timestamp >= start_time)

        if end_time:
            conditions.append(BotMessage.timestamp <= end_time)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # 按时间排序
        stmt = stmt.order_by(BotMessage.timestamp)

        result = await session.execute(stmt)
        return result.fetchall()

    def _match_message_pairs(
        self,
        user_messages: List[Tuple],
        bot_responses: List[Tuple]
    ) -> List[ConversationPair]:
        """
        关联用户消息和Bot回复

        匹配策略:
        1. 相同群组
        2. Bot回复时间在用户消息之后
        3. 时间差在max_time_gap_seconds内
        4. 选择时间差最小的Bot回复

        Args:
            user_messages: (id, sender_id, group_id, message, timestamp, quality_score)
            bot_responses: (id, group_id, message, timestamp)

        Returns:
            对话对列表
        """
        pairs = []
        used_bot_indices = set()

        # 将Bot回复按群组分组,提高匹配效率
        bot_by_group = {}
        for idx, (bot_id, group_id, message, timestamp) in enumerate(bot_responses):
            if group_id not in bot_by_group:
                bot_by_group[group_id] = []
            bot_by_group[group_id].append((idx, bot_id, message, timestamp))

        # 遍历用户消息,寻找匹配的Bot回复
        for user_id, sender_id, group_id, user_msg, user_ts, quality_score in user_messages:
            if group_id not in bot_by_group:
                continue

            # 查找该群组内,时间在用户消息之后的Bot回复
            best_match = None
            min_time_gap = float('inf')
            best_idx = None

            for idx, bot_id, bot_msg, bot_ts in bot_by_group[group_id]:
                # 跳过已使用的Bot回复
                if idx in used_bot_indices:
                    continue

                # Bot回复必须在用户消息之后
                if bot_ts < user_ts:
                    continue

                # 计算时间差 (毫秒转秒)
                time_gap = (bot_ts - user_ts) / 1000

                # 时间差必须在允许范围内
                if time_gap > self.max_time_gap_seconds:
                    break  # bot_responses已按时间排序,后续的都不符合

                # 选择时间差最小的
                if time_gap < min_time_gap:
                    min_time_gap = time_gap
                    best_match = (bot_id, bot_msg, bot_ts)
                    best_idx = idx

            # 找到匹配
            if best_match:
                bot_id, bot_msg, bot_ts = best_match
                used_bot_indices.add(best_idx)

                pair = ConversationPair(
                    user_message=user_msg,
                    bot_response=bot_msg,
                    user_id=sender_id,
                    group_id=group_id,
                    user_timestamp=user_ts,
                    bot_timestamp=bot_ts,
                    quality_score=quality_score,
                    metadata={
                        "time_gap_seconds": min_time_gap
                    }
                )
                pairs.append(pair)

        return pairs

    async def export_to_jsonl(
        self,
        output_path: str,
        group_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        min_quality_score: Optional[float] = None,
        limit: Optional[int] = None,
        system_prompt: Optional[str] = None,
        include_metadata: bool = False
    ) -> Dict[str, Any]:
        """
        导出训练数据为JSONL文件

        Args:
            output_path: 输出文件路径
            group_id: 群组ID (可选)
            start_time: 开始时间戳 (毫秒,可选)
            end_time: 结束时间戳 (毫秒,可选)
            min_quality_score: 最小质量分数 (可选,0-1)
            limit: 最大导出数量 (可选)
            system_prompt: 系统提示词 (可选)
            include_metadata: 是否包含元数据 (可选)

        Returns:
            导出结果统计
        """
        try:
            start_export_time = time.time()

            # 1. 提取对话对
            self._logger.info(f"开始提取对话对... (group={group_id}, limit={limit})")
            pairs = await self.extract_conversation_pairs(
                group_id=group_id,
                start_time=start_time,
                end_time=end_time,
                min_quality_score=min_quality_score,
                limit=limit
            )

            if not pairs:
                return {
                    "success": False,
                    "message": "未找到符合条件的对话对",
                    "total_pairs": 0,
                    "output_path": None
                }

            # 2. 创建输出目录
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # 3. 写入JSONL文件
            with open(output_file, 'w', encoding='utf-8') as f:
                for pair in pairs:
                    training_data = pair.to_training_format(
                        system_prompt=system_prompt,
                        include_metadata=include_metadata
                    )
                    f.write(json.dumps(training_data, ensure_ascii=False) + '\n')

            export_duration = time.time() - start_export_time

            self._logger.info(
                f"✅ 导出完成: {len(pairs)} 个对话对, "
                f"耗时 {export_duration:.2f}s, "
                f"文件: {output_path}"
            )

            return {
                "success": True,
                "message": "导出成功",
                "total_pairs": len(pairs),
                "output_path": str(output_file.absolute()),
                "duration_seconds": export_duration,
                "filters": {
                    "group_id": group_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "min_quality_score": min_quality_score,
                    "limit": limit
                }
            }

        except Exception as e:
            self._logger.error(f"导出训练数据失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"导出失败: {str(e)}",
                "total_pairs": 0,
                "output_path": None
            }

    async def export_by_date_range(
        self,
        output_dir: str,
        days_ago: int = 7,
        **export_kwargs
    ) -> Dict[str, Any]:
        """
        按日期范围导出 (便捷方法)

        Args:
            output_dir: 输出目录
            days_ago: 最近N天 (默认7天)
            **export_kwargs: 其他导出参数

        Returns:
            导出结果
        """
        end_time = int(time.time() * 1000)  # 当前时间 (毫秒)
        start_time = end_time - (days_ago * 24 * 60 * 60 * 1000)  # N天前

        # 生成文件名
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"training_data_{days_ago}days_{timestamp_str}.jsonl"
        output_path = str(Path(output_dir) / output_filename)

        return await self.export_to_jsonl(
            output_path=output_path,
            start_time=start_time,
            end_time=end_time,
            **export_kwargs
        )

    async def get_export_statistics(
        self,
        group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取可导出数据的统计信息

        Args:
            group_id: 群组ID (可选)

        Returns:
            统计信息
        """
        try:
            async with self.db_manager.get_session() as session:
                # 统计用户消息数
                user_stmt = select(func.count(RawMessage.id))
                if group_id:
                    user_stmt = user_stmt.where(RawMessage.group_id == group_id)

                user_result = await session.execute(user_stmt)
                total_user_messages = user_result.scalar()

                # 统计Bot回复数
                bot_stmt = select(func.count(BotMessage.id))
                if group_id:
                    bot_stmt = bot_stmt.where(BotMessage.group_id == group_id)

                bot_result = await session.execute(bot_stmt)
                total_bot_messages = bot_result.scalar()

                # 统计高质量消息数
                filtered_stmt = select(func.count(FilteredMessage.id))
                if group_id:
                    filtered_stmt = filtered_stmt.where(FilteredMessage.group_id == group_id)

                filtered_result = await session.execute(filtered_stmt)
                total_filtered_messages = filtered_result.scalar()

                return {
                    "total_user_messages": total_user_messages,
                    "total_bot_messages": total_bot_messages,
                    "total_filtered_messages": total_filtered_messages,
                    "estimated_max_pairs": min(total_user_messages, total_bot_messages),
                    "group_id": group_id
                }

        except Exception as e:
            self._logger.error(f"获取统计信息失败: {e}", exc_info=True)
            return {
                "total_user_messages": 0,
                "total_bot_messages": 0,
                "total_filtered_messages": 0,
                "estimated_max_pairs": 0,
                "error": str(e)
            }