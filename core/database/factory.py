"""
数据库工厂 - 根据配置创建对应的数据库后端
"""
from typing import Optional
from astrbot.api import logger

from .backend_interface import IDatabaseBackend, DatabaseConfig, DatabaseType
from .sqlite_backend import SQLiteBackend
from .mysql_backend import MySQLBackend


class DatabaseFactory:
    """数据库工厂类"""

    @staticmethod
    def create_backend(config: DatabaseConfig) -> Optional[IDatabaseBackend]:
        """
        根据配置创建数据库后端

        Args:
            config: 数据库配置

        Returns:
            数据库后端实例，失败返回None
        """
        try:
            # 验证配置
            valid, error = config.validate()
            if not valid:
                logger.error(f"[DatabaseFactory] 配置验证失败: {error}")
                return None

            # 根据类型创建后端
            if config.db_type == DatabaseType.SQLITE:
                logger.info(f"[DatabaseFactory] 创建SQLite后端: {config.sqlite_path}")
                return SQLiteBackend(config)
            elif config.db_type == DatabaseType.MYSQL:
                logger.info(f"[DatabaseFactory] 创建MySQL后端: {config.mysql_host}:{config.mysql_port}/{config.mysql_database}")
                return MySQLBackend(config)
            else:
                logger.error(f"[DatabaseFactory] 不支持的数据库类型: {config.db_type}")
                return None

        except Exception as e:
            logger.error(f"[DatabaseFactory] 创建数据库后端失败: {e}", exc_info=True)
            return None

    @staticmethod
    def create_from_dict(config_dict: dict) -> Optional[IDatabaseBackend]:
        """
        从字典配置创建数据库后端

        Args:
            config_dict: 配置字典

        Returns:
            数据库后端实例
        """
        try:
            # 解析数据库类型
            db_type_str = config_dict.get('db_type', 'sqlite')
            db_type = DatabaseType(db_type_str.lower())

            # 创建配置对象
            config = DatabaseConfig(
                db_type=db_type,
                sqlite_path=config_dict.get('sqlite_path'),
                mysql_host=config_dict.get('mysql_host'),
                mysql_port=config_dict.get('mysql_port', 3306),
                mysql_user=config_dict.get('mysql_user'),
                mysql_password=config_dict.get('mysql_password'),
                mysql_database=config_dict.get('mysql_database'),
                mysql_charset=config_dict.get('mysql_charset', 'utf8mb4'),
                max_connections=config_dict.get('max_connections', 10),
                min_connections=config_dict.get('min_connections', 2),
                connection_timeout=config_dict.get('connection_timeout', 30)
            )

            return DatabaseFactory.create_backend(config)

        except Exception as e:
            logger.error(f"[DatabaseFactory] 从字典创建后端失败: {e}", exc_info=True)
            return None
