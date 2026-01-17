-- =====================================================
-- 传统表（未迁移到 ORM 的表）
-- =====================================================

-- 选择数据库
USE bot_db_migrated;

-- ===================================================
-- 学习批次表（如果已存在则确保结构正确）
-- ===================================================
-- 先创建表（如果不存在）
CREATE TABLE IF NOT EXISTS learning_batches (
    id INT PRIMARY KEY AUTO_INCREMENT,
    batch_id VARCHAR(255) UNIQUE,
    batch_name VARCHAR(255) NOT NULL,
    group_id VARCHAR(255) NOT NULL,
    start_time DOUBLE NOT NULL,
    end_time DOUBLE,
    quality_score DOUBLE,
    processed_messages INT DEFAULT 0,
    message_count INT DEFAULT 0,
    filtered_count INT DEFAULT 0,
    success BOOLEAN DEFAULT 1,
    error_message TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id),
    INDEX idx_batch_id (batch_id),
    INDEX idx_batch_name (batch_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 确保 batch_name 列存在（用于向后兼容）
-- 如果表已存在但缺少该列，则添加
SET @column_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_batches'
    AND COLUMN_NAME = 'batch_name');

SET @alter_sql = IF(@column_exists = 0,
    'ALTER TABLE learning_batches ADD COLUMN batch_name VARCHAR(255) NOT NULL AFTER batch_id',
    'SELECT "Column batch_name already exists"');

PREPARE stmt FROM @alter_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ===================================================
-- 其他传统表
-- ===================================================

-- 强化学习结果表
CREATE TABLE IF NOT EXISTS reinforcement_learning_results (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    timestamp DOUBLE NOT NULL,
    replay_analysis TEXT,
    optimization_strategy TEXT,
    reinforcement_feedback TEXT,
    next_action TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 策略优化结果表
CREATE TABLE IF NOT EXISTS strategy_optimization_results (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    timestamp DOUBLE NOT NULL,
    exploration_type VARCHAR(100),
    effectiveness_score DOUBLE,
    detailed_metrics TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 人格融合历史表
CREATE TABLE IF NOT EXISTS persona_fusion_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    timestamp DOUBLE NOT NULL,
    base_persona_hash BIGINT,
    incremental_hash BIGINT,
    fusion_result TEXT,
    compatibility_score DOUBLE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 学习会话表
CREATE TABLE IF NOT EXISTS learning_sessions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    group_id VARCHAR(255) NOT NULL,
    batch_id VARCHAR(255),
    start_time DOUBLE NOT NULL,
    end_time DOUBLE,
    metrics TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id),
    INDEX idx_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 人格备份表
CREATE TABLE IF NOT EXISTS persona_backups (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    backup_time DOUBLE NOT NULL,
    persona_content TEXT NOT NULL,
    persona_hash BIGINT,
    backup_reason VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 人格更新记录表
CREATE TABLE IF NOT EXISTS persona_update_records (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    update_time DOUBLE NOT NULL,
    old_persona_hash BIGINT,
    new_persona_hash BIGINT,
    update_type VARCHAR(50),
    update_content TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Bot 心情表
CREATE TABLE IF NOT EXISTS bot_mood (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    mood_type VARCHAR(50) NOT NULL,
    intensity DOUBLE DEFAULT 0.5,
    trigger_event TEXT,
    timestamp DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 对话上下文表
CREATE TABLE IF NOT EXISTS conversation_contexts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    context_data TEXT,
    last_update DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 情感模式表
CREATE TABLE IF NOT EXISTS emotion_patterns (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    pattern_type VARCHAR(100),
    pattern_data TEXT,
    confidence DOUBLE DEFAULT 0.5,
    last_updated DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 情感档案表
CREATE TABLE IF NOT EXISTS emotion_profiles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    emotion_data TEXT,
    last_updated DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group_user (group_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 知识实体表
CREATE TABLE IF NOT EXISTS knowledge_entities (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    entity_type VARCHAR(100),
    entity_name VARCHAR(255),
    entity_data TEXT,
    confidence DOUBLE DEFAULT 0.5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 语言风格模式表
CREATE TABLE IF NOT EXISTS language_style_patterns (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    pattern_type VARCHAR(100),
    pattern_content TEXT,
    frequency INT DEFAULT 0,
    last_used DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 风格档案表
CREATE TABLE IF NOT EXISTS style_profiles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    style_data TEXT,
    last_updated DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 主题偏好表
CREATE TABLE IF NOT EXISTS topic_preferences (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    topic VARCHAR(255),
    preference_score DOUBLE DEFAULT 0.5,
    last_updated DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 主题摘要表
CREATE TABLE IF NOT EXISTS topic_summaries (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    topic VARCHAR(255),
    summary_content TEXT,
    last_updated DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户偏好表
CREATE TABLE IF NOT EXISTS user_preferences (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    preference_data TEXT,
    last_updated DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group_user (group_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户档案表
CREATE TABLE IF NOT EXISTS user_profiles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    profile_data TEXT,
    last_updated DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group_user (group_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- LLM 调用统计表
CREATE TABLE IF NOT EXISTS llm_call_statistics (
    id INT PRIMARY KEY AUTO_INCREMENT,
    call_type VARCHAR(50),
    model_name VARCHAR(100),
    tokens_used INT,
    response_time DOUBLE,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    timestamp DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_call_type (call_type),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 风格学习记录表
CREATE TABLE IF NOT EXISTS style_learning_records (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    learning_type VARCHAR(100),
    learning_content TEXT,
    effectiveness DOUBLE DEFAULT 0.5,
    timestamp DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 好感度历史表
CREATE TABLE IF NOT EXISTS affection_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    old_affection INT,
    new_affection INT,
    change_reason VARCHAR(255),
    timestamp DOUBLE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_group_user (group_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
