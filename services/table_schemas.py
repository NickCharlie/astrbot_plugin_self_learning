"""
数据库表结构定义
定义所有需要的表结构，支持SQLite和MySQL
"""
from typing import Dict, Tuple
from ..core.database.backend_interface import DatabaseType


class TableSchemas:
    """数据库表结构定义"""

    @staticmethod
    def get_all_table_schemas() -> Dict[str, Tuple[str, str]]:
        """
        获取所有表的DDL语句

        Returns:
            Dict[table_name, (sqlite_ddl, mysql_ddl)]
        """
        return {
            # 原始消息表
            'raw_messages': (
                '''CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id TEXT NOT NULL,
                    sender_name TEXT,
                    message TEXT NOT NULL,
                    group_id TEXT,
                    timestamp REAL NOT NULL,
                    platform TEXT,
                    message_id TEXT,
                    reply_to TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )''',
                '''CREATE TABLE IF NOT EXISTS raw_messages (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    sender_id VARCHAR(255) NOT NULL,
                    sender_name VARCHAR(255),
                    message TEXT NOT NULL,
                    group_id VARCHAR(255),
                    timestamp DOUBLE NOT NULL,
                    platform VARCHAR(100),
                    message_id VARCHAR(255),
                    reply_to VARCHAR(255),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_group_timestamp (group_id, timestamp),
                    INDEX idx_sender (sender_id),
                    INDEX idx_timestamp (timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 筛选后消息表
            'filtered_messages': (
                '''CREATE TABLE IF NOT EXISTS filtered_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    confidence REAL,
                    processed INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )''',
                '''CREATE TABLE IF NOT EXISTS filtered_messages (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    message TEXT NOT NULL,
                    sender_id VARCHAR(255) NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    timestamp DOUBLE NOT NULL,
                    confidence DOUBLE,
                    processed TINYINT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_group_processed (group_id, processed),
                    INDEX idx_timestamp (timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 社交关系表
            'social_relations': (
                '''CREATE TABLE IF NOT EXISTS social_relations (
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
                )''',
                '''CREATE TABLE IF NOT EXISTS social_relations (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    from_user VARCHAR(255) NOT NULL,
                    to_user VARCHAR(255) NOT NULL,
                    relation_type VARCHAR(100) NOT NULL,
                    strength DOUBLE NOT NULL,
                    frequency INT NOT NULL,
                    last_interaction DOUBLE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_from_to_type (from_user, to_user, relation_type),
                    INDEX idx_from_user (from_user),
                    INDEX idx_to_user (to_user),
                    INDEX idx_strength (strength)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 用户好感度表
            'user_affection': (
                '''CREATE TABLE IF NOT EXISTS user_affection (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    affection_level INTEGER DEFAULT 0,
                    last_interaction REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    interaction_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_id)
                )''',
                '''CREATE TABLE IF NOT EXISTS user_affection (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    user_id VARCHAR(255) NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    affection_level INT DEFAULT 0,
                    last_interaction DOUBLE NOT NULL,
                    last_updated DOUBLE NOT NULL,
                    interaction_count INT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_user_group (user_id, group_id),
                    INDEX idx_group (group_id),
                    INDEX idx_affection (affection_level)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # Bot情绪表
            'bot_moods': (
                '''CREATE TABLE IF NOT EXISTS bot_moods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL UNIQUE,
                    mood_type TEXT NOT NULL,
                    intensity REAL NOT NULL,
                    description TEXT,
                    start_time REAL NOT NULL,
                    duration_hours REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )''',
                '''CREATE TABLE IF NOT EXISTS bot_moods (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL UNIQUE,
                    mood_type VARCHAR(100) NOT NULL,
                    intensity DOUBLE NOT NULL,
                    description TEXT,
                    start_time DOUBLE NOT NULL,
                    duration_hours DOUBLE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_group (group_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 表达模式表
            'expression_patterns': (
                '''CREATE TABLE IF NOT EXISTS expression_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    situation TEXT NOT NULL,
                    expression TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    last_active_time REAL NOT NULL,
                    create_time REAL NOT NULL,
                    group_id TEXT NOT NULL,
                    UNIQUE(situation, expression, group_id)
                )''',
                '''CREATE TABLE IF NOT EXISTS expression_patterns (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    situation TEXT NOT NULL,
                    expression TEXT NOT NULL,
                    weight DOUBLE NOT NULL DEFAULT 1.0,
                    last_active_time DOUBLE NOT NULL,
                    create_time DOUBLE NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    UNIQUE KEY uk_situation_expression_group (situation(255), expression(255), group_id),
                    INDEX idx_group (group_id),
                    INDEX idx_weight (weight)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 黑话表
            'jargon': (
                '''CREATE TABLE IF NOT EXISTS jargon (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    jargon TEXT NOT NULL,
                    meaning TEXT NOT NULL,
                    context TEXT,
                    source_chat_id TEXT,
                    frequency INTEGER DEFAULT 1,
                    last_seen REAL,
                    is_jargon INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(jargon, source_chat_id)
                )''',
                '''CREATE TABLE IF NOT EXISTS jargon (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    jargon VARCHAR(255) NOT NULL,
                    meaning TEXT NOT NULL,
                    context TEXT,
                    source_chat_id VARCHAR(255),
                    frequency INT DEFAULT 1,
                    last_seen DOUBLE,
                    is_jargon TINYINT DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_jargon_chat (jargon, source_chat_id),
                    INDEX idx_chat (source_chat_id),
                    INDEX idx_is_jargon (is_jargon)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # Bot历史消息表
            'bot_history_messages': (
                '''CREATE TABLE IF NOT EXISTS bot_history_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )''',
                '''CREATE TABLE IF NOT EXISTS bot_history_messages (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    timestamp DOUBLE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_group_timestamp (group_id, timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 人格备份表
            'persona_backups': (
                '''CREATE TABLE IF NOT EXISTS persona_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    reason TEXT,
                    persona_config TEXT,
                    original_persona TEXT,
                    imitation_dialogues TEXT,
                    backup_reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )''',
                '''CREATE TABLE IF NOT EXISTS persona_backups (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    backup_name VARCHAR(255) NOT NULL,
                    timestamp DOUBLE NOT NULL,
                    reason TEXT,
                    persona_config TEXT,
                    original_persona TEXT,
                    imitation_dialogues TEXT,
                    backup_reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_timestamp (timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 风格学习审查表
            'style_learning_reviews': (
                '''CREATE TABLE IF NOT EXISTS style_learning_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    learned_patterns TEXT,
                    few_shots_content TEXT,
                    status TEXT DEFAULT 'pending',
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )''',
                '''CREATE TABLE IF NOT EXISTS style_learning_reviews (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    type VARCHAR(100) NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    timestamp DOUBLE NOT NULL,
                    learned_patterns TEXT,
                    few_shots_content TEXT,
                    status VARCHAR(50) DEFAULT 'pending',
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_group_status (group_id, status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # ==================== 心理状态管理表 ====================

            # 心理状态组件表 - 存储单个心理状态（情绪、认知等）
            'psychological_state_components': (
                '''CREATE TABLE IF NOT EXISTS psychological_state_components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    state_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    state_type TEXT NOT NULL,
                    value REAL NOT NULL,
                    threshold REAL DEFAULT 0.3,
                    description TEXT,
                    start_time REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )''',
                '''CREATE TABLE IF NOT EXISTS psychological_state_components (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL,
                    state_id VARCHAR(255) NOT NULL,
                    category VARCHAR(100) NOT NULL,
                    state_type VARCHAR(100) NOT NULL,
                    value DOUBLE NOT NULL,
                    threshold DOUBLE DEFAULT 0.3,
                    description TEXT,
                    start_time DOUBLE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_group_state (group_id, state_id),
                    INDEX idx_group_category (group_id, category),
                    INDEX idx_value (value)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 复合心理状态表 - 存储复合心理状态的元数据
            'composite_psychological_states': (
                '''CREATE TABLE IF NOT EXISTS composite_psychological_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    state_id TEXT NOT NULL UNIQUE,
                    triggering_events TEXT,
                    context TEXT,
                    created_at REAL NOT NULL,
                    last_updated REAL NOT NULL
                )''',
                '''CREATE TABLE IF NOT EXISTS composite_psychological_states (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL,
                    state_id VARCHAR(255) NOT NULL UNIQUE,
                    triggering_events TEXT,
                    context TEXT,
                    created_at DOUBLE NOT NULL,
                    last_updated DOUBLE NOT NULL,
                    INDEX idx_group (group_id),
                    INDEX idx_last_updated (last_updated)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 心理状态变化历史表
            'psychological_state_history': (
                '''CREATE TABLE IF NOT EXISTS psychological_state_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    state_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    old_state_type TEXT,
                    new_state_type TEXT NOT NULL,
                    old_value REAL,
                    new_value REAL NOT NULL,
                    change_reason TEXT,
                    timestamp REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )''',
                '''CREATE TABLE IF NOT EXISTS psychological_state_history (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL,
                    state_id VARCHAR(255) NOT NULL,
                    category VARCHAR(100) NOT NULL,
                    old_state_type VARCHAR(100),
                    new_state_type VARCHAR(100) NOT NULL,
                    old_value DOUBLE,
                    new_value DOUBLE NOT NULL,
                    change_reason TEXT,
                    timestamp DOUBLE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_group_timestamp (group_id, timestamp),
                    INDEX idx_state (state_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # ==================== 增强社交关系管理表 ====================

            # 用户社交关系组件表 - 存储单个关系类型及其数值
            'user_social_relation_components': (
                '''CREATE TABLE IF NOT EXISTS user_social_relation_components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id TEXT NOT NULL,
                    to_user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    value REAL NOT NULL,
                    frequency INTEGER DEFAULT 0,
                    last_interaction REAL NOT NULL,
                    description TEXT,
                    tags TEXT,
                    created_at REAL NOT NULL,
                    UNIQUE(from_user_id, to_user_id, group_id, relation_type)
                )''',
                '''CREATE TABLE IF NOT EXISTS user_social_relation_components (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    from_user_id VARCHAR(255) NOT NULL,
                    to_user_id VARCHAR(255) NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    relation_type VARCHAR(100) NOT NULL,
                    value DOUBLE NOT NULL,
                    frequency INT DEFAULT 0,
                    last_interaction DOUBLE NOT NULL,
                    description TEXT,
                    tags TEXT,
                    created_at DOUBLE NOT NULL,
                    UNIQUE KEY uk_from_to_group_type (from_user_id, to_user_id, group_id, relation_type),
                    INDEX idx_from_user_group (from_user_id, group_id),
                    INDEX idx_to_user_group (to_user_id, group_id),
                    INDEX idx_value (value)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 用户社交档案统计表
            'user_social_profiles': (
                '''CREATE TABLE IF NOT EXISTS user_social_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    total_relations INTEGER DEFAULT 0,
                    significant_relations INTEGER DEFAULT 0,
                    dominant_relation_type TEXT,
                    created_at REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    UNIQUE(user_id, group_id)
                )''',
                '''CREATE TABLE IF NOT EXISTS user_social_profiles (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    user_id VARCHAR(255) NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    total_relations INT DEFAULT 0,
                    significant_relations INT DEFAULT 0,
                    dominant_relation_type VARCHAR(100),
                    created_at DOUBLE NOT NULL,
                    last_updated DOUBLE NOT NULL,
                    UNIQUE KEY uk_user_group (user_id, group_id),
                    INDEX idx_group (group_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 社交关系变化历史表
            'social_relation_history': (
                '''CREATE TABLE IF NOT EXISTS social_relation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id TEXT NOT NULL,
                    to_user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    old_value REAL,
                    new_value REAL NOT NULL,
                    change_reason TEXT,
                    timestamp REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )''',
                '''CREATE TABLE IF NOT EXISTS social_relation_history (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    from_user_id VARCHAR(255) NOT NULL,
                    to_user_id VARCHAR(255) NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    relation_type VARCHAR(100) NOT NULL,
                    old_value DOUBLE,
                    new_value DOUBLE NOT NULL,
                    change_reason TEXT,
                    timestamp DOUBLE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_from_user_timestamp (from_user_id, timestamp),
                    INDEX idx_group_timestamp (group_id, timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),
        }

    @staticmethod
    def get_table_ddl(table_name: str, db_type: DatabaseType) -> str:
        """
        获取指定表的DDL语句

        Args:
            table_name: 表名
            db_type: 数据库类型

        Returns:
            DDL语句
        """
        schemas = TableSchemas.get_all_table_schemas()
        if table_name not in schemas:
            raise ValueError(f"Unknown table: {table_name}")

        sqlite_ddl, mysql_ddl = schemas[table_name]

        if db_type == DatabaseType.SQLITE:
            return sqlite_ddl
        elif db_type == DatabaseType.MYSQL:
            return mysql_ddl
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    @staticmethod
    def get_all_table_names() -> list:
        """获取所有表名"""
        return list(TableSchemas.get_all_table_schemas().keys())
