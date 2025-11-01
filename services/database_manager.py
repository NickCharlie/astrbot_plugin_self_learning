"""
数据库管理器 - 管理分群数据库和数据持久化
"""
import os
import json
import aiosqlite
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

from astrbot.api import logger

from ..config import PluginConfig

from ..exceptions import DataStorageError

from ..core.patterns import AsyncServiceBase


class DatabaseManager(AsyncServiceBase):
    """数据库管理器 - 管理分群数据库和全局消息数据库的数据持久化"""
    
    def __init__(self, config: PluginConfig, context=None):
        super().__init__("database_manager") # 调用基类构造函数
        self.config = config
        self.context = context
        self.group_db_connections: Dict[str, aiosqlite.Connection] = {}
        
        # 安全地构建路径
        if not config.data_dir:
            raise ValueError("config.data_dir 不能为空")
        
        self.group_data_dir = os.path.join(config.data_dir, "group_databases")
        self.messages_db_path = config.messages_db_path
        self.messages_db_connection: Optional[aiosqlite.Connection] = None
        
        # 确保数据目录存在
        os.makedirs(self.group_data_dir, exist_ok=True)
        
        self._logger.info("数据库管理器初始化完成") # 使用基类的logger

    async def _do_start(self) -> bool:
        """启动服务时初始化数据库"""
        try:
            await self._init_messages_database()
            self._logger.info("全局消息数据库初始化成功")
            return True
        except Exception as e:
            self._logger.error(f"全局消息数据库初始化失败: {e}", exc_info=True)
            return False

    async def _do_stop(self) -> bool:
        """停止服务时关闭所有数据库连接"""
        try:
            await self.close_all_connections()
            self._logger.info("所有数据库连接已关闭")
            return True
        except Exception as e:
            self._logger.error(f"关闭数据库连接失败: {e}", exc_info=True)
            return False

    async def close_all_connections(self):
        """关闭所有数据库连接"""
        try:
            # 关闭全局消息数据库连接
            if self.messages_db_connection:
                await self.messages_db_connection.close()
                self.messages_db_connection = None
                self._logger.info("全局消息数据库连接已关闭")
            
            # 关闭所有群组数据库连接
            for group_id, conn in list(self.group_db_connections.items()):
                try:
                    await conn.close()
                    self._logger.info(f"群组 {group_id} 数据库连接已关闭")
                except Exception as e:
                    self._logger.error(f"关闭群组 {group_id} 数据库连接失败: {e}")
            
            self.group_db_connections.clear()
            self._logger.info("所有数据库连接已关闭")
            
        except Exception as e:
            self._logger.error(f"关闭数据库连接过程中发生错误: {e}")
            raise

    async def _get_messages_db_connection(self) -> aiosqlite.Connection:
        """获取全局消息数据库连接"""
        if self.messages_db_connection is None:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.messages_db_path), exist_ok=True)
            self.messages_db_connection = await aiosqlite.connect(self.messages_db_path)
            # 首次连接时，确保数据库表被初始化
            await self._init_messages_database_tables(self.messages_db_connection)
        return self.messages_db_connection

    async def _init_messages_database(self):
        """
        此方法现在仅作为 _do_start 的入口，实际的表创建逻辑已移至 _init_messages_database_tables。
        """
        # 确保连接已建立并表已初始化
        await self._get_messages_db_connection()
        self._logger.info("全局消息数据库连接已建立并表已初始化。")

    async def _init_messages_database_tables(self, conn: aiosqlite.Connection):
        """初始化全局消息SQLite数据库的表结构"""
        cursor = await conn.cursor()
        
        try:
            # 创建原始消息表
            self._logger.info("尝试创建 raw_messages 表...")
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id TEXT NOT NULL,
                    sender_name TEXT,
                    message TEXT NOT NULL,
                    group_id TEXT,
                    platform TEXT,
                    timestamp REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processed BOOLEAN DEFAULT FALSE
                )
            ''')
            self._logger.info("raw_messages 表创建/检查完成。")
            await conn.commit() # 强制提交，确保表结构写入磁盘
            
            # 创建筛选后消息表
            self._logger.info("尝试创建 filtered_messages 表...")
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS filtered_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_message_id INTEGER,
                    message TEXT NOT NULL,
                    sender_id TEXT,
                    group_id TEXT,
                    confidence REAL,
                    filter_reason TEXT,
                    timestamp REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    used_for_learning BOOLEAN DEFAULT FALSE,
                    quality_scores TEXT, -- 新增字段，存储JSON字符串
                    FOREIGN KEY (raw_message_id) REFERENCES raw_messages (id)
                )
            ''')
            self._logger.info("filtered_messages 表创建/检查完成。")
            
            # 检查并添加 quality_scores 列（如果不存在）
            await cursor.execute("PRAGMA table_info(filtered_messages)")
            columns = [col[1] for col in await cursor.fetchall()]
            if 'quality_scores' not in columns:
                await cursor.execute("ALTER TABLE filtered_messages ADD COLUMN quality_scores TEXT")
                logger.info("已为 filtered_messages 表添加 quality_scores 列。")
            
            # 检查并添加 group_id 列（如果不存在）
            if 'group_id' not in columns:
                await cursor.execute("ALTER TABLE filtered_messages ADD COLUMN group_id TEXT")
                logger.info("已为 filtered_messages 表添加 group_id 列。")

            # 创建学习批次表
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS learning_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    quality_score REAL DEFAULT 0.5,
                    processed_messages INTEGER DEFAULT 0,
                    batch_name TEXT UNIQUE,
                    message_count INTEGER,
                    filtered_count INTEGER,
                    success BOOLEAN,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建人格更新记录表
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS persona_update_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    group_id TEXT NOT NULL,
                    update_type TEXT NOT NULL,
                    original_content TEXT,
                    new_content TEXT NOT NULL,
                    reason TEXT,
                    status TEXT DEFAULT 'pending',
                    reviewer_comment TEXT,
                    review_time REAL
                )
            ''')
            
            # 创建索引
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_raw_messages_timestamp ON raw_messages(timestamp)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_raw_messages_sender ON raw_messages(sender_id)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_raw_messages_processed ON raw_messages(processed)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_filtered_messages_confidence ON filtered_messages(confidence)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_filtered_messages_used ON filtered_messages(used_for_learning)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_persona_update_records_status ON persona_update_records(status)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_persona_update_records_group_id ON persona_update_records(group_id)')
            
            # 新增强化学习相关表
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS reinforcement_learning_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    replay_analysis TEXT,
                    optimization_strategy TEXT,
                    reinforcement_feedback TEXT,
                    next_action TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS persona_fusion_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    base_persona_hash INTEGER,
                    incremental_hash INTEGER,
                    fusion_result TEXT,
                    compatibility_score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy_optimization_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    original_strategy TEXT,
                    optimization_result TEXT,
                    expected_improvement TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS learning_performance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    session_id TEXT,
                    timestamp REAL NOT NULL,
                    quality_score REAL,
                    learning_time REAL,
                    success BOOLEAN,
                    successful_pattern TEXT,
                    failed_pattern TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 为强化学习表创建索引
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_reinforcement_learning_group ON reinforcement_learning_results(group_id)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_persona_fusion_group ON persona_fusion_history(group_id)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_strategy_optimization_group ON strategy_optimization_results(group_id)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_learning_performance_group ON learning_performance_history(group_id)')
            
            await conn.commit()
            logger.info("全局消息数据库初始化完成")
            
        except aiosqlite.Error as e:
            logger.error(f"全局消息数据库初始化失败: {e}", exc_info=True)
            # 尝试删除可能损坏的数据库文件，以便下次启动时重新创建
            if os.path.exists(self.messages_db_path):
                self._logger.warning(f"数据库初始化失败，尝试删除损坏的数据库文件: {self.messages_db_path}")
                try:
                    os.remove(self.messages_db_path)
                except OSError as ose:
                    self._logger.error(f"删除数据库文件失败: {ose}")
            raise DataStorageError(f"全局消息数据库初始化失败: {str(e)}")

    def get_group_db_path(self, group_id: str) -> str:
        """获取群数据库文件路径"""
        if not group_id:
            raise ValueError("group_id 不能为空")
        if not self.group_data_dir:
            raise ValueError("group_data_dir 未初始化")
        return os.path.join(self.group_data_dir, f"{group_id}_ID.db")

    async def get_group_connection(self, group_id: str) -> aiosqlite.Connection:
        """获取群数据库连接"""
        if group_id not in self.group_db_connections:
            db_path = self.get_group_db_path(group_id)
            conn = await aiosqlite.connect(db_path)
            await self._init_group_database(conn)
            self.group_db_connections[group_id] = conn
            logger.info(f"已创建群 {group_id} 的数据库连接")
        
        return self.group_db_connections[group_id]

    async def _init_group_database(self, conn: aiosqlite.Connection):
        """初始化群数据库表结构"""
        cursor = await conn.cursor()
        
        try:
            # 原始消息表 (群数据库中不再存储原始消息，由全局消息数据库统一管理)
            # 筛选消息表 (群数据库中不再存储筛选消息，由全局消息数据库统一管理)
            
            # 用户画像表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS user_profiles (
                    qq_id TEXT PRIMARY KEY,
                    qq_name TEXT,
                    nicknames TEXT, -- JSON格式存储
                    activity_pattern TEXT, -- JSON格式存储活动模式
                    communication_style TEXT, -- JSON格式存储沟通风格
                    topic_preferences TEXT, -- JSON格式存储话题偏好
                    emotional_tendency TEXT, -- JSON格式存储情感倾向
                    last_active REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 社交关系表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS social_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user TEXT NOT NULL,
                    to_user TEXT NOT NULL,
                    relation_type TEXT NOT NULL, -- mention, reply, frequent_interaction
                    strength REAL NOT NULL,
                    frequency INTEGER NOT NULL,
                    last_interaction REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(from_user, to_user, relation_type)
                )
            ''')
            
            # 风格档案表
            await cursor.execute(''' 
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
            ''')
            
            # 人格备份表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS persona_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    reason TEXT,
                    persona_config TEXT, -- JSON格式存储人格配置
                    original_persona TEXT, -- JSON格式存储
                    imitation_dialogues TEXT, -- JSON格式存储模仿对话
                    backup_reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 学习会话表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS learning_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    messages_processed INTEGER DEFAULT 0,
                    filtered_messages INTEGER DEFAULT 0,
                    style_updates INTEGER DEFAULT 0,
                    quality_score REAL DEFAULT 0.0,
                    success BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_social_relations_from_user ON social_relations(from_user)') 
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_social_relations_to_user ON social_relations(to_user)') 
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_active ON user_profiles(last_active)') 
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_style_profiles_name ON style_profiles(profile_name)')
            
            # 创建好感度表
            await cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS user_affection (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    affection_level INTEGER DEFAULT 0,
                    last_interaction REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    interaction_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_id)
                )
            ''')
            
            # 创建bot情绪表
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_mood (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    mood_type TEXT NOT NULL,
                    mood_intensity REAL DEFAULT 0.5,
                    mood_description TEXT,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建好感度变化记录表
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS affection_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    change_amount INTEGER NOT NULL,
                    previous_level INTEGER NOT NULL,
                    new_level INTEGER NOT NULL,
                    change_reason TEXT,
                    bot_mood TEXT,
                    timestamp REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await conn.commit() 
            logger.debug("群数据库表结构初始化完成") 
            
        except aiosqlite.Error as e: 
            logger.error(f"初始化群数据库失败: {e}", exc_info=True) 
            raise DataStorageError(f"初始化群数据库失败: {str(e)}")

    async def save_style_profile(self, group_id: str, profile_data: Dict[str, Any]):
        """保存风格档案到数据库"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()

        try:
            await cursor.execute('''
                INSERT OR REPLACE INTO style_profiles
                (profile_name, vocabulary_richness, sentence_complexity, emotional_expression,
                 interaction_tendency, topic_diversity, formality_level, creativity_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                profile_data['profile_name'],
                profile_data.get('vocabulary_richness'),
                profile_data.get('sentence_complexity'),
                profile_data.get('emotional_expression'),
                profile_data.get('interaction_tendency'),
                profile_data.get('topic_diversity'),
                profile_data.get('formality_level'),
                profile_data.get('creativity_score')
            ))
            await conn.commit()
            logger.debug(f"风格档案 '{profile_data['profile_name']}' 已保存到群 {group_id} 数据库。")
        except aiosqlite.Error as e:
            logger.error(f"保存风格档案失败: {e}", exc_info=True)
            raise DataStorageError(f"保存风格档案失败: {str(e)}")

    async def load_style_profile(self, group_id: str, profile_name: str) -> Optional[Dict[str, Any]]:
        """从数据库加载风格档案"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()

        try:
            await cursor.execute('''
                SELECT profile_name, vocabulary_richness, sentence_complexity, emotional_expression,
                       interaction_tendency, topic_diversity, formality_level, creativity_score
                FROM style_profiles WHERE profile_name = ?
            ''', (profile_name,))
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                'profile_name': row[0],
                'vocabulary_richness': row[1],
                'sentence_complexity': row[2],
                'emotional_expression': row[3],
                'interaction_tendency': row[4],
                'topic_diversity': row[5],
                'formality_level': row[6],
                'creativity_score': row[7]
            }
        except aiosqlite.Error as e:
            logger.error(f"加载风格档案失败: {e}", exc_info=True)
            return None

    async def save_user_profile(self, group_id: str, profile_data: Dict[str, Any]):
        """保存用户画像到数据库"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT OR REPLACE INTO user_profiles 
                (qq_id, qq_name, nicknames, activity_pattern, communication_style, 
                 topic_preferences, emotional_tendency, last_active, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                profile_data['qq_id'],
                profile_data.get('qq_name', ''),
                json.dumps(profile_data.get('nicknames', []), ensure_ascii=False),
                json.dumps(profile_data.get('activity_pattern', {}), ensure_ascii=False),
                json.dumps(profile_data.get('communication_style', {}), ensure_ascii=False),
                json.dumps(profile_data.get('topic_preferences', {}), ensure_ascii=False),
                json.dumps(profile_data.get('emotional_tendency', {}), ensure_ascii=False),
                profile_data.get('last_active', time.time()),  # 使用profile中的值或当前时间
                datetime.now().isoformat()
            ))
            
            await conn.commit()
            
        except aiosqlite.Error as e:
            logger.error(f"保存用户画像失败: {e}", exc_info=True)
            raise DataStorageError(f"保存用户画像失败: {str(e)}")

    async def load_user_profile(self, group_id: str, qq_id: str) -> Optional[Dict[str, Any]]:
        """从数据库加载用户画像"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT qq_id, qq_name, nicknames, activity_pattern, communication_style,
                       topic_preferences, emotional_tendency, last_active
                FROM user_profiles WHERE qq_id = ?
            ''', (qq_id,))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            return {
                'qq_id': row[0],
                'qq_name': row[1],
                'nicknames': json.loads(row[2]) if row[2] else [],
                'activity_pattern': json.loads(row[3]) if row[3] else {},
                'communication_style': json.loads(row[4]) if row[4] else {},
                'topic_preferences': json.loads(row[5]) if row[5] else {},
                'emotional_tendency': json.loads(row[6]) if row[6] else {},
                'last_active': row[7]
            }
            
        except aiosqlite.Error as e:
            logger.error(f"加载用户画像失败: {e}", exc_info=True)
            return None

    async def save_social_relation(self, group_id: str, relation_data: Dict[str, Any]):
        """保存社交关系到数据库"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute(''' 
                INSERT OR REPLACE INTO social_relations 
                (from_user, to_user, relation_type, strength, frequency, last_interaction, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                relation_data['from_user'],
                relation_data['to_user'],
                relation_data['relation_type'],
                relation_data['strength'],
                relation_data['frequency'],
                relation_data['last_interaction'],
                datetime.now().isoformat()
            ))
            
            await conn.commit()
            
        except aiosqlite.Error as e:
            logger.error(f"保存社交关系失败: {e}", exc_info=True)
            raise DataStorageError(f"保存社交关系失败: {str(e)}")

    async def save_raw_message(self, message_data: Dict[str, Any]) -> int:
        """
        将原始消息保存到全局消息数据库。
        """
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO raw_messages (sender_id, sender_name, message, group_id, platform, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                message_data.get('sender_id'),
                message_data.get('sender_name'),
                message_data.get('message'),
                message_data.get('group_id'),
                message_data.get('platform'),
                message_data.get('timestamp')
            ))
            
            message_id = cursor.lastrowid
            await conn.commit()
            logger.debug(f"原始消息已保存，ID: {message_id}")
            return message_id
            
        except aiosqlite.Error as e:
            logger.error(f"保存原始消息失败: {e}", exc_info=True)
            raise DataStorageError(f"保存原始消息失败: {str(e)}")

    async def get_unprocessed_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取未处理的原始消息
        
        Args:
            limit: 限制返回的消息数量
            
        Returns:
            未处理的消息列表
        """
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            if limit:
                await cursor.execute('''
                    SELECT id, sender_id, sender_name, message, group_id, platform, timestamp
                    FROM raw_messages 
                    WHERE processed = FALSE 
                    ORDER BY timestamp ASC 
                    LIMIT ?
                ''', (limit,))
            else:
                await cursor.execute('''
                    SELECT id, sender_id, sender_name, message, group_id, platform, timestamp
                    FROM raw_messages 
                    WHERE processed = FALSE 
                    ORDER BY timestamp ASC
                ''')
            
            messages = []
            for row in await cursor.fetchall():
                messages.append({
                    'id': row[0],
                    'sender_id': row[1],
                    'sender_name': row[2],
                    'message': row[3],
                    'group_id': row[4],
                    'platform': row[5],
                    'timestamp': row[6]
                })
            
            logger.debug(f"获取到 {len(messages)} 条未处理消息")
            return messages
            
        except aiosqlite.Error as e:
            logger.error(f"获取未处理消息失败: {e}", exc_info=True)
            raise DataStorageError(f"获取未处理消息失败: {str(e)}")

    async def mark_messages_processed(self, message_ids: List[int]) -> bool:
        """
        标记消息为已处理
        
        Args:
            message_ids: 消息ID列表
            
        Returns:
            是否成功标记
        """
        if not message_ids:
            return True
            
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            # 批量更新消息状态
            placeholders = ','.join(['?' for _ in message_ids])
            await cursor.execute(f'''
                UPDATE raw_messages 
                SET processed = TRUE 
                WHERE id IN ({placeholders})
            ''', message_ids)
            
            await conn.commit()
            logger.debug(f"已标记 {len(message_ids)} 条消息为已处理")
            return True
            
        except aiosqlite.Error as e:
            logger.error(f"标记消息处理状态失败: {e}", exc_info=True)
            raise DataStorageError(f"标记消息处理状态失败: {str(e)}")

    async def add_filtered_message(self, filtered_data: Dict[str, Any]) -> int:
        """
        添加筛选后的消息
        
        Args:
            filtered_data: 筛选后的消息数据
            
        Returns:
            筛选消息的ID
        """
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO filtered_messages 
                (raw_message_id, message, sender_id, confidence, filter_reason, timestamp, quality_scores, group_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                filtered_data.get('raw_message_id'),
                filtered_data.get('message'),
                filtered_data.get('sender_id'),
                filtered_data.get('confidence', 0.8),
                filtered_data.get('filter_reason', ''),
                filtered_data.get('timestamp', time.time()),
                json.dumps(filtered_data.get('quality_scores', {}), ensure_ascii=False),
                filtered_data.get('group_id')
            ))
            
            filtered_id = cursor.lastrowid
            await conn.commit()
            logger.debug(f"筛选消息已保存，ID: {filtered_id}")
            return filtered_id
            
        except aiosqlite.Error as e:
            logger.error(f"添加筛选消息失败: {e}", exc_info=True)
            raise DataStorageError(f"添加筛选消息失败: {str(e)}")

    async def get_filtered_messages_for_learning(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取用于学习的筛选消息
        
        Args:
            limit: 限制返回的消息数量
            
        Returns:
            筛选消息列表
        """
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            if limit:
                await cursor.execute('''
                    SELECT id, message, sender_id, confidence, quality_scores, timestamp, group_id
                    FROM filtered_messages 
                    WHERE used_for_learning = FALSE 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (limit,))
            else:
                await cursor.execute('''
                    SELECT id, message, sender_id, confidence, quality_scores, timestamp, group_id
                    FROM filtered_messages 
                    WHERE used_for_learning = FALSE 
                    ORDER BY timestamp DESC
                ''')
            
            messages = []
            for row in await cursor.fetchall():
                quality_scores = {}
                try:
                    if row[4]:  # quality_scores
                        quality_scores = json.loads(row[4])
                except (json.JSONDecodeError, TypeError):
                    pass
                
                messages.append({
                    'id': row[0],
                    'message': row[1],
                    'sender_id': row[2],
                    'confidence': row[3],
                    'quality_scores': quality_scores,
                    'timestamp': row[5],
                    'group_id': row[6]
                })
            
            return messages
            
        except aiosqlite.Error as e:
            logger.error(f"获取学习消息失败: {e}", exc_info=True)
            raise DataStorageError(f"获取学习消息失败: {str(e)}")

    async def get_recent_filtered_messages(self, group_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取指定群组最近的筛选消息
        
        Args:
            group_id: 群组ID
            limit: 消息数量限制
            
        Returns:
            筛选消息列表
        """
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT id, message, sender_id, confidence, quality_scores, timestamp
                FROM filtered_messages 
                WHERE group_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (group_id, limit))
            
            messages = []
            for row in await cursor.fetchall():
                quality_scores = {}
                try:
                    if row[4]:  # quality_scores
                        quality_scores = json.loads(row[4])
                except (json.JSONDecodeError, TypeError):
                    pass
                
                messages.append({
                    'id': row[0],
                    'message': row[1],
                    'sender_id': row[2],
                    'confidence': row[3],
                    'quality_scores': quality_scores,
                    'timestamp': row[5]
                })
            
            return messages
            
        except aiosqlite.Error as e:
            logger.error(f"获取最近筛选消息失败: {e}", exc_info=True)
            return []

    async def get_messages_statistics(self) -> Dict[str, Any]:
        """
        获取消息统计信息
        
        Returns:
            统计信息字典
        """
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            # 获取原始消息统计
            await cursor.execute('SELECT COUNT(*) FROM raw_messages')
            total_messages = (await cursor.fetchone())[0]
            
            await cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE processed = FALSE')
            unprocessed_messages = (await cursor.fetchone())[0]
            
            # 获取筛选消息统计
            await cursor.execute('SELECT COUNT(*) FROM filtered_messages')
            filtered_messages = (await cursor.fetchone())[0]
            
            await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE used_for_learning = FALSE')
            unused_filtered_messages = (await cursor.fetchone())[0]
            
            return {
                'total_messages': total_messages,
                'unprocessed_messages': unprocessed_messages,
                'filtered_messages': filtered_messages,
                'unused_filtered_messages': unused_filtered_messages,
                'raw_messages': total_messages  # 兼容旧接口
            }
            
        except aiosqlite.Error as e:
            logger.error(f"获取消息统计失败: {e}", exc_info=True)
            return {
                'total_messages': 0,
                'unprocessed_messages': 0,
                'filtered_messages': 0,
                'unused_filtered_messages': 0,
                'raw_messages': 0
            }

    async def get_group_messages_statistics(self, group_id: str) -> Dict[str, Any]:
        """
        获取指定群组的消息统计信息
        
        Args:
            group_id: 群组ID
            
        Returns:
            统计信息字典
        """
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            # 获取原始消息统计
            await cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE group_id = ?', (group_id,))
            total_messages = (await cursor.fetchone())[0]
            
            await cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE group_id = ? AND processed = FALSE', (group_id,))
            unprocessed_messages = (await cursor.fetchone())[0]
            
            # 获取筛选消息统计
            await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE group_id = ?', (group_id,))
            filtered_messages = (await cursor.fetchone())[0]
            
            await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE group_id = ? AND used_for_learning = FALSE', (group_id,))
            unused_filtered_messages = (await cursor.fetchone())[0]
            
            return {
                'total_messages': total_messages,
                'unprocessed_messages': unprocessed_messages,
                'filtered_messages': filtered_messages,
                'unused_filtered_messages': unused_filtered_messages,
                'raw_messages': total_messages  # 兼容旧接口
            }
            
        except aiosqlite.Error as e:
            logger.error(f"获取群组消息统计失败: {e}", exc_info=True)
            return {
                'total_messages': 0,
                'unprocessed_messages': 0,
                'filtered_messages': 0,
                'unused_filtered_messages': 0,
                'raw_messages': 0
            }

    async def load_social_graph(self, group_id: str) -> List[Dict[str, Any]]:
        """加载完整社交图谱"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT from_user, to_user, relation_type, strength, frequency, last_interaction
                FROM social_relations ORDER BY strength DESC
            ''')
            
            relations = []
            for row in await cursor.fetchall():
                relations.append({
                    'from_user': row[0],
                    'to_user': row[1],
                    'relation_type': row[2],
                    'strength': row[3],
                    'frequency': row[4],
                    'last_interaction': row[5]
                })
            
            return relations
            
        except aiosqlite.Error as e:
            self._logger.error(f"加载社交图谱失败: {e}", exc_info=True)
            return []

    async def get_messages_for_replay(self, group_id: str, days: int, limit: int) -> List[Dict[str, Any]]:
        """
        从全局消息数据库获取指定群组在过去一段时间内的原始消息，用于记忆重放。
        """
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            start_timestamp = time.time() - (days * 86400) # 转换为秒
            
            await cursor.execute('''
                SELECT id, sender_id, sender_name, message, group_id, platform, timestamp
                FROM raw_messages 
                WHERE group_id = ? AND timestamp > ?
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (group_id, start_timestamp, limit))
            
            messages = []
            for row in await cursor.fetchall():
                messages.append({
                    'id': row[0],
                    'sender_id': row[1],
                    'sender_name': row[2],
                    'message': row[3],
                    'group_id': row[4],
                    'platform': row[5],
                    'timestamp': row[6]
                })
            
            return messages
            
        except aiosqlite.Error as e:
            self._logger.error(f"获取记忆重放消息失败: {e}", exc_info=True)
            return []

    async def backup_persona(self, group_id: str, backup_data: Dict[str, Any]) -> int:
        """备份人格数据"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 获取当前时间戳
            current_timestamp = time.time()
            
            await cursor.execute(''' 
                INSERT INTO persona_backups (backup_name, timestamp, original_persona, imitation_dialogues, backup_reason)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                backup_data['backup_name'],
                current_timestamp,
                json.dumps(backup_data['original_persona'], ensure_ascii=False),
                json.dumps(backup_data.get('imitation_dialogues', []), ensure_ascii=False),
                backup_data.get('backup_reason', 'Auto backup before update')
            ))
            
            backup_id = cursor.lastrowid
            await conn.commit()
            
            logger.info(f"人格数据已备份，备份ID: {backup_id}")
            return backup_id
            
        except aiosqlite.Error as e:
            logger.error(f"备份人格数据失败: {e}", exc_info=True)
            raise DataStorageError(f"备份人格数据失败: {str(e)}")

    async def get_persona_backups(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的人格备份"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT id, backup_name, created_at FROM persona_backups 
                ORDER BY created_at DESC LIMIT ?
            ''', (limit,))
            
            backups = []
            for row in await cursor.fetchall():
                backups.append({
                    'id': row[0],
                    'backup_name': row[1],
                    'created_at': row[2]
                })
            
            return backups
            
        except aiosqlite.Error as e:
            logger.error(f"获取人格备份失败: {e}", exc_info=True)
            return []

    async def restore_persona(self, group_id: str, backup_id: int) -> Optional[Dict[str, Any]]:
        """从备份恢复人格数据"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT backup_name, original_persona, imitation_dialogues, backup_reason 
                FROM persona_backups WHERE id = ?
            ''', (backup_id,))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            return {
                'backup_name': row[0],
                'original_persona': json.loads(row[1]),
                'imitation_dialogues': json.loads(row[2]),
                'backup_reason': row[3]
            }
            
        except aiosqlite.Error as e:
            logger.error(f"恢复人格数据失败: {e}", exc_info=True)
            return None

    async def save_persona_update_record(self, record: Dict[str, Any]) -> int:
        """保存人格更新记录到数据库"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO persona_update_records (timestamp, group_id, update_type, original_content, new_content, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.get('timestamp', time.time()),
                record.get('group_id'),
                record.get('update_type'),
                record.get('original_content'),
                record.get('new_content'),
                record.get('reason'),
                record.get('status', 'pending')
            ))
            
            record_id = cursor.lastrowid
            await conn.commit()
            logger.debug(f"人格更新记录已保存，ID: {record_id}")
            return record_id
            
        except aiosqlite.Error as e:
            logger.error(f"保存人格更新记录失败: {e}", exc_info=True)
            raise DataStorageError(f"保存人格更新记录失败: {str(e)}")

    async def get_pending_persona_update_records(self) -> List[Dict[str, Any]]:
        """获取所有待审查的人格更新记录"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT id, timestamp, group_id, update_type, original_content, new_content, reason, status, reviewer_comment, review_time
                FROM persona_update_records
                WHERE status = 'pending'
                ORDER BY timestamp DESC
            ''')
            
            records = []
            for row in await cursor.fetchall():
                records.append({
                    'id': row[0],
                    'timestamp': row[1],
                    'group_id': row[2],
                    'update_type': row[3],
                    'original_content': row[4],
                    'new_content': row[5],
                    'reason': row[6],
                    'status': row[7],
                    'reviewer_comment': row[8],
                    'review_time': row[9]
                })
            return records
            
        except aiosqlite.Error as e:
            logger.error(f"获取待审查人格更新记录失败: {e}", exc_info=True)
            return []

    async def update_persona_update_record_status(self, record_id: int, status: str, reviewer_comment: Optional[str] = None) -> bool:
        """更新人格更新记录的状态"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            review_time = time.time()
            await cursor.execute('''
                UPDATE persona_update_records
                SET status = ?, reviewer_comment = ?, review_time = ?
                WHERE id = ?
            ''', (status, reviewer_comment, review_time, record_id))
            
            await conn.commit()
            logger.debug(f"人格更新记录 {record_id} 状态已更新为 {status}")
            return cursor.rowcount > 0
            
        except aiosqlite.Error as e:
            logger.error(f"更新人格更新记录状态失败: {e}", exc_info=True)
            raise DataStorageError(f"更新人格更新记录状态失败: {str(e)}")

    # ========== 高级功能数据库操作方法 ==========

    async def save_emotion_profile(self, group_id: str, user_id: str, profile_data: Dict[str, Any]) -> bool:
        """保存情感档案"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 检查是否已存在表，如果不存在则创建
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS emotion_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    dominant_emotions TEXT, -- JSON格式
                    emotion_patterns TEXT, -- JSON格式
                    empathy_level REAL DEFAULT 0.5,
                    emotional_stability REAL DEFAULT 0.5,
                    last_updated REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_id)
                )
            ''')
            
            await cursor.execute('''
                INSERT OR REPLACE INTO emotion_profiles 
                (user_id, group_id, dominant_emotions, emotion_patterns, empathy_level, emotional_stability, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                group_id,
                json.dumps(profile_data.get('dominant_emotions', {}), ensure_ascii=False),
                json.dumps(profile_data.get('emotion_patterns', {}), ensure_ascii=False),
                profile_data.get('empathy_level', 0.5),
                profile_data.get('emotional_stability', 0.5),
                profile_data.get('last_updated', time.time())
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存情感档案失败: {e}")
            return False

    async def load_emotion_profile(self, group_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """加载情感档案"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT dominant_emotions, emotion_patterns, empathy_level, emotional_stability, last_updated
                FROM emotion_profiles WHERE user_id = ? AND group_id = ?
            ''', (user_id, group_id))
            
            row = await cursor.fetchone()
            if not row:
                return None
                
            return {
                'user_id': user_id,
                'group_id': group_id,
                'dominant_emotions': json.loads(row[0]) if row[0] else {},
                'emotion_patterns': json.loads(row[1]) if row[1] else {},
                'empathy_level': row[2],
                'emotional_stability': row[3],
                'last_updated': row[4]
            }
            
        except Exception as e:
            self._logger.error(f"加载情感档案失败: {e}")
            return None

    async def save_knowledge_entity(self, group_id: str, entity_data: Dict[str, Any]) -> bool:
        """保存知识实体"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 检查是否已存在表，如果不存在则创建
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS knowledge_entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    attributes TEXT, -- JSON格式
                    relationships TEXT, -- JSON格式
                    confidence REAL DEFAULT 0.5,
                    source_messages TEXT, -- JSON格式
                    last_mentioned REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await cursor.execute('''
                INSERT OR REPLACE INTO knowledge_entities 
                (entity_id, name, entity_type, attributes, relationships, confidence, source_messages, last_mentioned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entity_data.get('entity_id'),
                entity_data.get('name', ''),
                entity_data.get('entity_type', 'unknown'),
                json.dumps(entity_data.get('attributes', {}), ensure_ascii=False),
                json.dumps(entity_data.get('relationships', []), ensure_ascii=False),
                entity_data.get('confidence', 0.5),
                json.dumps(entity_data.get('source_messages', []), ensure_ascii=False),
                entity_data.get('last_mentioned', time.time())
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存知识实体失败: {e}")
            return False

    async def get_knowledge_entities(self, group_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取知识实体列表"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT entity_id, name, entity_type, attributes, relationships, confidence, source_messages, last_mentioned
                FROM knowledge_entities 
                ORDER BY last_mentioned DESC
                LIMIT ?
            ''', (limit,))
            
            entities = []
            for row in await cursor.fetchall():
                entities.append({
                    'entity_id': row[0],
                    'name': row[1],
                    'entity_type': row[2],
                    'attributes': json.loads(row[3]) if row[3] else {},
                    'relationships': json.loads(row[4]) if row[4] else [],
                    'confidence': row[5],
                    'source_messages': json.loads(row[6]) if row[6] else [],
                    'last_mentioned': row[7]
                })
            
            return entities
            
        except Exception as e:
            self._logger.error(f"获取知识实体失败: {e}")
            return []

    # 新增强化学习相关方法
    async def save_reinforcement_learning_result(self, group_id: str, result_data: Dict[str, Any]) -> bool:
        """保存强化学习结果"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO reinforcement_learning_results 
                (group_id, timestamp, replay_analysis, optimization_strategy, reinforcement_feedback, next_action)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                group_id,
                result_data.get('timestamp', time.time()),
                json.dumps(result_data.get('replay_analysis', {}), ensure_ascii=False),
                json.dumps(result_data.get('optimization_strategy', {}), ensure_ascii=False),
                json.dumps(result_data.get('reinforcement_feedback', {}), ensure_ascii=False),
                result_data.get('next_action', '')
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"保存强化学习结果失败: {e}")
            return False

    async def get_learning_history_for_reinforcement(self, group_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取用于强化学习的历史数据"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT timestamp, quality_score, success, successful_pattern, failed_pattern
                FROM learning_performance_history 
                WHERE group_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (group_id, limit))
            
            history = []
            for row in await cursor.fetchall():
                history.append({
                    'timestamp': row[0],
                    'quality_score': row[1],
                    'success': bool(row[2]),
                    'successful_pattern': row[3] or '',
                    'failed_pattern': row[4] or ''
                })
            
            return history
            
        except Exception as e:
            logger.error(f"获取强化学习历史数据失败: {e}")
            return []

    async def save_persona_fusion_result(self, group_id: str, fusion_data: Dict[str, Any]) -> bool:
        """保存人格融合结果"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO persona_fusion_history 
                (group_id, timestamp, base_persona_hash, incremental_hash, fusion_result, compatibility_score)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                group_id,
                fusion_data.get('timestamp', time.time()),
                fusion_data.get('base_persona_hash'),
                fusion_data.get('incremental_hash'),
                json.dumps(fusion_data.get('fusion_result', {}), ensure_ascii=False),
                fusion_data.get('compatibility_score', 0.0)
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"保存人格融合结果失败: {e}")
            return False

    async def get_persona_fusion_history(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取人格融合历史"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT timestamp, base_persona_hash, incremental_hash, fusion_result, compatibility_score
                FROM persona_fusion_history 
                WHERE group_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (group_id, limit))
            
            history = []
            for row in await cursor.fetchall():
                fusion_result = {}
                try:
                    fusion_result = json.loads(row[3]) if row[3] else {}
                except json.JSONDecodeError:
                    logger.warning(f"解析融合结果JSON失败: {row[3]}")
                
                history.append({
                    'timestamp': row[0],
                    'base_persona_hash': row[1],
                    'incremental_hash': row[2],
                    'fusion_result': fusion_result,
                    'compatibility_score': row[4]
                })
            
            return history
            
        except Exception as e:
            logger.error(f"获取人格融合历史失败: {e}")
            return []

    async def save_strategy_optimization_result(self, group_id: str, optimization_data: Dict[str, Any]) -> bool:
        """保存策略优化结果"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO strategy_optimization_results 
                (group_id, timestamp, original_strategy, optimization_result, expected_improvement)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                group_id,
                optimization_data.get('timestamp', time.time()),
                json.dumps(optimization_data.get('original_strategy', {}), ensure_ascii=False),
                json.dumps(optimization_data.get('optimization_result', {}), ensure_ascii=False),
                json.dumps(optimization_data.get('expected_improvement', {}), ensure_ascii=False)
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"保存策略优化结果失败: {e}")
            return False

    async def get_learning_performance_history(self, group_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """获取学习性能历史数据"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT session_id, timestamp, quality_score, learning_time, success
                FROM learning_performance_history 
                WHERE group_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (group_id, limit))
            
            history = []
            for row in await cursor.fetchall():
                history.append({
                    'session_id': row[0],
                    'timestamp': row[1],
                    'quality_score': row[2] or 0.0,
                    'learning_time': row[3] or 0.0,
                    'success': bool(row[4])
                })
            
            return history
            
        except Exception as e:
            logger.error(f"获取学习性能历史失败: {e}")
            return []

    async def save_learning_performance_record(self, group_id: str, performance_data: Dict[str, Any]) -> bool:
        """保存学习性能记录"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT INTO learning_performance_history 
                (group_id, session_id, timestamp, quality_score, learning_time, success, successful_pattern, failed_pattern)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                group_id,
                performance_data.get('session_id', ''),
                performance_data.get('timestamp', time.time()),
                performance_data.get('quality_score', 0.0),
                performance_data.get('learning_time', 0.0),
                performance_data.get('success', False),
                performance_data.get('successful_pattern', ''),
                performance_data.get('failed_pattern', '')
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"保存学习性能记录失败: {e}")
            return False

    async def get_messages_for_replay(self, group_id: str, days: int = 30, limit: int = 100) -> List[Dict[str, Any]]:
        """获取用于记忆重放的消息"""
        conn = await self._get_messages_db_connection()
        cursor = await conn.cursor()
        
        try:
            # 获取指定天数内的消息
            cutoff_time = time.time() - (days * 24 * 3600)
            
            await cursor.execute('''
                SELECT id, message, sender_id, group_id, timestamp
                FROM raw_messages 
                WHERE group_id = ? AND timestamp > ? AND processed = TRUE
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (group_id, cutoff_time, limit))
            
            messages = []
            for row in await cursor.fetchall():
                messages.append({
                    'message_id': row[0],
                    'message': row[1],
                    'sender_id': row[2],
                    'group_id': row[3],
                    'timestamp': row[4]
                })
            
            return messages
            
        except Exception as e:
            logger.error(f"获取记忆重放消息失败: {e}")
            return []

    async def save_user_preferences(self, group_id: str, user_id: str, preferences: Dict[str, Any]) -> bool:
        """保存用户偏好设置"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 检查是否已存在表，如果不存在则创建
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    favorite_topics TEXT, -- JSON格式
                    interaction_style TEXT, -- JSON格式
                    learning_preferences TEXT, -- JSON格式
                    adaptive_rate REAL DEFAULT 0.5,
                    updated_at REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_id)
                )
            ''')
            
            await cursor.execute('''
                INSERT OR REPLACE INTO user_preferences 
                (user_id, group_id, favorite_topics, interaction_style, learning_preferences, adaptive_rate, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                group_id,
                json.dumps(preferences.get('favorite_topics', []), ensure_ascii=False),
                json.dumps(preferences.get('interaction_style', {}), ensure_ascii=False),
                json.dumps(preferences.get('learning_preferences', {}), ensure_ascii=False),
                preferences.get('adaptive_rate', 0.5),
                time.time()
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存用户偏好失败: {e}")
            return False

    async def load_user_preferences(self, group_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """加载用户偏好设置"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT favorite_topics, interaction_style, learning_preferences, adaptive_rate, updated_at
                FROM user_preferences WHERE user_id = ? AND group_id = ?
            ''', (user_id, group_id))
            
            row = await cursor.fetchone()
            if not row:
                return None
                
            return {
                'favorite_topics': json.loads(row[0]) if row[0] else [],
                'interaction_style': json.loads(row[1]) if row[1] else {},
                'learning_preferences': json.loads(row[2]) if row[2] else {},
                'adaptive_rate': row[3],
                'updated_at': row[4]
            }
            
        except Exception as e:
            self._logger.error(f"加载用户偏好失败: {e}")
            return None

    async def save_conversation_context(self, group_id: str, context_data: Dict[str, Any]) -> bool:
        """保存对话上下文"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            # 检查是否已存在表，如果不存在则创建
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversation_contexts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    context_id TEXT UNIQUE NOT NULL,
                    participants TEXT, -- JSON格式存储参与者列表
                    current_topic TEXT,
                    emotion_state TEXT, -- JSON格式存储情感状态
                    context_messages TEXT, -- JSON格式存储上下文消息
                    start_time REAL NOT NULL,
                    last_updated REAL NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await cursor.execute('''
                INSERT OR REPLACE INTO conversation_contexts 
                (group_id, context_id, participants, current_topic, emotion_state, context_messages, start_time, last_updated, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                group_id,
                context_data.get('context_id'),
                json.dumps(list(context_data.get('participants', set())), ensure_ascii=False),
                context_data.get('current_topic'),
                json.dumps(context_data.get('emotion_state', {}), ensure_ascii=False),
                json.dumps(context_data.get('messages', []), ensure_ascii=False),
                context_data.get('start_time', time.time()),
                time.time(),
                context_data.get('is_active', True)
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存对话上下文失败: {e}")
            return False

    async def get_active_conversation_contexts(self, group_id: str) -> List[Dict[str, Any]]:
        """获取活跃的对话上下文"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT context_id, participants, current_topic, emotion_state, context_messages, start_time, last_updated
                FROM conversation_contexts 
                WHERE group_id = ? AND is_active = TRUE
                ORDER BY last_updated DESC
            ''', (group_id,))
            
            contexts = []
            for row in await cursor.fetchall():
                contexts.append({
                    'context_id': row[0],
                    'participants': set(json.loads(row[1])) if row[1] else set(),
                    'current_topic': row[2],
                    'emotion_state': json.loads(row[3]) if row[3] else {},
                    'messages': json.loads(row[4]) if row[4] else [],
                    'start_time': row[5],
                    'last_updated': row[6]
                })
            
            return contexts
            
        except Exception as e:
            self._logger.error(f"获取对话上下文失败: {e}")
            return []

    async def save_learning_session_record(self, group_id: str, session_data: Dict[str, Any]) -> bool:
        """保存学习会话记录"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                INSERT OR REPLACE INTO learning_sessions
                (session_id, start_time, end_time, messages_processed, filtered_messages, 
                 style_updates, quality_score, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_data.get('session_id'),
                session_data.get('start_time'),
                session_data.get('end_time'),
                session_data.get('messages_processed', 0),
                session_data.get('filtered_messages', 0),
                session_data.get('style_updates', 0),
                session_data.get('quality_score', 0.0),
                session_data.get('success', False)
            ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存学习会话记录失败: {e}")
            return False

    async def get_recent_learning_sessions(self, group_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近的学习会话记录"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            start_time = time.time() - (days * 24 * 3600)
            
            await cursor.execute('''
                SELECT session_id, start_time, end_time, messages_processed, filtered_messages,
                       style_updates, quality_score, success
                FROM learning_sessions 
                WHERE start_time >= ?
                ORDER BY start_time DESC
            ''', (start_time,))
            
            sessions = []
            for row in await cursor.fetchall():
                sessions.append({
                    'session_id': row[0],
                    'start_time': row[1],
                    'end_time': row[2],
                    'messages_processed': row[3],
                    'filtered_messages': row[4],
                    'style_updates': row[5],
                    'quality_score': row[6],
                    'success': row[7]
                })
            
            return sessions
            
        except Exception as e:
            self._logger.error(f"获取学习会话记录失败: {e}")
            return []

    # ========== 好感度系统数据库操作方法 ==========

    async def get_user_affection(self, group_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户好感度"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT affection_level, last_interaction, last_updated, interaction_count
                FROM user_affection WHERE user_id = ? AND group_id = ?
            ''', (user_id, group_id))
            
            row = await cursor.fetchone()
            if not row:
                return None
                
            return {
                'user_id': user_id,
                'group_id': group_id,
                'affection_level': row[0],
                'last_interaction': row[1],
                'last_updated': row[2],
                'interaction_count': row[3]
            }
            
        except Exception as e:
            self._logger.error(f"获取用户好感度失败: {e}")
            return None

    async def update_user_affection(self, group_id: str, user_id: str, 
                                  new_level: int, change_reason: str = "", 
                                  bot_mood: str = "") -> bool:
        """更新用户好感度"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            current_time = time.time()
            
            # 获取当前好感度
            current_affection = await self.get_user_affection(group_id, user_id)
            previous_level = current_affection['affection_level'] if current_affection else 0
            interaction_count = current_affection['interaction_count'] if current_affection else 0
            
            # 更新或插入好感度记录
            await cursor.execute('''
                INSERT OR REPLACE INTO user_affection 
                (user_id, group_id, affection_level, last_interaction, last_updated, interaction_count)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, group_id, new_level, current_time, current_time, interaction_count + 1))
            
            # 记录好感度变化历史
            change_amount = new_level - previous_level
            if change_amount != 0:
                await cursor.execute('''
                    INSERT INTO affection_history 
                    (user_id, group_id, change_amount, previous_level, new_level, 
                     change_reason, bot_mood, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, group_id, change_amount, previous_level, new_level, 
                      change_reason, bot_mood, current_time))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"更新用户好感度失败: {e}")
            return False

    async def get_all_user_affections(self, group_id: str) -> List[Dict[str, Any]]:
        """获取群内所有用户好感度"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT user_id, affection_level, last_interaction, last_updated, interaction_count
                FROM user_affection 
                WHERE group_id = ?
                ORDER BY affection_level DESC
            ''', (group_id,))
            
            affections = []
            for row in await cursor.fetchall():
                affections.append({
                    'user_id': row[0],
                    'group_id': group_id,
                    'affection_level': row[1],
                    'last_interaction': row[2],
                    'last_updated': row[3],
                    'interaction_count': row[4]
                })
            
            return affections
            
        except Exception as e:
            self._logger.error(f"获取所有用户好感度失败: {e}")
            return []

    async def get_total_affection(self, group_id: str) -> int:
        """获取群内总好感度"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            await cursor.execute('''
                SELECT SUM(affection_level) FROM user_affection WHERE group_id = ?
            ''', (group_id,))
            
            result = await cursor.fetchone()
            return result[0] if result[0] is not None else 0
            
        except Exception as e:
            self._logger.error(f"获取总好感度失败: {e}")
            return 0

    async def save_bot_mood(self, group_id: str, mood_type: str, mood_intensity: float,
                           mood_description: str, duration_hours: int = 24) -> bool:
        """保存bot情绪状态"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            current_time = time.time()
            end_time = current_time + (duration_hours * 3600)
            
            # 将之前的情绪设为非活跃状态
            await cursor.execute('''
                UPDATE bot_mood SET is_active = FALSE, end_time = ? WHERE group_id = ? AND is_active = TRUE
            ''', (current_time, group_id))
            
            # 插入新的情绪状态
            await cursor.execute('''
                INSERT INTO bot_mood 
                (group_id, mood_type, mood_intensity, mood_description, start_time, end_time, is_active)
                VALUES (?, ?, ?, ?, ?, ?, TRUE)
            ''', (group_id, mood_type, mood_intensity, mood_description, current_time, end_time))
            
            await conn.commit()
            return True
            
        except Exception as e:
            self._logger.error(f"保存bot情绪失败: {e}")
            return False

    async def get_current_bot_mood(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取当前bot情绪"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            current_time = time.time()
            
            await cursor.execute('''
                SELECT mood_type, mood_intensity, mood_description, start_time, end_time
                FROM bot_mood 
                WHERE group_id = ? AND is_active = TRUE AND start_time <= ? AND (end_time IS NULL OR end_time > ?)
                ORDER BY start_time DESC
                LIMIT 1
            ''', (group_id, current_time, current_time))
            
            row = await cursor.fetchone()
            if not row:
                return None
                
            return {
                'mood_type': row[0],
                'mood_intensity': row[1],
                'mood_description': row[2],
                'start_time': row[3],
                'end_time': row[4]
            }
            
        except Exception as e:
            self._logger.error(f"获取当前bot情绪失败: {e}")
            return None

    async def get_affection_history(self, group_id: str, user_id: str = None, 
                                   days: int = 7) -> List[Dict[str, Any]]:
        """获取好感度变化历史"""
        conn = await self.get_group_connection(group_id)
        cursor = await conn.cursor()
        
        try:
            start_time = time.time() - (days * 24 * 3600)
            
            if user_id:
                await cursor.execute('''
                    SELECT user_id, change_amount, previous_level, new_level, 
                           change_reason, bot_mood, timestamp
                    FROM affection_history 
                    WHERE group_id = ? AND user_id = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                ''', (group_id, user_id, start_time))
            else:
                await cursor.execute('''
                    SELECT user_id, change_amount, previous_level, new_level, 
                           change_reason, bot_mood, timestamp
                    FROM affection_history 
                    WHERE group_id = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                ''', (group_id, start_time))
            
            history = []
            for row in await cursor.fetchall():
                history.append({
                    'user_id': row[0],
                    'change_amount': row[1],
                    'previous_level': row[2],
                    'new_level': row[3],
                    'change_reason': row[4],
                    'bot_mood': row[5],
                    'timestamp': row[6]
                })
            
            return history
            
        except Exception as e:
            self._logger.error(f"获取好感度历史失败: {e}")
            return []

    async def export_messages_learning_data(self) -> Dict[str, Any]:
        """导出消息学习数据"""
        try:
            conn = await self._get_messages_db_connection()
            cursor = await conn.cursor()

            # 导出原始消息
            await cursor.execute('''
                SELECT id, sender_id, sender_name, message, group_id, platform, timestamp, processed
                FROM raw_messages ORDER BY timestamp DESC
            ''')
            raw_messages = []
            for row in await cursor.fetchall():
                raw_messages.append({
                    'id': row[0],
                    'sender_id': row[1],
                    'sender_name': row[2],
                    'message': row[3],
                    'group_id': row[4],
                    'platform': row[5],
                    'timestamp': row[6],
                    'processed': bool(row[7])
                })

            # 导出筛选消息
            await cursor.execute('''
                SELECT id, raw_message_id, message, sender_id, group_id, confidence,
                       filter_reason, timestamp, used_for_learning, quality_scores
                FROM filtered_messages ORDER BY timestamp DESC
            ''')
            filtered_messages = []
            for row in await cursor.fetchall():
                quality_scores = {}
                try:
                    if row[9]:  # quality_scores
                        quality_scores = json.loads(row[9])
                except (json.JSONDecodeError, TypeError):
                    pass

                filtered_messages.append({
                    'id': row[0],
                    'raw_message_id': row[1],
                    'message': row[2],
                    'sender_id': row[3],
                    'group_id': row[4],
                    'confidence': row[5],
                    'filter_reason': row[6],
                    'timestamp': row[7],
                    'used_for_learning': bool(row[8]),
                    'quality_scores': quality_scores
                })

            # 导出学习批次记录
            await cursor.execute('''
                SELECT id, group_id, start_time, end_time, quality_score,
                       processed_messages, batch_name, message_count,
                       filtered_count, success, error_message
                FROM learning_batches ORDER BY start_time DESC
            ''')
            learning_batches = []
            for row in await cursor.fetchall():
                learning_batches.append({
                    'id': row[0],
                    'group_id': row[1],
                    'start_time': row[2],
                    'end_time': row[3],
                    'quality_score': row[4],
                    'processed_messages': row[5],
                    'batch_name': row[6],
                    'message_count': row[7],
                    'filtered_count': row[8],
                    'success': bool(row[9]),
                    'error_message': row[10]
                })

            # 导出人格更新记录
            await cursor.execute('''
                SELECT id, timestamp, group_id, update_type, original_content,
                       new_content, reason, status, reviewer_comment, review_time
                FROM persona_update_records ORDER BY timestamp DESC
            ''')
            persona_update_records = []
            for row in await cursor.fetchall():
                persona_update_records.append({
                    'id': row[0],
                    'timestamp': row[1],
                    'group_id': row[2],
                    'update_type': row[3],
                    'original_content': row[4],
                    'new_content': row[5],
                    'reason': row[6],
                    'status': row[7],
                    'reviewer_comment': row[8],
                    'review_time': row[9]
                })

            # 获取统计信息
            statistics = await self.get_messages_statistics()

            export_data = {
                'export_timestamp': time.time(),
                'export_date': datetime.now().isoformat(),
                'statistics': statistics,
                'raw_messages': raw_messages,
                'filtered_messages': filtered_messages,
                'learning_batches': learning_batches,
                'persona_update_records': persona_update_records
            }

            self._logger.info(f"成功导出学习数据: {len(raw_messages)} 条原始消息, {len(filtered_messages)} 条筛选消息")
            return export_data

        except Exception as e:
            self._logger.error(f"导出消息学习数据失败: {e}", exc_info=True)
            raise DataStorageError(f"导出消息学习数据失败: {str(e)}")

    async def clear_all_messages_data(self):
        """清空所有消息数据"""
        try:
            conn = await self._get_messages_db_connection()
            cursor = await conn.cursor()

            # 清空所有表的数据
            tables_to_clear = [
                'raw_messages',
                'filtered_messages',
                'learning_batches',
                'persona_update_records',
                'reinforcement_learning_results',
                'persona_fusion_history',
                'strategy_optimization_results',
                'learning_performance_history'
            ]

            for table in tables_to_clear:
                await cursor.execute(f'DELETE FROM {table}')
                self._logger.debug(f"已清空表: {table}")

            await conn.commit()
            self._logger.info("所有消息数据已清空")

        except Exception as e:
            self._logger.error(f"清空所有消息数据失败: {e}", exc_info=True)
            raise DataStorageError(f"清空所有消息数据失败: {str(e)}")
