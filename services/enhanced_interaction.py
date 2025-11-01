"""
增强交互服务 - 提供图像理解、多轮对话管理、跨群记忆等交互增强功能
"""
import asyncio
import json
import time
import os
import base64
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, asdict

import numpy as np

from astrbot.api import logger

from ..config import PluginConfig

from ..core.patterns import AsyncServiceBase

from ..core.interfaces import IDataStorage

from ..core.framework_llm_adapter import FrameworkLLMAdapter


@dataclass
class ConversationContext:
    """对话上下文数据结构"""
    group_id: str
    messages: List[Dict]
    current_topic: Optional[str]
    participants: set
    emotion_state: Dict[str, float]
    last_activity: float
    context_embedding: Optional[List[float]] = None


@dataclass
class CrossGroupMemory:
    """跨群记忆数据结构"""
    user_id: str
    global_profile: Dict[str, Any]
    group_behaviors: Dict[str, Dict]  # group_id -> behavior_data
    cross_group_relationships: List[Dict]
    last_updated: float


class EnhancedInteractionService(AsyncServiceBase):
    """增强交互服务"""
    
    def __init__(self, config: PluginConfig, database_manager: IDataStorage, 
                 llm_adapter: Optional[FrameworkLLMAdapter] = None):
        super().__init__("enhanced_interaction")
        self.config = config
        self.db_manager = database_manager
        self.llm_adapter = llm_adapter
        
        # 多轮对话管理
        self.conversation_contexts: Dict[str, ConversationContext] = {}
        self.context_retention_time = 3600  # 1小时
        
        # 跨群记忆
        self.cross_group_memories: Dict[str, CrossGroupMemory] = {}
        self.memory_sync_interval = 300  # 5分钟同步一次
        
        # 主动话题引导
        self.group_interests = defaultdict(dict)
        self.topic_suggestions = defaultdict(list)
        self.last_topic_guidance = defaultdict(float)
        
    async def _do_start(self) -> bool:
        """启动增强交互服务"""
        try:
            await self._load_cross_group_memories()
            await self._load_group_interests()
            
            # 启动定期任务
            asyncio.create_task(self._periodic_memory_sync())
            asyncio.create_task(self._periodic_context_cleanup())
            
            self._logger.info("增强交互服务启动成功")
            return True
        except Exception as e:
            self._logger.error(f"增强交互服务启动失败: {e}")
            return False
    
    async def _do_stop(self) -> bool:
        """停止增强交互服务"""
        await self._save_cross_group_memories()
        await self._save_group_interests()
        return True
    
    async def _analyze_text_emotion(self, text: str) -> Dict[str, Any]:
        """分析文本情感（简化版本）"""
        # 简单的情感词典分析
        positive_words = ['开心', '快乐', '哈哈', '笑', '好', '棒', '赞']
        negative_words = ['难过', '生气', '哭', '糟糕', '差', '恨']
        humorous_words = ['哈哈', '嘻嘻', '搞笑', '有趣', '逗', '搞怪']
        
        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)
        humorous_count = sum(1 for word in humorous_words if word in text)
        
        # 简单的情感分类
        if humorous_count > 0:
            emotion_type = 'humorous'
            intensity = min(1.0, humorous_count / 3)
        elif positive_count > negative_count:
            emotion_type = 'positive'
            intensity = min(1.0, positive_count / 3)
        elif negative_count > positive_count:
            emotion_type = 'negative'
            intensity = min(1.0, negative_count / 3)
        else:
            emotion_type = 'neutral'
            intensity = 0.0
        
        return {
            'emotion_type': emotion_type,
            'expression_intensity': intensity,
            'humor_level': min(1.0, humorous_count / 2)
        }
    
    
    
    
    async def update_conversation_context(self, group_id: str, sender_id: str, message_text: str):
        """更新对话上下文 - main.py调用的接口方法"""
        message_data = {
            'sender_id': sender_id,
            'message': message_text,
            'timestamp': time.time()
        }
        await self.manage_conversation_context(group_id, message_data)
    
    async def manage_conversation_context(self, group_id: str, message: Dict) -> ConversationContext:
        """管理多轮对话上下文"""
        try:
            current_time = time.time()
            
            # 获取或创建对话上下文
            if group_id not in self.conversation_contexts:
                self.conversation_contexts[group_id] = ConversationContext(
                    group_id=group_id,
                    messages=[],
                    current_topic=None,
                    participants=set(),
                    emotion_state={},
                    last_activity=current_time
                )
            
            context = self.conversation_contexts[group_id]
            
            # 更新上下文
            context.messages.append(message)
            context.participants.add(message.get('sender_id'))
            context.last_activity = current_time
            
            # 保持消息历史在合理大小
            if len(context.messages) > 100:
                context.messages = context.messages[-100:]
            
            # 检测话题变化
            new_topic = await self._detect_topic_change(context.messages)
            if new_topic != context.current_topic:
                context.current_topic = new_topic
                self._logger.info(f"群组 {group_id} 话题变化: {context.current_topic}")
            
            # 更新情感状态
            await self._update_conversation_emotion_state(context, message)
            
            return context
            
        except Exception as e:
            self._logger.error(f"对话上下文管理失败: {e}")
            return self.conversation_contexts.get(group_id)
    
    async def _detect_topic_change(self, messages: List[Dict]) -> Optional[str]:
        """检测话题变化"""
        if len(messages) < 3:
            return None
        
        try:
            # 分析最近几条消息的话题
            recent_messages = messages[-5:]
            message_texts = [msg.get('message', '') for msg in recent_messages]
            
            topic_prompt = f"""
            分析以下对话消息，提取当前讨论的主要话题：
            
            消息内容:
            {chr(10).join(f"- {text}" for text in message_texts)}
            
            请用2-4个词概括当前话题，如果没有明确话题返回"日常聊天"。
            只返回话题名称，不要其他内容。
            """
            
            if not self.llm_adapter:
                self._logger.warning("LLM适配器未配置，跳过话题检测")
                return None
            
            response = await self.llm_adapter.filter_chat_completion(
                prompt=topic_prompt
            )
            
            return response.strip() if response else None
            
        except Exception as e:
            self._logger.error(f"话题检测失败: {e}")
            return None
    
    async def _update_conversation_emotion_state(self, context: ConversationContext, message: Dict):
        """更新对话情感状态"""
        sender_id = message.get('sender_id')
        content = message.get('message', '')
        
        # 简单情感分析
        emotion_score = await self._simple_emotion_analysis(content)
        
        # 更新发言者的情感状态
        context.emotion_state[sender_id] = {
            'last_emotion': emotion_score,
            'timestamp': time.time()
        }
        
        # 清理过期的情感状态
        current_time = time.time()
        expired_users = [
            user_id for user_id, data in context.emotion_state.items()
            if current_time - data['timestamp'] > 1800  # 30分钟过期
        ]
        
        for user_id in expired_users:
            del context.emotion_state[user_id]
    
    async def _simple_emotion_analysis(self, text: str) -> Dict[str, float]:
        """简单情感分析"""
        emotions = {
            'positive': 0.0,
            'negative': 0.0,
            'neutral': 1.0,
            'excited': 0.0
        }
        
        # 关键词匹配
        positive_keywords = ['开心', '快乐', '好', '棒', '赞', '哈哈', '笑']
        negative_keywords = ['难过', '生气', '糟糕', '恨', '讨厌', '愤怒']
        excited_keywords = ['！', '!', '哇', '太好了', '太棒了', '激动']
        
        text_lower = text.lower()
        
        for keyword in positive_keywords:
            if keyword in text_lower:
                emotions['positive'] += 0.2
                emotions['neutral'] -= 0.1
        
        for keyword in negative_keywords:
            if keyword in text_lower:
                emotions['negative'] += 0.2
                emotions['neutral'] -= 0.1
        
        for keyword in excited_keywords:
            if keyword in text_lower:
                emotions['excited'] += 0.3
                emotions['neutral'] -= 0.1
        
        # 确保数值在合理范围内
        for key in emotions:
            emotions[key] = max(0.0, min(1.0, emotions[key]))
        
        return emotions
    
    async def manage_cross_group_memory(self, user_id: str, group_id: str, 
                                      message_data: Dict) -> CrossGroupMemory:
        """管理跨群记忆"""
        try:
            # 获取或创建跨群记忆
            if user_id not in self.cross_group_memories:
                self.cross_group_memories[user_id] = CrossGroupMemory(
                    user_id=user_id,
                    global_profile={},
                    group_behaviors={},
                    cross_group_relationships=[],
                    last_updated=time.time()
                )
            
            memory = self.cross_group_memories[user_id]
            
            # 更新群组行为数据
            if group_id not in memory.group_behaviors:
                memory.group_behaviors[group_id] = {
                    'message_count': 0,
                    'avg_message_length': 0,
                    'activity_times': [],
                    'interaction_partners': set(),
                    'topics_discussed': set()
                }
            
            group_behavior = memory.group_behaviors[group_id]
            
            # 更新统计数据
            group_behavior['message_count'] += 1
            
            message_length = len(message_data.get('message', ''))
            prev_avg = group_behavior['avg_message_length']
            count = group_behavior['message_count']
            group_behavior['avg_message_length'] = (prev_avg * (count - 1) + message_length) / count
            
            # 记录活动时间
            group_behavior['activity_times'].append(time.time())
            if len(group_behavior['activity_times']) > 100:  # 保持合理大小
                group_behavior['activity_times'] = group_behavior['activity_times'][-100:]
            
            # 更新全局档案
            await self._update_global_user_profile(memory, group_id, message_data)
            
            memory.last_updated = time.time()
            
            return memory
            
        except Exception as e:
            self._logger.error(f"跨群记忆管理失败: {e}")
            return self.cross_group_memories.get(user_id)
    
    async def _update_global_user_profile(self, memory: CrossGroupMemory, 
                                        group_id: str, message_data: Dict):
        """更新全局用户档案"""
        try:
            profile = memory.global_profile
            
            # 计算跨群一致性
            consistency_scores = self._calculate_cross_group_consistency(memory.group_behaviors)
            profile['consistency_scores'] = consistency_scores
            
            # 计算总体活跃度
            total_messages = sum(
                behavior.get('message_count', 0) 
                for behavior in memory.group_behaviors.values()
            )
            profile['total_messages'] = total_messages
            
            # 计算平均消息长度
            avg_lengths = [
                behavior.get('avg_message_length', 0) 
                for behavior in memory.group_behaviors.values()
            ]
            profile['global_avg_message_length'] = np.mean(avg_lengths) if avg_lengths else 0
            
            # 活跃群组数
            profile['active_groups'] = len([
                gid for gid, behavior in memory.group_behaviors.items()
                if behavior.get('message_count', 0) > 10
            ])
            
        except Exception as e:
            self._logger.error(f"全局用户档案更新失败: {e}")
    
    def _calculate_cross_group_consistency(self, group_behaviors: Dict) -> Dict[str, float]:
        """计算跨群行为一致性"""
        if len(group_behaviors) < 2:
            return {'message_length': 1.0, 'activity_pattern': 1.0}
        
        # 消息长度一致性
        lengths = [b.get('avg_message_length', 0) for b in group_behaviors.values()]
        length_std = np.std(lengths)
        length_consistency = max(0, 1 - (length_std / (np.mean(lengths) + 1)))
        
        # 活跃度模式一致性（简化计算）
        activity_consistency = 0.8  # 暂时使用固定值，可扩展
        
        return {
            'message_length': length_consistency,
            'activity_pattern': activity_consistency
        }
    
    async def suggest_proactive_topics(self, group_id: str) -> Optional[str]:
        """主动话题引导"""
        try:
            current_time = time.time()
            last_guidance = self.last_topic_guidance.get(group_id, 0)
            
            # 检查是否需要主动引导（避免过于频繁）
            if current_time - last_guidance < 1800:  # 30分钟内不重复引导
                return None
            
            # 检查群组是否沉寂
            context = self.conversation_contexts.get(group_id)
            if context and (current_time - context.last_activity) < 300:  # 5分钟内有活动
                return None
            
            # 获取群组兴趣数据
            group_interests = self.group_interests.get(group_id, {})
            
            if not group_interests:
                return None
            
            # 选择合适的话题
            topic_suggestion = await self._select_engaging_topic(group_id, group_interests)
            
            if topic_suggestion:
                self.last_topic_guidance[group_id] = current_time
                return topic_suggestion
            
            return None
            
        except Exception as e:
            self._logger.error(f"话题引导失败: {e}")
            return None
    
    async def _select_engaging_topic(self, group_id: str, interests: Dict) -> Optional[str]:
        """选择吸引人的话题"""
        try:
            # 获取兴趣话题排序
            sorted_interests = sorted(interests.items(), key=lambda x: x[1], reverse=True)
            
            if not sorted_interests:
                return None
            
            # 选择top话题
            top_interest = sorted_interests[0][0]
            
            # 生成话题引导语
            topic_prompt = f"""
            基于群组成员对"{top_interest}"的兴趣，生成一个自然的话题引导句子：
            
            要求：
            1. 语气轻松自然
            2. 能够引起讨论
            3. 不要太突兀
            4. 30字以内
            
            只返回引导句子，不要其他内容。
            """
            
            if not self.llm_adapter:
                self._logger.warning("LLM适配器未配置，跳过话题选择")
                return None
            
            response = await self.llm_adapter.filter_chat_completion(
                prompt=topic_prompt
            )
            
            return response.strip() if response else None
            
        except Exception as e:
            self._logger.error(f"话题选择失败: {e}")
            return None
    
    async def _periodic_memory_sync(self):
        """定期同步跨群记忆"""
        while True:
            try:
                await asyncio.sleep(self.memory_sync_interval)
                await self._save_cross_group_memories()
            except Exception as e:
                self._logger.error(f"记忆同步失败: {e}")
    
    async def _periodic_context_cleanup(self):
        """定期清理过期上下文"""
        while True:
            try:
                await asyncio.sleep(600)  # 10分钟清理一次
                current_time = time.time()
                
                expired_contexts = [
                    group_id for group_id, context in self.conversation_contexts.items()
                    if current_time - context.last_activity > self.context_retention_time
                ]
                
                for group_id in expired_contexts:
                    del self.conversation_contexts[group_id]
                    self._logger.debug(f"清理过期对话上下文: {group_id}")
                    
            except Exception as e:
                self._logger.error(f"上下文清理失败: {e}")
    
    async def _load_cross_group_memories(self):
        """加载跨群记忆数据"""
        try:
            memory_file = os.path.join(self.config.data_dir, "cross_group_memories.json")
            if os.path.exists(memory_file):
                with open(memory_file, 'r', encoding='utf-8') as f:
                    memory_data = json.load(f)
                    
                for user_id, data in memory_data.items():
                    # 重建 CrossGroupMemory 对象
                    memory = CrossGroupMemory(
                        user_id=user_id,
                        global_profile=data.get('global_profile', {}),
                        group_behaviors=data.get('group_behaviors', {}),
                        cross_group_relationships=data.get('cross_group_relationships', []),
                        last_updated=data.get('last_updated', time.time())
                    )
                    
                    # 转换 set 类型（JSON 不支持 set）
                    for group_id, behavior in memory.group_behaviors.items():
                        if 'interaction_partners' in behavior and isinstance(behavior['interaction_partners'], list):
                            behavior['interaction_partners'] = set(behavior['interaction_partners'])
                        if 'topics_discussed' in behavior and isinstance(behavior['topics_discussed'], list):
                            behavior['topics_discussed'] = set(behavior['topics_discussed'])
                    
                    self.cross_group_memories[user_id] = memory
                    
        except Exception as e:
            self._logger.error(f"加载跨群记忆失败: {e}")
    
    async def _save_cross_group_memories(self):
        """保存跨群记忆数据"""
        try:
            memory_data = {}
            
            for user_id, memory in self.cross_group_memories.items():
                # 转换为可序列化的格式
                serializable_memory = asdict(memory)
                
                # 转换 set 为 list
                for group_id, behavior in serializable_memory['group_behaviors'].items():
                    if 'interaction_partners' in behavior and isinstance(behavior['interaction_partners'], set):
                        behavior['interaction_partners'] = list(behavior['interaction_partners'])
                    if 'topics_discussed' in behavior and isinstance(behavior['topics_discussed'], set):
                        behavior['topics_discussed'] = list(behavior['topics_discussed'])
                
                memory_data[user_id] = serializable_memory
            
            memory_file = os.path.join(self.config.data_dir, "cross_group_memories.json")
            with open(memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self._logger.error(f"保存跨群记忆失败: {e}")
    
    async def _load_group_interests(self):
        """加载群组兴趣数据"""
        try:
            interests_file = os.path.join(self.config.data_dir, "group_interests.json")
            if os.path.exists(interests_file):
                with open(interests_file, 'r', encoding='utf-8') as f:
                    self.group_interests = defaultdict(dict, json.load(f))
        except Exception as e:
            self._logger.error(f"加载群组兴趣失败: {e}")
    
    async def _save_group_interests(self):
        """保存群组兴趣数据"""
        try:
            interests_file = os.path.join(self.config.data_dir, "group_interests.json")
            with open(interests_file, 'w', encoding='utf-8') as f:
                json.dump(dict(self.group_interests), f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._logger.error(f"保存群组兴趣失败: {e}")
    
    async def get_interaction_status(self, group_id: str) -> Dict[str, Any]:
        """获取交互状态"""
        context = self.conversation_contexts.get(group_id)
        
        return {
            'has_active_context': context is not None,
            'participants_count': len(context.participants) if context else 0,
            'current_topic': context.current_topic if context else None,
            'last_activity': context.last_activity if context else 0,
            'cross_group_users': len(self.cross_group_memories),
            'group_interests_count': len(self.group_interests.get(group_id, {}))
        }