-- =====================================================
-- AstrBot Self Learning Plugin - MySQL Schema
-- 从 SQLAlchemy ORM 模型自动生成
-- =====================================================

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS astrbot_self_learning DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE astrbot_self_learning;

-- 表: affection_interactions
DROP TABLE IF EXISTS `affection_interactions`;

CREATE TABLE affection_interactions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_affection_id INTEGER NOT NULL, 
	interaction_type VARCHAR(50) NOT NULL, 
	affection_delta INTEGER NOT NULL, 
	message_content TEXT, 
	timestamp BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_affection_id) REFERENCES user_affections (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: bot_messages
DROP TABLE IF EXISTS `bot_messages`;

CREATE TABLE bot_messages (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	message TEXT NOT NULL, 
	timestamp BIGINT NOT NULL, 
	created_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: composite_psychological_states
DROP TABLE IF EXISTS `composite_psychological_states`;

CREATE TABLE composite_psychological_states (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	state_id VARCHAR(255) NOT NULL, 
	triggering_events TEXT, 
	context TEXT, 
	created_at BIGINT NOT NULL, 
	last_updated BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (state_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: expression_patterns
DROP TABLE IF EXISTS `expression_patterns`;

CREATE TABLE expression_patterns (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	situation TEXT NOT NULL, 
	expression TEXT NOT NULL, 
	weight FLOAT NOT NULL, 
	last_active_time FLOAT NOT NULL, 
	create_time FLOAT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: filtered_messages
DROP TABLE IF EXISTS `filtered_messages`;

CREATE TABLE filtered_messages (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	raw_message_id INTEGER, 
	message TEXT NOT NULL, 
	sender_id VARCHAR(255) NOT NULL, 
	group_id VARCHAR(255), 
	timestamp BIGINT NOT NULL, 
	confidence FLOAT, 
	quality_scores TEXT, 
	filter_reason TEXT, 
	created_at BIGINT NOT NULL, 
	processed BOOL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: interaction_records
DROP TABLE IF EXISTS `interaction_records`;

CREATE TABLE interaction_records (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(100) NOT NULL, 
	user_id VARCHAR(100) NOT NULL, 
	interaction_type VARCHAR(50) NOT NULL, 
	content_preview VARCHAR(200), 
	timestamp BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: jargon
DROP TABLE IF EXISTS `jargon`;

CREATE TABLE jargon (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	content TEXT NOT NULL, 
	raw_content TEXT, 
	meaning TEXT, 
	is_jargon BOOL, 
	count INTEGER, 
	last_inference_count INTEGER, 
	is_complete BOOL, 
	is_global BOOL, 
	chat_id VARCHAR(255) NOT NULL, 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: learning_performance_history
DROP TABLE IF EXISTS `learning_performance_history`;

CREATE TABLE learning_performance_history (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	session_id VARCHAR(255), 
	timestamp BIGINT NOT NULL, 
	quality_score FLOAT, 
	learning_time FLOAT, 
	success BOOL, 
	successful_pattern TEXT, 
	failed_pattern TEXT, 
	created_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: memories
DROP TABLE IF EXISTS `memories`;

CREATE TABLE memories (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	user_id VARCHAR(255) NOT NULL, 
	content TEXT NOT NULL, 
	importance INTEGER NOT NULL, 
	memory_type VARCHAR(50), 
	created_at BIGINT NOT NULL, 
	last_accessed BIGINT NOT NULL, 
	access_count INTEGER NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: memory_embeddings
DROP TABLE IF EXISTS `memory_embeddings`;

CREATE TABLE memory_embeddings (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	memory_id INTEGER NOT NULL, 
	embedding_model VARCHAR(100) NOT NULL, 
	embedding_data TEXT NOT NULL, 
	created_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: memory_summaries
DROP TABLE IF EXISTS `memory_summaries`;

CREATE TABLE memory_summaries (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	user_id VARCHAR(255) NOT NULL, 
	summary_type VARCHAR(50) NOT NULL, 
	summary_content TEXT NOT NULL, 
	memory_count INTEGER, 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: persona_update_reviews
DROP TABLE IF EXISTS `persona_update_reviews`;

CREATE TABLE persona_update_reviews (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	timestamp FLOAT NOT NULL, 
	group_id VARCHAR(255) NOT NULL, 
	update_type VARCHAR(255) NOT NULL, 
	original_content TEXT, 
	new_content TEXT, 
	proposed_content TEXT, 
	confidence_score FLOAT, 
	reason TEXT, 
	status VARCHAR(50) NOT NULL, 
	reviewer_comment TEXT, 
	review_time FLOAT, 
	metadata TEXT, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: psychological_state_components
DROP TABLE IF EXISTS `psychological_state_components`;

CREATE TABLE psychological_state_components (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	composite_state_id INTEGER, 
	group_id VARCHAR(255) NOT NULL, 
	state_id VARCHAR(255) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	state_type VARCHAR(100) NOT NULL, 
	value FLOAT NOT NULL, 
	threshold FLOAT NOT NULL, 
	description TEXT, 
	start_time BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(composite_state_id) REFERENCES composite_psychological_states (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: psychological_state_history
DROP TABLE IF EXISTS `psychological_state_history`;

CREATE TABLE psychological_state_history (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	state_id VARCHAR(255) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	old_state_type VARCHAR(100), 
	new_state_type VARCHAR(100) NOT NULL, 
	old_value FLOAT, 
	new_value FLOAT NOT NULL, 
	change_reason TEXT, 
	timestamp BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: raw_messages
DROP TABLE IF EXISTS `raw_messages`;

CREATE TABLE raw_messages (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	sender_id VARCHAR(255) NOT NULL, 
	sender_name VARCHAR(255), 
	message TEXT NOT NULL, 
	group_id VARCHAR(255), 
	timestamp BIGINT NOT NULL, 
	platform VARCHAR(100), 
	message_id VARCHAR(255), 
	reply_to VARCHAR(255), 
	created_at BIGINT NOT NULL, 
	processed BOOL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: social_network_edges
DROP TABLE IF EXISTS `social_network_edges`;

CREATE TABLE social_network_edges (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	from_user_id VARCHAR(255) NOT NULL, 
	to_user_id VARCHAR(255) NOT NULL, 
	edge_type VARCHAR(50) NOT NULL, 
	weight FLOAT, 
	properties TEXT, 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: social_network_nodes
DROP TABLE IF EXISTS `social_network_nodes`;

CREATE TABLE social_network_nodes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	user_id VARCHAR(255) NOT NULL, 
	node_type VARCHAR(50), 
	display_name VARCHAR(255), 
	properties TEXT, 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: social_relation_analysis_results
DROP TABLE IF EXISTS `social_relation_analysis_results`;

CREATE TABLE social_relation_analysis_results (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	analysis_type VARCHAR(50) NOT NULL, 
	result_data TEXT NOT NULL, 
	created_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: social_relation_history
DROP TABLE IF EXISTS `social_relation_history`;

CREATE TABLE social_relation_history (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	from_user_id VARCHAR(255) NOT NULL, 
	to_user_id VARCHAR(255) NOT NULL, 
	group_id VARCHAR(255) NOT NULL, 
	relation_type VARCHAR(100) NOT NULL, 
	old_value FLOAT, 
	new_value FLOAT NOT NULL, 
	change_reason TEXT, 
	timestamp BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: social_relations
DROP TABLE IF EXISTS `social_relations`;

CREATE TABLE social_relations (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id VARCHAR(255), 
	from_user VARCHAR(255), 
	to_user VARCHAR(255), 
	group_id VARCHAR(255), 
	relation_type VARCHAR(100), 
	affection_score FLOAT, 
	interaction_count INTEGER, 
	strength FLOAT, 
	frequency INTEGER, 
	last_interaction FLOAT, 
	metadata TEXT, 
	created_at BIGINT, 
	updated_at BIGINT, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: style_learning_patterns
DROP TABLE IF EXISTS `style_learning_patterns`;

CREATE TABLE style_learning_patterns (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(100) NOT NULL, 
	pattern_type VARCHAR(50) NOT NULL, 
	pattern TEXT NOT NULL, 
	usage_count INTEGER, 
	confidence FLOAT, 
	last_used BIGINT, 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: style_learning_reviews
DROP TABLE IF EXISTS `style_learning_reviews`;

CREATE TABLE style_learning_reviews (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	type VARCHAR(100) NOT NULL, 
	group_id VARCHAR(255) NOT NULL, 
	timestamp FLOAT NOT NULL, 
	learned_patterns TEXT, 
	few_shots_content TEXT, 
	status VARCHAR(50), 
	description TEXT, 
	reviewer_comment TEXT, 
	review_time FLOAT, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: user_affections
DROP TABLE IF EXISTS `user_affections`;

CREATE TABLE user_affections (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	user_id VARCHAR(255) NOT NULL, 
	affection_level INTEGER NOT NULL, 
	max_affection INTEGER NOT NULL, 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: user_conversation_history
DROP TABLE IF EXISTS `user_conversation_history`;

CREATE TABLE user_conversation_history (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	user_id VARCHAR(255) NOT NULL, 
	`role` VARCHAR(20) NOT NULL, 
	content TEXT NOT NULL, 
	timestamp BIGINT NOT NULL, 
	turn_index INTEGER NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: user_diversity
DROP TABLE IF EXISTS `user_diversity`;

CREATE TABLE user_diversity (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	group_id VARCHAR(255) NOT NULL, 
	user_id VARCHAR(255) NOT NULL, 
	response_hash VARCHAR(64) NOT NULL, 
	response_preview VARCHAR(200), 
	timestamp BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: user_social_profiles
DROP TABLE IF EXISTS `user_social_profiles`;

CREATE TABLE user_social_profiles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id VARCHAR(255) NOT NULL, 
	group_id VARCHAR(255) NOT NULL, 
	total_relations INTEGER NOT NULL, 
	significant_relations INTEGER NOT NULL, 
	dominant_relation_type VARCHAR(100), 
	created_at BIGINT NOT NULL, 
	last_updated BIGINT NOT NULL, 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 表: user_social_relation_components
DROP TABLE IF EXISTS `user_social_relation_components`;

CREATE TABLE user_social_relation_components (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	profile_id INTEGER NOT NULL, 
	from_user_id VARCHAR(255) NOT NULL, 
	to_user_id VARCHAR(255) NOT NULL, 
	group_id VARCHAR(255) NOT NULL, 
	relation_type VARCHAR(100) NOT NULL, 
	value FLOAT NOT NULL, 
	frequency INTEGER NOT NULL, 
	last_interaction BIGINT NOT NULL, 
	description TEXT, 
	tags TEXT, 
	created_at BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(profile_id) REFERENCES user_social_profiles (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
