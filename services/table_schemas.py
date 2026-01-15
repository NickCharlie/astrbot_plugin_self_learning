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
            # 原始消息表（匹配 ORM 模型 RawMessage）
            'raw_messages': (
                '''CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id TEXT NOT NULL,
                    sender_name TEXT,
                    message TEXT NOT NULL,
                    group_id TEXT,
                    timestamp INTEGER NOT NULL,
                    platform TEXT,
                    message_id TEXT,
                    reply_to TEXT,
                    created_at INTEGER NOT NULL,
                    processed INTEGER DEFAULT 0
                )''',
                '''CREATE TABLE IF NOT EXISTS raw_messages (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    sender_id VARCHAR(255) NOT NULL,
                    sender_name VARCHAR(255),
                    message TEXT NOT NULL,
                    group_id VARCHAR(255),
                    timestamp BIGINT NOT NULL,
                    platform VARCHAR(100),
                    message_id VARCHAR(255),
                    reply_to VARCHAR(255),
                    created_at BIGINT NOT NULL,
                    processed TINYINT DEFAULT 0,
                    INDEX idx_raw_timestamp (timestamp),
                    INDEX idx_raw_sender (sender_id),
                    INDEX idx_raw_processed (processed),
                    INDEX idx_raw_group (group_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 筛选后消息表（匹配 ORM 模型 FilteredMessage）
            'filtered_messages': (
                '''CREATE TABLE IF NOT EXISTS filtered_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_message_id INTEGER,
                    message TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    group_id TEXT,
                    timestamp INTEGER NOT NULL,
                    confidence REAL,
                    quality_scores TEXT,
                    filter_reason TEXT,
                    created_at INTEGER NOT NULL,
                    processed INTEGER DEFAULT 0
                )''',
                '''CREATE TABLE IF NOT EXISTS filtered_messages (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    raw_message_id INT,
                    message TEXT NOT NULL,
                    sender_id VARCHAR(255) NOT NULL,
                    group_id VARCHAR(255),
                    timestamp BIGINT NOT NULL,
                    confidence DOUBLE,
                    quality_scores TEXT,
                    filter_reason TEXT,
                    created_at BIGINT NOT NULL,
                    processed TINYINT DEFAULT 0,
                    INDEX idx_filtered_timestamp (timestamp),
                    INDEX idx_filtered_sender (sender_id),
                    INDEX idx_filtered_processed (processed),
                    INDEX idx_filtered_group (group_id)
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

            # 用户好感度表（匹配 ORM 模型 UserAffection）
            'user_affections': (
                '''CREATE TABLE IF NOT EXISTS user_affections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    affection_level INTEGER DEFAULT 0 NOT NULL,
                    max_affection INTEGER DEFAULT 100 NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(group_id, user_id)
                )''',
                '''CREATE TABLE IF NOT EXISTS user_affections (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    affection_level INT DEFAULT 0 NOT NULL,
                    max_affection INT DEFAULT 100 NOT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    UNIQUE KEY idx_group_user_affection (group_id, user_id),
                    INDEX idx_affection_group (group_id),
                    INDEX idx_affection_user (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 表达模式表（匹配 ORM 模型 ExpressionPattern）
            'expression_patterns': (
                '''CREATE TABLE IF NOT EXISTS expression_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    situation TEXT NOT NULL,
                    expression TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    last_active_time REAL NOT NULL,
                    create_time REAL NOT NULL
                )''',
                '''CREATE TABLE IF NOT EXISTS expression_patterns (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL,
                    situation TEXT NOT NULL,
                    expression TEXT NOT NULL,
                    weight DOUBLE NOT NULL DEFAULT 1.0,
                    last_active_time DOUBLE NOT NULL,
                    create_time DOUBLE NOT NULL,
                    INDEX idx_group_weight (group_id, weight),
                    INDEX idx_group_active (group_id, last_active_time)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 黑话表（匹配 ORM 模型 Jargon）
            'jargon': (
                '''CREATE TABLE IF NOT EXISTS jargon (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    raw_content TEXT,
                    meaning TEXT,
                    is_jargon INTEGER,
                    count INTEGER DEFAULT 1,
                    last_inference_count INTEGER DEFAULT 0,
                    is_complete INTEGER DEFAULT 0,
                    is_global INTEGER DEFAULT 0,
                    chat_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(content, chat_id)
                )''',
                '''CREATE TABLE IF NOT EXISTS jargon (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    content TEXT NOT NULL,
                    raw_content TEXT,
                    meaning TEXT,
                    is_jargon TINYINT,
                    count INT DEFAULT 1,
                    last_inference_count INT DEFAULT 0,
                    is_complete TINYINT DEFAULT 0,
                    is_global TINYINT DEFAULT 0,
                    chat_id VARCHAR(255) NOT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    UNIQUE KEY uk_content_chat (content(255), chat_id),
                    INDEX idx_jargon_content (content(255)),
                    INDEX idx_jargon_chat_id (chat_id),
                    INDEX idx_jargon_is_jargon (is_jargon)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # Bot消息表（匹配 ORM 模型 BotMessage）
            'bot_messages': (
                '''CREATE TABLE IF NOT EXISTS bot_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )''',
                '''CREATE TABLE IF NOT EXISTS bot_messages (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    timestamp BIGINT NOT NULL,
                    created_at BIGINT NOT NULL,
                    INDEX idx_bot_timestamp (timestamp),
                    INDEX idx_bot_group (group_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 人格学习审核表（匹配 ORM 模型 PersonaLearningReview）
            'persona_update_reviews': (
                '''CREATE TABLE IF NOT EXISTS persona_update_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    group_id TEXT NOT NULL,
                    update_type TEXT NOT NULL,
                    original_content TEXT,
                    new_content TEXT,
                    proposed_content TEXT,
                    confidence_score REAL,
                    reason TEXT,
                    status TEXT DEFAULT 'pending' NOT NULL,
                    reviewer_comment TEXT,
                    review_time REAL,
                    metadata TEXT
                )''',
                '''CREATE TABLE IF NOT EXISTS persona_update_reviews (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    timestamp DOUBLE NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    update_type VARCHAR(255) NOT NULL,
                    original_content TEXT,
                    new_content TEXT,
                    proposed_content TEXT,
                    confidence_score DOUBLE,
                    reason TEXT,
                    status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                    reviewer_comment TEXT,
                    review_time DOUBLE,
                    metadata TEXT,
                    INDEX idx_group_persona_review (group_id, status),
                    INDEX idx_persona_review_timestamp (timestamp),
                    INDEX idx_persona_review_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 风格学习审查表（匹配 ORM 模型 StyleLearningReview）
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
                    reviewer_comment TEXT,
                    review_time REAL,
                    created_at TEXT,
                    updated_at TEXT
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
                    reviewer_comment TEXT,
                    review_time DOUBLE,
                    created_at DATETIME,
                    updated_at DATETIME,
                    INDEX idx_status (status),
                    INDEX idx_group (group_id),
                    INDEX idx_timestamp (timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # ==================== 心理状态管理表 ====================

            # 心理状态组件表（匹配 ORM 模型 PsychologicalStateComponent）
            'psychological_state_components': (
                '''CREATE TABLE IF NOT EXISTS psychological_state_components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    composite_state_id INTEGER,
                    group_id TEXT NOT NULL,
                    state_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    state_type TEXT NOT NULL,
                    value REAL NOT NULL,
                    threshold REAL DEFAULT 0.3 NOT NULL,
                    description TEXT,
                    start_time INTEGER NOT NULL
                )''',
                '''CREATE TABLE IF NOT EXISTS psychological_state_components (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    composite_state_id INT,
                    group_id VARCHAR(255) NOT NULL,
                    state_id VARCHAR(255) NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    state_type VARCHAR(100) NOT NULL,
                    value DOUBLE NOT NULL,
                    threshold DOUBLE DEFAULT 0.3 NOT NULL,
                    description TEXT,
                    start_time BIGINT NOT NULL,
                    INDEX idx_psych_component_composite (composite_state_id),
                    INDEX idx_psych_component_state (state_id),
                    INDEX idx_psych_component_category (category),
                    INDEX idx_psych_component_group (group_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 复合心理状态表（匹配 ORM 模型 CompositePsychologicalState）
            'composite_psychological_states': (
                '''CREATE TABLE IF NOT EXISTS composite_psychological_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL UNIQUE,
                    state_id TEXT NOT NULL UNIQUE,
                    triggering_events TEXT,
                    context TEXT,
                    created_at INTEGER NOT NULL,
                    last_updated INTEGER NOT NULL
                )''',
                '''CREATE TABLE IF NOT EXISTS composite_psychological_states (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL UNIQUE,
                    state_id VARCHAR(255) NOT NULL UNIQUE,
                    triggering_events TEXT,
                    context TEXT,
                    created_at BIGINT NOT NULL,
                    last_updated BIGINT NOT NULL,
                    INDEX idx_psych_state_group (group_id),
                    INDEX idx_last_updated (last_updated)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 心理状态变化历史表（匹配 ORM 模型 PsychologicalStateHistory）
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
                    timestamp INTEGER NOT NULL
                )''',
                '''CREATE TABLE IF NOT EXISTS psychological_state_history (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id VARCHAR(255) NOT NULL,
                    state_id VARCHAR(255) NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    old_state_type VARCHAR(100),
                    new_state_type VARCHAR(100) NOT NULL,
                    old_value DOUBLE,
                    new_value DOUBLE NOT NULL,
                    change_reason TEXT,
                    timestamp BIGINT NOT NULL,
                    INDEX idx_psych_history_group (group_id),
                    INDEX idx_psych_history_timestamp (timestamp)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # ==================== 增强社交关系管理表 ====================

            # 用户社交关系组件表（匹配 ORM 模型 UserSocialRelationComponent）
            'user_social_relation_components': (
                '''CREATE TABLE IF NOT EXISTS user_social_relation_components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER,
                    from_user_id TEXT NOT NULL,
                    to_user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    value REAL NOT NULL,
                    frequency INTEGER DEFAULT 0 NOT NULL,
                    last_interaction INTEGER NOT NULL,
                    description TEXT,
                    tags TEXT,
                    created_at INTEGER NOT NULL
                )''',
                '''CREATE TABLE IF NOT EXISTS user_social_relation_components (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    profile_id INT,
                    from_user_id VARCHAR(255) NOT NULL,
                    to_user_id VARCHAR(255) NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    relation_type VARCHAR(100) NOT NULL,
                    value DOUBLE NOT NULL,
                    frequency INT DEFAULT 0 NOT NULL,
                    last_interaction BIGINT NOT NULL,
                    description TEXT,
                    tags TEXT,
                    created_at BIGINT NOT NULL,
                    INDEX idx_social_relation_profile (profile_id),
                    INDEX idx_social_relation_from_to (from_user_id, to_user_id, group_id),
                    INDEX idx_social_relation_type (relation_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 用户社交档案统计表（匹配 ORM 模型 UserSocialProfile）
            'user_social_profiles': (
                '''CREATE TABLE IF NOT EXISTS user_social_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    total_relations INTEGER DEFAULT 0 NOT NULL,
                    significant_relations INTEGER DEFAULT 0 NOT NULL,
                    dominant_relation_type TEXT,
                    created_at INTEGER NOT NULL,
                    last_updated INTEGER NOT NULL,
                    UNIQUE(user_id, group_id)
                )''',
                '''CREATE TABLE IF NOT EXISTS user_social_profiles (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    user_id VARCHAR(255) NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    total_relations INT DEFAULT 0 NOT NULL,
                    significant_relations INT DEFAULT 0 NOT NULL,
                    dominant_relation_type VARCHAR(100),
                    created_at BIGINT NOT NULL,
                    last_updated BIGINT NOT NULL,
                    UNIQUE KEY idx_social_profile_user_group (user_id, group_id),
                    INDEX idx_social_profile_group (group_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'''
            ),

            # 社交关系变化历史表（匹配 ORM 模型 SocialRelationHistory）
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
                    timestamp INTEGER NOT NULL
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
                    timestamp BIGINT NOT NULL,
                    INDEX idx_social_history_from_to (from_user_id, to_user_id, group_id),
                    INDEX idx_social_history_timestamp (timestamp)
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
