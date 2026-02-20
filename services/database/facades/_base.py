"""
Facade 基类 — 提供会话管理和通用工具方法
"""
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from astrbot.api import logger

from ....config import PluginConfig
from ....core.database.engine import DatabaseEngine


class BaseFacade:
    """领域 Facade 基类

    所有领域 Facade 继承此类，获得统一的会话管理能力。
    Facade 方法返回 Dict/List[Dict]，不向消费者暴露 ORM 对象。
    """

    def __init__(self, engine: DatabaseEngine, config: PluginConfig):
        self.engine = engine
        self.config = config
        self._logger = logger

    @asynccontextmanager
    async def get_session(self):
        """获取异步数据库会话（上下文管理器）"""
        session = self.engine.get_session()
        try:
            async with session:
                yield session
        finally:
            await session.close()

    @staticmethod
    def _row_to_dict(obj: Any, fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """将 ORM 对象转换为字典

        Args:
            obj: ORM 模型实例
            fields: 需要提取的字段列表。为 None 时使用 to_dict() 或 __table__.columns。

        Returns:
            Dict 表示的记录数据
        """
        if obj is None:
            return {}
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        if fields:
            return {f: getattr(obj, f, None) for f in fields}
        # 回退：从 SQLAlchemy column 列表提取
        if hasattr(obj, '__table__'):
            return {c.name: getattr(obj, c.name, None) for c in obj.__table__.columns}
        return {}

    @staticmethod
    def _to_float_ts(
        value: Union[None, int, float, str, datetime],
        default: Optional[float] = None,
    ) -> Optional[float]:
        """将各类时间表示统一转换为 float 时间戳

        支持 float/int 直通、ISO 8601 字符串、datetime 对象。
        调用方传入 default=time.time() 可在 value 为 None 时使用当前时间。

        Args:
            value: 原始时间值
            default: value 为 None 时的回退值

        Returns:
            UNIX 时间戳 (float)，或 None
        """
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, datetime):
            return value.timestamp()
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).timestamp()
            except (ValueError, TypeError):
                pass
            try:
                return float(value)
            except (ValueError, TypeError):
                pass
        return default
