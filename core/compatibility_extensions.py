"""
方法接口兼容性扩展 - 为新服务提供必要的接口方法
"""
import json
import time
from typing import Dict, List, Optional, Any


class LLMClientExtension:
    """LLM客户端扩展，提供统一的生成接口 - 已弃用，建议使用FrameworkLLMAdapter"""
    
    def __init__(self, llm_client, config, persona_manager=None, llm_adapter=None):
        self.llm_client = llm_client
        self.config = config
        self.persona_manager = persona_manager
        self.llm_adapter = llm_adapter  # 新增适配器支持
    
    async def generate_response(self, prompt: str, model_name: Optional[str] = None, 
                               group_id: Optional[str] = None, **kwargs) -> str:
        """生成响应的统一接口，自动包含当前人格信息"""
        try:
            # 获取当前人格信息
            system_prompt = None
            if self.persona_manager and group_id:
                try:
                    if hasattr(self.persona_manager, 'get_current_persona_description'):
                        persona_description = await self.persona_manager.get_current_persona_description(group_id)
                    else:
                        # 兼容性处理
                        persona_ext = PersonaManagerExtension(self.persona_manager)
                        persona_description = await persona_ext.get_current_persona_description(group_id)
                    
                    if persona_description:
                        system_prompt = f"你的人格特征：{persona_description}\n\n请根据上述人格特征来回应用户。"
                except Exception as e:
                    from astrbot.api import logger
                    logger.error(f"获取人格描述失败: {e}")
            
            # 优先使用新的适配器
            if self.llm_adapter and self.llm_adapter.has_filter_provider():
                response = await self.llm_adapter.filter_chat_completion(
                    prompt=prompt,
                    system_prompt=system_prompt
                )
            else:
                # 向后兼容：使用老式API配置
                api_url = getattr(self.config, 'filter_api_url', 'http://localhost:1234/v1/chat/completions')
                api_key = getattr(self.config, 'filter_api_key', 'not-needed')
                # 如果没有传入模型名称，使用默认值
                if not model_name:
                    model_name = 'gpt-4o'
                
                # 调用LLM
                response = await self.llm_client.chat_completion(
                    api_url=api_url,
                    api_key=api_key,
                    model_name=model_name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    **kwargs
                )
            
            if response and hasattr(response, 'text'):
                return response.text()
            else:
                return "抱歉，我暂时无法理解您的问题。"
                
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"LLM响应生成失败: {e}")
            return "抱歉，我暂时无法理解您的问题。"


class DatabaseManagerExtension:
    """数据库管理器扩展，提供缺失的方法"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    async def get_persona_update_history(self, group_id: str, days: int) -> List[Dict]:
        """获取人格更新历史（基于真实数据库查询）"""
        try:
            # 使用数据库管理器的专门方法获取学习会话记录
            sessions = await self.db_manager.get_recent_learning_sessions(group_id, days)
            
            # 转换为人格更新历史格式
            history = []
            for session in sessions:
                history.append({
                    'timestamp': session.get('start_time', time.time()),
                    'group_id': group_id,
                    'style_profile': {
                        'quality_score': session.get('quality_score', 0.5),
                        'messages_processed': session.get('messages_processed', 0),
                        'success': session.get('success', False)
                    },
                    'update_type': 'learning_session',
                    'backup_reason': f"学习会话 {session.get('session_id', 'unknown')}"
                })
            
            return history
            
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"获取人格更新历史失败: {e}")
            return []
    
    async def get_learning_batch_history(self, group_id: str, days: int) -> List[Dict]:
        """获取学习批次历史（基于真实数据库查询）"""
        try:
            # 从全局消息数据库查询学习批次记录
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                start_timestamp = time.time() - (days * 24 * 3600)
                
                await cursor.execute('''
                    SELECT * FROM learning_batches 
                    WHERE start_time >= ? AND group_id = ?
                    ORDER BY start_time DESC 
                    LIMIT 30
                ''', (start_timestamp, group_id))
                
                rows = await cursor.fetchall()
                history = []
                
                for row in rows:
                    history.append({
                        'start_time': row[2],  # start_time column
                        'end_time': row[3],    # end_time column
                        'group_id': row[1],    # group_id column
                        'quality_score': row[4] if row[4] else 0.5,  # quality_score column
                        'processed_messages': row[5] if row[5] else 0,  # processed_messages column
                        'processing_time': (row[3] - row[2]) if (row[3] and row[2]) else 0  # calculate from timestamps
                    })
                
                return history
            
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"获取学习批次历史失败: {e}")
            # 如果表不存在或查询失败，返回空列表
            return []
    
    async def get_messages_by_timerange(self, group_id: str, start_time, end_time) -> List[Dict]:
        """根据时间范围获取消息（基于真实数据库查询）"""
        try:
            # 从全局消息数据库查询指定时间范围内的消息
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                start_timestamp = start_time.timestamp()
                end_timestamp = end_time.timestamp()
                
                await cursor.execute('''
                    SELECT sender_id, sender_name, message, group_id, platform, timestamp 
                    FROM raw_messages 
                    WHERE timestamp >= ? AND timestamp <= ? AND group_id = ?
                    ORDER BY timestamp ASC
                    LIMIT 1000
                ''', (start_timestamp, end_timestamp, group_id))
                
                rows = await cursor.fetchall()
                messages = []
                
                for row in rows:
                    messages.append({
                        'timestamp': row[5],    # timestamp column
                        'group_id': row[3],     # group_id column
                        'sender_id': row[0],    # sender_id column
                        'sender_name': row[1],  # sender_name column
                        'message': row[2],      # message column
                        'platform': row[4]      # platform column
                    })
                
                return messages
            
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"根据时间范围获取消息失败: {e}")
            # 如果查询失败，返回空列表
            return []
    
    async def get_social_relationships(self, group_id: str, days: int) -> List[Dict]:
        """获取社交关系数据（基于真实数据库查询）"""
        try:
            # 使用数据库管理器的现有方法
            relationships = await self.db_manager.load_social_graph(group_id)
            
            # 过滤最近几天的关系
            start_timestamp = time.time() - (days * 24 * 3600)
            filtered_relationships = [
                {
                    'user1_id': rel['from_user'],
                    'user2_id': rel['to_user'],
                    'relationship_type': rel['relation_type'],
                    'interaction_count': rel['frequency'],
                    'strength': rel['strength'],
                    'last_interaction': rel['last_interaction']
                }
                for rel in relationships
                if rel['last_interaction'] >= start_timestamp
            ]
            
            return filtered_relationships
            
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"获取社交关系失败: {e}")
            return []
    
    async def get_message_statistics(self) -> Dict[str, int]:
        """获取消息统计（基于真实数据库查询）"""
        try:
            # 从全局消息数据库查询真实统计
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                # 查询原始消息总数
                await cursor.execute('SELECT COUNT(*) FROM raw_messages')
                total_messages = (await cursor.fetchone())[0]
                
                # 查询筛选后消息数
                await cursor.execute('SELECT COUNT(*) FROM filtered_messages')
                filtered_messages = (await cursor.fetchone())[0]
                
                # 查询已用于学习的消息数
                await cursor.execute('SELECT COUNT(*) FROM filtered_messages WHERE used_for_learning = 1')
                processed_messages = (await cursor.fetchone())[0]
                
                return {
                    'total_messages': total_messages,
                    'filtered_messages': filtered_messages, 
                    'processed_messages': processed_messages
                }
            
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"获取消息统计失败: {e}")
            return {'total_messages': 0, 'filtered_messages': 0, 'processed_messages': 0}


class PersonaManagerExtension:
    """人格管理器扩展，提供缺失的方法"""
    
    def __init__(self, persona_manager):
        self.persona_manager = persona_manager
    
    async def get_current_persona(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取当前人格配置"""
        try:
            # 尝试调用原有方法
            if hasattr(self.persona_manager, 'get_current_persona'):
                result = await self.persona_manager.get_current_persona()
                if isinstance(result, dict):
                    return result
            
            # 返回默认人格配置
            return {
                'name': '默认人格',
                'description': '友好、智能的AI助手',
                'style_profile': {
                    'creativity': 0.7,
                    'formality': 0.5,
                    'emotional_intensity': 0.6,
                    'vocabulary_richness': 0.6,
                    'empathy': 0.8
                },
                'group_id': group_id,
                'last_updated': time.time()
            }
            
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"获取当前人格配置失败: {e}")
            return None
    
    async def get_current_persona_description(self, group_id: str = None) -> str:
        """获取当前人格描述"""
        try:
            if hasattr(self.persona_manager, 'get_current_persona_description'):
                result = await self.persona_manager.get_current_persona_description()
                if result:
                    return result
            
            # 返回默认描述
            return "我是一个友好、智能的AI助手，能够理解您的需求并提供有用的回答。"
            
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"获取人格描述失败: {e}")
            return "我是一个AI助手。"


def create_compatibility_extensions(config, llm_client, db_manager, persona_manager):
    """创建兼容性扩展"""
    return {
        'llm_client': LLMClientExtension(llm_client, config, persona_manager),
        'db_manager': DatabaseManagerExtension(db_manager),
        'persona_manager': PersonaManagerExtension(persona_manager) if persona_manager else None
    }