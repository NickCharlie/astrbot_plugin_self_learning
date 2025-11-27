"""
Group数据库表管理辅助方法
确保group数据库中的表在访问前存在
"""
import aiosqlite
from astrbot.api import logger


async def ensure_group_table_exists(conn: aiosqlite.Connection, table_name: str) -> bool:
    """
    确保group数据库中的表存在，如果不存在则创建

    Args:
        conn: 数据库连接
        table_name: 表名

    Returns:
        bool: 表是否存在或创建成功
    """
    try:
        cursor = await conn.cursor()

        # 检查表是否存在
        await cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        result = await cursor.fetchone()

        if result:
            # 表已存在
            return True

        # 表不存在，根据表名创建
        logger.info(f"[GroupDB] 表 {table_name} 不存在，开始创建...")

        table_schemas = {
            'user_profiles': '''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    qq_id TEXT PRIMARY KEY,
                    qq_name TEXT,
                    nicknames TEXT,
                    activity_pattern TEXT,
                    communication_style TEXT,
                    topic_preferences TEXT,
                    emotional_tendency TEXT,
                    last_active REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''',
            'social_relations': '''
                CREATE TABLE IF NOT EXISTS social_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user TEXT NOT NULL,
                    to_user TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    strength REAL NOT NULL,
                    frequency INTEGER NOT NULL,
                    last_interaction REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(from_user, to_user, relation_type)
                )
            ''',
            'style_profiles': '''
                CREATE TABLE IF NOT EXISTS style_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_name TEXT NOT NULL,
                    vocabulary_richness REAL,
                    sentence_complexity REAL,
                    emotional_expression REAL,
                    interaction_tendency REAL,
                    topic_diversity REAL,
                    formality_level REAL,
                    creativity_score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''',
            'persona_backups': '''
                CREATE TABLE IF NOT EXISTS persona_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    reason TEXT,
                    persona_config TEXT,
                    original_persona TEXT,
                    imitation_dialogues TEXT,
                    backup_reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''',
        }

        if table_name not in table_schemas:
            logger.error(f"[GroupDB] 未知的表名: {table_name}")
            return False

        # 创建表
        await cursor.execute(table_schemas[table_name])
        await conn.commit()

        logger.info(f"[GroupDB] 表 {table_name} 创建成功")
        return True

    except Exception as e:
        logger.error(f"[GroupDB] 确保表 {table_name} 存在时出错: {e}", exc_info=True)
        return False
