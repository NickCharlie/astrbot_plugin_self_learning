"""
智能化提升服务 - 提供情感智能、知识图谱、个性化推荐等智能化功能
"""
import asyncio
import json
import time
import os
import re
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict

import numpy as np
import networkx as nx

from astrbot.api import logger

from ..config import PluginConfig
from ..core.patterns import AsyncServiceBase
from ..utils.json_utils import safe_parse_llm_json
from ..core.interfaces import IDataStorage, IPersonaManager, ServiceLifecycle
from ..core.framework_llm_adapter import FrameworkLLMAdapter


@dataclass
class EmotionProfile:
    """情感档案"""
    user_id: str
    group_id: str
    emotion_history: List[Dict]
    dominant_emotions: Dict[str, float]
    emotion_patterns: Dict[str, Any]
    empathy_level: float
    emotional_stability: float
    last_updated: float


@dataclass
class KnowledgeEntity:
    """知识实体"""
    entity_id: str
    name: str
    entity_type: str  # person, concept, topic, etc.
    attributes: Dict[str, Any]
    relationships: List[Dict]
    confidence: float
    source_messages: List[str]
    last_mentioned: float


@dataclass
class PersonalizedRecommendation:
    """个性化推荐"""
    user_id: str
    group_id: str
    recommendation_type: str  # topic, response, activity
    content: str
    confidence: float
    reasoning: str
    timestamp: float


class IntelligenceEnhancementService(AsyncServiceBase):
    """智能化提升服务"""
    
    def __init__(self, config: PluginConfig, 
                 database_manager: IDataStorage = None, persona_manager: IPersonaManager = None,
                 llm_adapter: Optional[FrameworkLLMAdapter] = None):
        super().__init__("intelligence_enhancement")
        self.config = config
        self.llm_adapter = llm_adapter  # 使用框架适配器
        self.db_manager = database_manager
        self.persona_manager = persona_manager
        
        # 不再使用兼容性扩展，直接使用框架适配器
        # extensions = create_compatibility_extensions(config, llm_client, database_manager, persona_manager)
        # self.llm_ext = extensions['llm_client']
        # self.persona_ext = extensions['persona_manager']
        
        # 情感智能
        self.emotion_profiles: Dict[str, EmotionProfile] = {}
        self.emotion_keywords = self._load_emotion_keywords()
        
        # 知识图谱
        self.knowledge_graph: nx.DiGraph = nx.DiGraph()
        self.knowledge_entities: Dict[str, KnowledgeEntity] = {}
        self.entity_extractor_patterns = self._compile_entity_patterns()
        
        # 个性化推荐
        self.user_preferences: Dict[str, Dict] = defaultdict(dict)
        self.recommendation_cache: Dict[str, List[PersonalizedRecommendation]] = defaultdict(list)
        self.adaptive_learning_rates: Dict[str, float] = defaultdict(lambda: 0.5)
        
    async def _do_start(self) -> bool:
        """启动智能化服务"""
        try:
            await self._load_emotion_profiles()
            await self._load_knowledge_graph()
            await self._load_user_preferences()
            
            # 启动定期任务
            asyncio.create_task(self._periodic_knowledge_update())
            asyncio.create_task(self._periodic_recommendation_refresh())
            
            self._logger.info("智能化提升服务启动成功")
            return True
        except Exception as e:
            self._logger.error(f"智能化提升服务启动失败: {e}")
            return False
    
    async def _do_stop(self) -> bool:
        """停止智能化服务"""
        await self._save_emotion_profiles()
        await self._save_knowledge_graph()
        await self._save_user_preferences()
        return True
    
    def _load_emotion_keywords(self) -> Dict[str, List[str]]:
        """加载情感关键词库"""
        return {
            'joy': ['开心', '快乐', '高兴', '愉快', '兴奋', '幸福', '满足', '喜悦', '欢乐', '哈哈'],
            'sadness': ['难过', '伤心', '悲伤', '沮丧', '失望', '痛苦', '忧郁', '哭', '眼泪', '心痛'],
            'anger': ['生气', '愤怒', '恼火', '暴躁', '气愤', '愤慨', '火大', '发火', '恨', '讨厌'],
            'fear': ['害怕', '恐惧', '担心', '紧张', '焦虑', '不安', '恐慌', '忧虑', '胆怯', '惊恐'],
            'surprise': ['惊讶', '震惊', '吃惊', '意外', '惊奇', '诧异', '哇', '天啊', '不敢相信'],
            'disgust': ['恶心', '厌恶', '反感', '讨厌', '恶心', '呕吐', '排斥', '嫌弃'],
            'love': ['爱', '喜欢', '爱情', '恋爱', '亲爱', '心爱', '深爱', '爱心', '爱意', '倾慕'],
            'neutral': ['好的', '知道', '了解', '明白', '嗯', '是的', '对', '行', '可以']
        }
    
    def _compile_entity_patterns(self) -> Dict[str, re.Pattern]:
        """编译实体提取正则模式"""
        return {
            'person': re.compile(r'@(\w+)'),  # @mentions
            'time': re.compile(r'(\d{1,2}[点时]|\d{1,2}:\d{2}|明天|昨天|今天|下周|上周)'),
            'location': re.compile(r'(在|去|到)([一-龟]{2,10}?[市区县镇村路街])'),
            'number': re.compile(r'\d+[个只条件台部辆]'),
            'topic_tag': re.compile(r'#(\w+)')
        }
    
    async def analyze_emotional_intelligence(self, group_id: str, user_id: str, 
                                           message: str, context_messages: List[Dict]) -> Dict[str, Any]:
        """分析和提升情感智能"""
        try:
            # 分析当前消息的情感
            current_emotions = await self._analyze_message_emotions(message)
            
            # 分析上下文情感
            context_emotions = await self._analyze_context_emotions(context_messages)
            
            # 获取或创建用户情感档案
            profile_key = f"{group_id}_{user_id}"
            if profile_key not in self.emotion_profiles:
                # 尝试从数据库加载现有档案
                existing_profile = await self.db_manager.load_emotion_profile(group_id, user_id)
                
                if existing_profile:
                    # 从数据库重建情感档案对象
                    self.emotion_profiles[profile_key] = EmotionProfile(
                        user_id=user_id,
                        group_id=group_id,
                        emotion_history=[],  # 历史记录暂时为空，可以根据需要实现
                        dominant_emotions=existing_profile['dominant_emotions'],
                        emotion_patterns=existing_profile['emotion_patterns'],
                        empathy_level=existing_profile['empathy_level'],
                        emotional_stability=existing_profile['emotional_stability'],
                        last_updated=existing_profile['last_updated']
                    )
                else:
                    # 创建新的情感档案
                    self.emotion_profiles[profile_key] = EmotionProfile(
                        user_id=user_id,
                        group_id=group_id,
                        emotion_history=[],
                        dominant_emotions={},
                        emotion_patterns={},
                        empathy_level=0.5,
                        emotional_stability=0.5,
                        last_updated=time.time()
                    )
            
            profile = self.emotion_profiles[profile_key]
            
            # 更新情感历史
            emotion_record = {
                'timestamp': time.time(),
                'emotions': current_emotions,
                'context_emotions': context_emotions,
                'message': message[:100]  # 保存消息片段
            }
            profile.emotion_history.append(emotion_record)
            
            # 保持历史记录大小
            if len(profile.emotion_history) > 100:
                profile.emotion_history = profile.emotion_history[-100:]
            
            # 更新主导情感
            await self._update_dominant_emotions(profile)
            
            # 分析情感模式
            await self._analyze_emotion_patterns(profile)
            
            # 计算共情水平
            empathy_score = await self._calculate_empathy_level(
                current_emotions, context_emotions, profile
            )
            profile.empathy_level = empathy_score
            
            # 计算情感稳定性
            stability_score = self._calculate_emotional_stability(profile)
            profile.emotional_stability = stability_score
            
            profile.last_updated = time.time()
            
            # 生成情感智能回应建议
            emotional_response = await self._generate_emotional_response_suggestion(
                current_emotions, context_emotions, profile
            )
            
            return {
                'success': True,
                'current_emotions': current_emotions,
                'context_emotions': context_emotions,
                'empathy_level': empathy_score,
                'emotional_stability': stability_score,
                'dominant_emotions': profile.dominant_emotions,
                'emotional_response_suggestion': emotional_response
            }
            
        except Exception as e:
            self._logger.error(f"情感智能分析失败: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _analyze_message_emotions(self, message: str) -> Dict[str, float]:

        try:
            """分析消息情感"""
            emotions = {emotion: 0.0 for emotion in self.emotion_keywords.keys()}
            
            message_lower = message.lower()
            
            # 基于关键词的情感分析
            for emotion, keywords in self.emotion_keywords.items():
                score = 0.0
                for keyword in keywords:
                    if keyword in message_lower:
                        score += 1.0
                
                # 标准化得分
                emotions[emotion] = min(1.0, score / max(1, len(keywords) * 0.2))
            
            # 使用LLM进行更精确的情感分析
        
                llm_emotions = await self._llm_emotion_analysis(message)
                
                # 融合关键词和LLM分析结果
                for emotion in emotions:
                    if emotion in llm_emotions:
                        emotions[emotion] = (emotions[emotion] + llm_emotions[emotion]) / 2
                    
        except Exception as e:
            self._logger.error(f"LLM情感分析失败: {e}")
        
        return emotions
    
    async def _llm_emotion_analysis(self, message: str) -> Dict[str, float]:
        """使用LLM进行情感分析"""
        emotion_prompt = f"""
        请分析以下消息的情感倾向，为每种情感给出0-1的得分：
        
        消息: {message}
        
        情感类型：
        - joy (喜悦)
        - sadness (悲伤)  
        - anger (愤怒)
        - fear (恐惧)
        - surprise (惊讶)
        - disgust (厌恶)
        - love (爱意)
        - neutral (中性)
        
        请返回JSON格式：{{"joy": 0.0, "sadness": 0.0, ...}}
        只返回JSON，不要其他内容。
        """
        
        # 使用框架适配器进行情感分析
        if self.llm_adapter and self.llm_adapter.has_filter_provider():
            try:
                response = await self.llm_adapter.filter_chat_completion(
                    prompt=emotion_prompt,
                    temperature=0.1
                )
                if response:
                    # 使用安全的JSON解析
                    default_emotions = {}
                    return safe_parse_llm_json(response.strip(), fallback_result=default_emotions)
            except Exception as e:
                logger.warning(f"框架适配器情感识别失败: {e}")
        
        # 框架适配器不可用时返回默认结果
        return {}
    
    async def _analyze_context_emotions(self, context_messages: List[Dict]) -> Dict[str, float]:
        """分析上下文情感"""
        if not context_messages:
            return {emotion: 0.0 for emotion in self.emotion_keywords.keys()}
        
        context_emotions = defaultdict(float)
        total_messages = len(context_messages)
        
        for msg in context_messages[-5:]:  # 分析最近5条消息
            content = msg.get('message', '')
            msg_emotions = await self._analyze_message_emotions(content)
            
            for emotion, score in msg_emotions.items():
                context_emotions[emotion] += score
        
        # 计算平均情感得分
        for emotion in context_emotions:
            context_emotions[emotion] /= min(5, total_messages)
        
        return dict(context_emotions)
    
    async def _update_dominant_emotions(self, profile: EmotionProfile):
        """更新主导情感"""
        if not profile.emotion_history:
            return
        
        # 统计最近20条记录的情感
        recent_records = profile.emotion_history[-20:]
        emotion_sums = defaultdict(float)
        
        for record in recent_records:
            for emotion, score in record['emotions'].items():
                emotion_sums[emotion] += score
        
        # 计算平均得分并排序
        total_records = len(recent_records)
        for emotion in emotion_sums:
            emotion_sums[emotion] /= total_records
        
        profile.dominant_emotions = dict(sorted(emotion_sums.items(), 
                                               key=lambda x: x[1], reverse=True))
    
    async def _analyze_emotion_patterns(self, profile: EmotionProfile):
        """分析情感模式"""
        if len(profile.emotion_history) < 10:
            return
        
        patterns = {}
        
        # 分析情感变化频率
        emotion_changes = 0
        prev_dominant = None
        
        for record in profile.emotion_history[-20:]:
            current_dominant = max(record['emotions'].items(), key=lambda x: x[1])[0]
            if prev_dominant and prev_dominant != current_dominant:
                emotion_changes += 1
            prev_dominant = current_dominant
        
        patterns['emotion_change_frequency'] = emotion_changes / min(20, len(profile.emotion_history))
        
        # 分析时间模式（简化版本）
        hour_emotions = defaultdict(list)
        for record in profile.emotion_history:
            hour = datetime.fromtimestamp(record['timestamp']).hour
            dominant_emotion = max(record['emotions'].items(), key=lambda x: x[1])[0]
            hour_emotions[hour].append(dominant_emotion)
        
        patterns['time_patterns'] = {
            hour: Counter(emotions).most_common(1)[0][0]
            for hour, emotions in hour_emotions.items()
            if emotions
        }
        
        profile.emotion_patterns = patterns
    
    async def _calculate_empathy_level(self, current_emotions: Dict, 
                                     context_emotions: Dict, profile: EmotionProfile) -> float:
        """计算共情水平"""
        if not context_emotions:
            return 0.5
        
        # 计算当前情感与上下文情感的相似度
        similarity_scores = []
        
        for emotion in current_emotions:
            if emotion in context_emotions:
                current_score = current_emotions[emotion]
                context_score = context_emotions[emotion]
                
                # 如果上下文有强烈情感，用户是否能感知到
                if context_score > 0.3:
                    similarity = 1 - abs(current_score - context_score)
                    similarity_scores.append(similarity)
        
        if similarity_scores:
            return np.mean(similarity_scores)
        else:
            return 0.5
    
    def _calculate_emotional_stability(self, profile: EmotionProfile) -> float:
        """计算情感稳定性"""
        if len(profile.emotion_history) < 5:
            return 0.5
        
        # 计算情感波动程度
        emotion_variances = []
        
        for emotion in self.emotion_keywords.keys():
            scores = [record['emotions'].get(emotion, 0) for record in profile.emotion_history[-20:]]
            if scores:
                variance = np.var(scores)
                emotion_variances.append(variance)
        
        if emotion_variances:
            avg_variance = np.mean(emotion_variances)
            stability = max(0, 1 - (avg_variance * 2))  # 方差越小，稳定性越高
            return stability
        else:
            return 0.5
    
    async def _generate_emotional_response_suggestion(self, current_emotions: Dict,
                                                    context_emotions: Dict, profile: EmotionProfile) -> str:
        """生成情感智能回应建议"""
        try:
            # 确定主导情感
            dominant_current = max(current_emotions.items(), key=lambda x: x[1])
            dominant_context = max(context_emotions.items(), key=lambda x: x[1]) if context_emotions else ('neutral', 0)
            
            suggestion_prompt = f"""
            基于以下情感分析，生成一个具有情感智能的回应建议：
            
            用户当前情感: {dominant_current[0]} (强度: {dominant_current[1]:.2f})
            上下文情感: {dominant_context[0]} (强度: {dominant_context[1]:.2f})
            用户共情水平: {profile.empathy_level:.2f}
            情感稳定性: {profile.emotional_stability:.2f}
            
            主导情感倾向: {list(profile.dominant_emotions.keys())[:3]}
            
            请生成一个：
            1. 体现情感理解的回应
            2. 适合当前情感氛围
            3. 能够促进积极交流
            4. 30字以内
            
            只返回建议的回应内容，不要其他说明。
            """
            
            
            # 使用框架适配器生成情感回应建议
            if self.llm_adapter and self.llm_adapter.has_refine_provider():
                try:
                    response = await self.llm_adapter.refine_chat_completion(
                        prompt=suggestion_prompt,
                        temperature=0.7
                    )
                    if response:
                        return response.strip()
                except Exception as e:
                    self._logger.error(f"框架适配器生成情感回应建议失败: {e}")
            
            # 框架适配器不可用时的默认回应
            return ""
            
        except Exception as e:
            self._logger.error(f"情感回应建议生成失败: {e}")
            return ""
    
    async def extract_knowledge_entities(self, group_id: str, messages: List[Dict]) -> Dict[str, Any]:
        """提取知识实体并构建知识图谱"""
        try:
            extracted_entities = []
            
            for message in messages:
                content = message.get('message', '')
                sender_id = message.get('sender_id', '')
                timestamp = message.get('timestamp', time.time())
                
                # 提取不同类型的实体
                entities = await self._extract_entities_from_message(content, sender_id, timestamp)
                extracted_entities.extend(entities)
            
            # 更新知识图谱
            await self._update_knowledge_graph(group_id, extracted_entities)
            
            # 发现实体关系
            relationships = await self._discover_entity_relationships(group_id, extracted_entities)
            
            # 更新知识实体
            for entity_data in extracted_entities:
                await self._update_knowledge_entity(entity_data)
            
            return {
                'success': True,
                'entities_extracted': len(extracted_entities),
                'relationships_discovered': len(relationships),
                'graph_nodes': self.knowledge_graph.number_of_nodes(),
                'graph_edges': self.knowledge_graph.number_of_edges()
            }
            
        except Exception as e:
            self._logger.error(f"知识实体提取失败: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _extract_entities_from_message(self, content: str, sender_id: str, timestamp: float) -> List[Dict]:
        """从消息中提取实体"""
        entities = []
        try:
            # 使用正则表达式提取基础实体
            for entity_type, pattern in self.entity_extractor_patterns.items():
                matches = pattern.findall(content)
                for match in matches:
                    entity_name = match if isinstance(match, str) else match[0]
                    entities.append({
                        'name': entity_name,
                        'type': entity_type,
                        'source_message': content[:200],
                        'sender_id': sender_id,
                        'timestamp': timestamp,
                        'confidence': 0.8
                    })
            
            # 使用LLM提取更复杂的实体
        
                llm_entities = await self._llm_entity_extraction(content)
                entities.extend(llm_entities)
        except Exception as e:
            self._logger.error(f"LLM实体提取失败: {e}")
        
        return entities
    
    async def _llm_entity_extraction(self, content: str) -> List[Dict]:
        """使用LLM提取实体"""
        extraction_prompt = f"""
        从以下消息中提取重要的实体信息：
        
        消息: {content}
        
        请提取以下类型的实体：
        - 人物 (person): 具体的人名或称呼
        - 地点 (location): 具体的地理位置
        - 概念 (concept): 重要的概念或话题
        - 事件 (event): 具体的事件或活动
        - 物品 (object): 重要的物品或产品
        
        返回JSON格式：
        [
          {{"name": "实体名", "type": "类型", "confidence": 0.9}},
          ...
        ]
        
        只返回JSON数组，不要其他内容。
        """
        
        # 使用框架适配器进行实体提取
        if self.llm_adapter and self.llm_adapter.has_refine_provider():
            try:
                response = await self.llm_adapter.refine_chat_completion(
                    prompt=extraction_prompt,
                    temperature=0.1
                )
                if response:
                    # 使用安全的JSON解析
                    default_entities = []
                    entities_data = safe_parse_llm_json(response.strip(), fallback_result=default_entities)
                    
                    if entities_data and isinstance(entities_data, list):
                        return [{
                            **entity,
                            'source_message': content[:200],
                            'timestamp': time.time()
                        } for entity in entities_data]
            except Exception as e:
                logger.error(f"框架适配器实体提取失败: {e}")
        
        # 框架适配器不可用时返回默认结果
        return []
    
    async def _update_knowledge_graph(self, group_id: str, entities: List[Dict]):
        """更新知识图谱"""
        for entity in entities:
            entity_id = f"{group_id}_{entity['type']}_{entity['name']}"
            
            # 添加节点
            self.knowledge_graph.add_node(entity_id, **entity)
            
            # 如果是人物实体，与发送者建立关系
            if entity['type'] == 'person' and 'sender_id' in entity:
                sender_id = f"{group_id}_person_{entity['sender_id']}"
                self.knowledge_graph.add_edge(sender_id, entity_id, relation='mentions')
    
    async def _discover_entity_relationships(self, group_id: str, entities: List[Dict]) -> List[Dict]:
        """发现实体之间的关系"""
        relationships = []
        
        # 简单的共现关系发现
        for i, entity1 in enumerate(entities):
            for j, entity2 in enumerate(entities[i+1:], i+1):
                # 如果两个实体在同一条消息中出现
                if entity1['source_message'] == entity2['source_message']:
                    relationships.append({
                        'entity1': entity1['name'],
                        'entity2': entity2['name'],
                        'relation': 'co_occurs',
                        'confidence': min(entity1['confidence'], entity2['confidence'])
                    })
        
        return relationships
    
    async def _update_knowledge_entity(self, entity_data: Dict):
        """更新知识实体"""
        entity_id = f"{entity_data.get('type', 'unknown')}_{entity_data.get('name', 'unknown')}"
        
        if entity_id in self.knowledge_entities:
            # 更新现有实体
            entity = self.knowledge_entities[entity_id]
            entity.last_mentioned = entity_data.get('timestamp', time.time())
            entity.source_messages.append(entity_data.get('source_message', ''))
            
            # 保持源消息列表大小
            if len(entity.source_messages) > 50:
                entity.source_messages = entity.source_messages[-50:]
        else:
            # 创建新实体
            entity = KnowledgeEntity(
                entity_id=entity_id,
                name=entity_data.get('name', ''),
                entity_type=entity_data.get('type', 'unknown'),
                attributes={},
                relationships=[],
                confidence=entity_data.get('confidence', 0.5),
                source_messages=[entity_data.get('source_message', '')],
                last_mentioned=entity_data.get('timestamp', time.time())
            )
            self.knowledge_entities[entity_id] = entity
    
    async def generate_personalized_recommendations(self, group_id: str, user_id: str, 
                                                  context_data: Dict) -> List[PersonalizedRecommendation]:
        """生成个性化推荐"""
        try:
            recommendations = []
            
            # 获取用户偏好，优先从数据库加载
            user_key = f"{group_id}_{user_id}"
            if user_key not in self.user_preferences:
                # 尝试从数据库加载
                db_preferences = await self.db_manager.load_user_preferences(group_id, user_id)
                if db_preferences:
                    self.user_preferences[user_key] = db_preferences
                else:
                    self.user_preferences[user_key] = {}
            
            user_preferences = self.user_preferences.get(user_key, {})
            
            # 基于情感状态的推荐
            emotion_recommendations = await self._generate_emotion_based_recommendations(
                group_id, user_id, context_data, user_preferences
            )
            recommendations.extend(emotion_recommendations)
            
            # 基于话题兴趣的推荐
            topic_recommendations = await self._generate_topic_based_recommendations(
                group_id, user_id, context_data, user_preferences
            )
            recommendations.extend(topic_recommendations)
            
            # 基于知识图谱的推荐
            knowledge_recommendations = await self._generate_knowledge_based_recommendations(
                group_id, user_id, context_data, user_preferences
            )
            recommendations.extend(knowledge_recommendations)
            
            # 根据自适应学习率调整推荐
            adaptive_rate = self.adaptive_learning_rates.get(user_key, 0.5)
            filtered_recommendations = self._filter_recommendations_by_rate(
                recommendations, adaptive_rate
            )
            
            # 缓存推荐结果
            self.recommendation_cache[user_key] = filtered_recommendations
            
            return filtered_recommendations
            
        except Exception as e:
            self._logger.error(f"个性化推荐生成失败: {e}")
            return []
    
    async def _generate_emotion_based_recommendations(self, group_id: str, user_id: str,
                                                    context_data: Dict, preferences: Dict) -> List[PersonalizedRecommendation]:
        """基于情感状态生成推荐"""
        recommendations = []
        try:
    
            # 获取用户情感档案
            profile_key = f"{group_id}_{user_id}"
            emotion_profile = self.emotion_profiles.get(profile_key)
            
            if not emotion_profile:
                return recommendations
            
            # 根据主导情感生成推荐
            dominant_emotion = max(emotion_profile.dominant_emotions.items(), 
                                 key=lambda x: x[1])[0] if emotion_profile.dominant_emotions else 'neutral'
            
            emotion_strategies = {
                'joy': ['分享有趣内容', '参与轻松话题', '表达积极观点'],
                'sadness': ['提供安慰支持', '分享温暖内容', '避免消极话题'],
                'anger': ['保持冷静语气', '转移注意力', '提供解决方案'],
                'fear': ['给予安全感', '提供可靠信息', '表达理解支持'],
                'neutral': ['根据群组氛围调整', '分享日常话题', '保持友好态度']
            }
            
            strategies = emotion_strategies.get(dominant_emotion, emotion_strategies['neutral'])
            
            for strategy in strategies:
                recommendation = PersonalizedRecommendation(
                    user_id=user_id,
                    group_id=group_id,
                    recommendation_type='emotion_response',
                    content=strategy,
                    confidence=0.7,
                    reasoning=f"基于用户主导情感: {dominant_emotion}",
                    timestamp=time.time()
                )
                recommendations.append(recommendation)
                
        except Exception as e:
            self._logger.error(f"情感推荐生成失败: {e}")
        
        return recommendations
    
    async def _generate_topic_based_recommendations(self, group_id: str, user_id: str,
                                                  context_data: Dict, preferences: Dict) -> List[PersonalizedRecommendation]:
        """基于话题兴趣生成推荐"""
        recommendations = []
        try:
    
            # 获取用户感兴趣的话题
            interested_topics = preferences.get('favorite_topics', [])
            
            if not interested_topics:
                return recommendations
            
            # 为每个感兴趣的话题生成推荐
            for topic in interested_topics[:3]:  # 限制推荐数量
                topic_prompt = f"""
                为对"{topic}"感兴趣的用户生成一个有趣的话题引导或相关内容推荐。
                
                要求：
                1. 与话题相关且有趣
                2. 能够引发讨论
                3. 适合群聊环境
                4. 20字以内
                
                只返回推荐内容，不要其他说明。
                """
                
                # 使用框架适配器生成推荐内容
                if self.llm_adapter and self.llm_adapter.has_refine_provider():
                    try:
                        response = await self.llm_adapter.refine_chat_completion(
                            prompt=topic_prompt,
                            temperature=0.6
                        )
                        if response:
                            content = response.strip()
                        else:
                            content = f"建议您进一步了解'{topic}'相关的内容"
                    except Exception as e:
                        self._logger.error(f"框架适配器生成推荐失败: {e}")
                        content = f"建议您进一步了解'{topic}'相关的内容"
                else:
                    content = f"建议您进一步了解'{topic}'相关的内容"
                
                recommendation = PersonalizedRecommendation(
                    user_id=user_id,
                    group_id=group_id,
                    recommendation_type='topic_suggestion',
                    content=content,
                    confidence=0.8,
                    reasoning=f"基于用户对'{topic}'的兴趣",
                    timestamp=time.time()
                )
                recommendations.append(recommendation)
                
        except Exception as e:
            self._logger.error(f"话题推荐生成失败: {e}")
        
        return recommendations
    
    async def _generate_knowledge_based_recommendations(self, group_id: str, user_id: str,
                                                      context_data: Dict, preferences: Dict) -> List[PersonalizedRecommendation]:
        """基于知识图谱生成推荐"""
        recommendations = []
        try:
    
            # 获取与用户相关的知识实体
            user_entities = []
            
            for entity_id, entity in self.knowledge_entities.items():
                if group_id in entity_id and user_id in ' '.join(entity.source_messages):
                    user_entities.append(entity)
            
            # 基于用户关联的实体生成推荐
            for entity in user_entities[:2]:  # 限制数量
                related_entities = self._find_related_entities(entity)
                
                if related_entities:
                    recommendation = PersonalizedRecommendation(
                        user_id=user_id,
                        group_id=group_id,
                        recommendation_type='knowledge_extension',
                        content=f"你提到的{entity.name}，还有相关的{related_entities[0].name}值得了解",
                        confidence=0.6,
                        reasoning=f"基于知识图谱中与{entity.name}的关联",
                        timestamp=time.time()
                    )
                    recommendations.append(recommendation)
                    
        except Exception as e:
            self._logger.error(f"知识推荐生成失败: {e}")
        
        return recommendations
    
    def _find_related_entities(self, entity: KnowledgeEntity) -> List[KnowledgeEntity]:
        """查找相关实体"""
        related = []
        
        # 在知识图谱中查找相关节点
        if hasattr(self.knowledge_graph, 'neighbors'):
            try:
                neighbors = list(self.knowledge_graph.neighbors(entity.entity_id))
                for neighbor_id in neighbors[:3]:  # 限制数量
                    if neighbor_id in self.knowledge_entities:
                        related.append(self.knowledge_entities[neighbor_id])
            except:
                pass
        
        return related
    
    def _filter_recommendations_by_rate(self, recommendations: List[PersonalizedRecommendation],
                                      adaptive_rate: float) -> List[PersonalizedRecommendation]:
        """根据自适应学习率过滤推荐"""
        # 根据学习率调整推荐数量和置信度阈值
        max_recommendations = max(1, int(len(recommendations) * adaptive_rate))
        confidence_threshold = 0.5 + (adaptive_rate * 0.3)
        
        # 过滤和排序
        filtered = [
            rec for rec in recommendations
            if rec.confidence >= confidence_threshold
        ]
        
        # 按置信度排序并限制数量
        filtered.sort(key=lambda x: x.confidence, reverse=True)
        return filtered[:max_recommendations]
    
    async def update_adaptive_learning_rate(self, group_id: str, user_id: str, 
                                          feedback_data: Dict):
        """更新自适应学习速率"""
        user_key = f"{group_id}_{user_id}"
        current_rate = self.adaptive_learning_rates.get(user_key, 0.5)
        
        # 根据反馈调整学习率
        feedback_score = feedback_data.get('success_rate', 0.5)
        user_activity = feedback_data.get('activity_level', 0.5)
        data_quality = feedback_data.get('data_quality', 0.5)
        
        # 计算新的学习率
        adjustment = (feedback_score + user_activity + data_quality) / 3
        new_rate = (current_rate + adjustment) / 2  # 平滑调整
        
        # 限制在合理范围内
        self.adaptive_learning_rates[user_key] = max(0.1, min(1.0, new_rate))
    
    async def _periodic_knowledge_update(self):
        """定期更新知识图谱"""
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时更新一次
                
                # 清理过期实体
                current_time = time.time()
                expired_entities = []
                
                for entity_id, entity in self.knowledge_entities.items():
                    if current_time - entity.last_mentioned > 86400 * 7:  # 7天未提及
                        expired_entities.append(entity_id)
                
                for entity_id in expired_entities:
                    del self.knowledge_entities[entity_id]
                    if self.knowledge_graph.has_node(entity_id):
                        self.knowledge_graph.remove_node(entity_id)
                
                self._logger.info(f"清理过期知识实体: {len(expired_entities)}")
                
            except Exception as e:
                self._logger.error(f"知识图谱更新失败: {e}")
    
    async def _periodic_recommendation_refresh(self):
        """定期刷新推荐缓存"""
        while True:
            try:
                await asyncio.sleep(1800)  # 30分钟刷新一次
                
                # 清理过期推荐
                current_time = time.time()
                for user_key in list(self.recommendation_cache.keys()):
                    recommendations = self.recommendation_cache[user_key]
                    fresh_recommendations = [
                        rec for rec in recommendations
                        if current_time - rec.timestamp < 3600  # 1小时内的推荐
                    ]
                    
                    if fresh_recommendations:
                        self.recommendation_cache[user_key] = fresh_recommendations
                    else:
                        del self.recommendation_cache[user_key]
                
            except Exception as e:
                self._logger.error(f"推荐缓存刷新失败: {e}")
    
    async def _load_emotion_profiles(self):
        """加载情感档案"""
        try:
            # 使用数据库管理器的方法而不是文件存储
            # 这里可以根据需要实现批量加载逻辑
            self._logger.info("情感档案将从数据库动态加载")
        except Exception as e:
            self._logger.error(f"加载情感档案失败: {e}")
    
    async def _save_emotion_profiles(self):
        """保存情感档案"""
        try:
            # 使用数据库管理器保存情感档案
            for profile_key, profile in self.emotion_profiles.items():
                parts = profile_key.split('_', 1)
                if len(parts) == 2:
                    group_id, user_id = parts
                    profile_data = {
                        'dominant_emotions': profile.dominant_emotions,
                        'emotion_patterns': profile.emotion_patterns,
                        'empathy_level': profile.empathy_level,
                        'emotional_stability': profile.emotional_stability,
                        'last_updated': profile.last_updated
                    }
                    await self.db_manager.save_emotion_profile(group_id, user_id, profile_data)
                    
        except Exception as e:
            self._logger.error(f"保存情感档案失败: {e}")
    
    async def _load_knowledge_graph(self):
        """加载知识图谱"""
        try:
            graph_file = os.path.join(self.config.data_dir, "knowledge_graph.json")
            if os.path.exists(graph_file):
                with open(graph_file, 'r', encoding='utf-8') as f:
                    graph_data = json.load(f)
                    
                # 重建NetworkX图
                self.knowledge_graph = nx.node_link_graph(graph_data)
            
            # 加载知识实体
            entities_file = os.path.join(self.config.data_dir, "knowledge_entities.json")
            if os.path.exists(entities_file):
                with open(entities_file, 'r', encoding='utf-8') as f:
                    entities_data = json.load(f)
                    
                for entity_id, data in entities_data.items():
                    entity = KnowledgeEntity(
                        entity_id=entity_id,
                        name=data.get('name', ''),
                        entity_type=data.get('entity_type', 'unknown'),
                        attributes=data.get('attributes', {}),
                        relationships=data.get('relationships', []),
                        confidence=data.get('confidence', 0.5),
                        source_messages=data.get('source_messages', []),
                        last_mentioned=data.get('last_mentioned', time.time())
                    )
                    self.knowledge_entities[entity_id] = entity
                    
        except Exception as e:
            self._logger.error(f"加载知识图谱失败: {e}")
    
    async def _save_knowledge_graph(self):
        """保存知识图谱"""
        try:
            # 保存NetworkX图
            graph_data = nx.node_link_data(self.knowledge_graph)
            graph_file = os.path.join(self.config.data_dir, "knowledge_graph.json")
            with open(graph_file, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)
            
            # 保存知识实体
            entities_data = {}
            for entity_id, entity in self.knowledge_entities.items():
                entities_data[entity_id] = asdict(entity)
            
            entities_file = os.path.join(self.config.data_dir, "knowledge_entities.json")
            with open(entities_file, 'w', encoding='utf-8') as f:
                json.dump(entities_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self._logger.error(f"保存知识图谱失败: {e}")
    
    async def _load_user_preferences(self):
        """加载用户偏好"""
        try:
            # 使用数据库管理器的方法而不是文件存储
            self._logger.info("用户偏好将从数据库动态加载")
        except Exception as e:
            self._logger.error(f"加载用户偏好失败: {e}")
    
    async def _save_user_preferences(self):
        """保存用户偏好"""
        try:
            # 使用数据库管理器保存用户偏好
            for user_key, preferences in self.user_preferences.items():
                parts = user_key.split('_', 1)
                if len(parts) == 2:
                    group_id, user_id = parts
                    await self.db_manager.save_user_preferences(group_id, user_id, preferences)
                    
        except Exception as e:
            self._logger.error(f"保存用户偏好失败: {e}")
    
    async def get_intelligence_status(self, group_id: str) -> Dict[str, Any]:
        """获取智能化状态"""
        return {
            'emotion_profiles_count': len(self.emotion_profiles),
            'knowledge_entities_count': len(self.knowledge_entities),
            'knowledge_graph_nodes': self.knowledge_graph.number_of_nodes(),
            'knowledge_graph_edges': self.knowledge_graph.number_of_edges(),
            'user_preferences_count': len(self.user_preferences),
            'cached_recommendations': len(self.recommendation_cache),
            'adaptive_learning_rates': dict(self.adaptive_learning_rates)
        }