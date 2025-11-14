"""
消息对应关系分析器 - 基于AstrBot框架的智能消息关系判断服务
"""
import asyncio
import time
import json
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context

from ..config import PluginConfig
from ..core.framework_llm_adapter import FrameworkLLMAdapter
from ..exceptions import MessageAnalysisError
from ..utils.json_utils import safe_parse_llm_json


@dataclass
class MessageRelationship:
    """消息关系"""
    sender_message_id: str
    sender_content: str
    sender_timestamp: float
    reply_message_id: str
    reply_content: str
    reply_timestamp: float
    confidence: float  # 0.0-1.0 置信度
    relationship_type: str  # 'direct_reply', 'topic_continuation', 'unrelated'
    analysis_reason: str


@dataclass
class ConversationContext:
    """对话上下文"""
    messages: List[Dict[str, Any]]
    time_window: float = 300.0  # 5分钟内的消息认为是连续对话
    max_messages: int = 20  # 最多分析20条消息


class MessageRelationshipAnalyzer:
    """消息对应关系分析器"""
    
    def __init__(self, config: PluginConfig, context: Context, 
                 llm_adapter: Optional[FrameworkLLMAdapter] = None):
        self.config = config
        self.context = context
        self.llm_adapter = llm_adapter
        
        # 分析缓存，避免重复分析
        self.analysis_cache = {}
        self.cache_ttl = 3600  # 缓存1小时
        
        # 简单规则匹配模式
        self.simple_patterns = {
            'direct_reply_keywords': [
                '是的', '不是', '对', '错', '没有', '有的', '好的', '不好',
                '可以', '不可以', '同意', '不同意', '赞成', '反对',
                '嗯', '哦', '额', '呃', '啊', '哈哈', '笑死'
            ],
            'question_indicators': [
                '?', '？', '什么', '怎么', '为什么', '哪里', '哪个',
                '是不是', '对不对', '好不好', '行不行', '可以吗'
            ],
            'topic_keywords': [
                '关于', '说到', '提到', '刚才', '之前', '刚刚',
                '对了', '还有', '另外', '顺便'
            ]
        }
        
        logger.info("消息对应关系分析器初始化完成")

    async def analyze_message_relationships(self, 
                                          conversation_messages: List[Dict[str, Any]],
                                          group_id: str) -> List[MessageRelationship]:
        """
        分析一组消息的对应关系
        
        Args:
            conversation_messages: 消息列表，按时间排序
            group_id: 群组ID
            
        Returns:
            消息关系列表
        """
        try:
            if len(conversation_messages) < 2:
                logger.debug("消息数量不足，无需分析关系")
                return []
                
            # 创建对话上下文
            context = ConversationContext(
                messages=conversation_messages[-self.config.max_messages_per_batch:],
                time_window=300.0,  # 5分钟
                max_messages=20
            )
            
            relationships = []
            
            # 逐对分析相邻消息的关系
            for i in range(1, len(context.messages)):
                prev_msg = context.messages[i-1]
                curr_msg = context.messages[i]
                
                # 检查时间间隔
                time_diff = curr_msg.get('timestamp', 0) - prev_msg.get('timestamp', 0)
                if time_diff > context.time_window:
                    logger.debug(f"消息时间间隔过长 ({time_diff}s)，跳过关系分析")
                    continue
                
                # 跳过同一用户的连续消息
                if prev_msg.get('sender_id') == curr_msg.get('sender_id'):
                    continue
                    
                # 分析消息关系
                relationship = await self._analyze_message_pair(prev_msg, curr_msg, group_id)
                if relationship:
                    relationships.append(relationship)
            
            # 分析更复杂的多消息关系
            complex_relationships = await self._analyze_complex_relationships(
                context.messages, group_id
            )
            relationships.extend(complex_relationships)
            
            logger.info(f"群组 {group_id} 分析了 {len(context.messages)} 条消息，发现 {len(relationships)} 个消息关系")
            return relationships
            
        except Exception as e:
            logger.error(f"分析消息关系失败: {e}")
            raise MessageAnalysisError(f"消息关系分析失败: {str(e)}")

    async def _analyze_message_pair(self, msg1: Dict[str, Any], msg2: Dict[str, Any], 
                                   group_id: str) -> Optional[MessageRelationship]:
        """分析两条消息之间的关系"""
        try:
            # 生成缓存键
            cache_key = f"{msg1.get('message_id', '')}_{msg2.get('message_id', '')}"
            
            # 检查缓存
            if cache_key in self.analysis_cache:
                cached_result = self.analysis_cache[cache_key]
                if time.time() - cached_result['timestamp'] < self.cache_ttl:
                    return cached_result['result']
            
            # 首先使用简单规则
            simple_result = self._simple_rule_analysis(msg1, msg2)
            
            # 如果简单规则置信度足够高，直接返回
            if simple_result and simple_result.confidence > 0.8:
                self._cache_result(cache_key, simple_result)
                return simple_result
            
            # 使用LLM进行深度分析
            if self.llm_adapter and self.llm_adapter.has_filter_provider():
                llm_result = await self._llm_relationship_analysis(msg1, msg2, group_id)
                if llm_result:
                    self._cache_result(cache_key, llm_result)
                    return llm_result
            
            # 返回简单规则结果或None
            if simple_result:
                self._cache_result(cache_key, simple_result)
                return simple_result
                
            return None
            
        except Exception as e:
            logger.error(f"分析消息对关系失败: {e}")
            return None

    def _simple_rule_analysis(self, msg1: Dict[str, Any], msg2: Dict[str, Any]) -> Optional[MessageRelationship]:
        """使用简单规则分析消息关系"""
        try:
            content1 = msg1.get('message', '').strip().lower()
            content2 = msg2.get('message', '').strip().lower()
            
            if not content1 or not content2:
                return None
                
            confidence = 0.0
            relationship_type = 'unrelated'
            reason = '未找到明确关系'
            
            # 1. 直接回复检测
            direct_reply_score = self._check_direct_reply(content1, content2)
            if direct_reply_score > 0.5:
                confidence = direct_reply_score
                relationship_type = 'direct_reply'
                reason = '检测到直接回复模式'
            
            # 2. 主题连续性检测
            elif self._check_topic_continuation(content1, content2):
                confidence = 0.6
                relationship_type = 'topic_continuation'
                reason = '检测到主题连续性'
            
            # 3. 问答模式检测
            elif self._check_question_answer_pattern(content1, content2):
                confidence = 0.7
                relationship_type = 'direct_reply'
                reason = '检测到问答模式'
            
            # 4. 时间邻近性加分
            time_diff = msg2.get('timestamp', 0) - msg1.get('timestamp', 0)
            if time_diff < 30:  # 30秒内
                confidence += 0.1
            elif time_diff < 120:  # 2分钟内
                confidence += 0.05
                
            # 只返回有意义的关系
            if confidence > 0.3:
                return MessageRelationship(
                    sender_message_id=msg1.get('message_id', ''),
                    sender_content=msg1.get('message', ''),
                    sender_timestamp=msg1.get('timestamp', 0),
                    reply_message_id=msg2.get('message_id', ''),
                    reply_content=msg2.get('message', ''),
                    reply_timestamp=msg2.get('timestamp', 0),
                    confidence=min(confidence, 1.0),
                    relationship_type=relationship_type,
                    analysis_reason=reason
                )
            
            return None
            
        except Exception as e:
            logger.error(f"简单规则分析失败: {e}")
            return None

    def _check_direct_reply(self, content1: str, content2: str) -> float:
        """检查是否为直接回复"""
        score = 0.0
        
        # 检查直接回复关键词
        for keyword in self.simple_patterns['direct_reply_keywords']:
            if content2.startswith(keyword):
                score += 0.3
                break
                
        # 检查是否包含第一条消息的关键词
        words1 = set(content1.split())
        words2 = set(content2.split())
        common_words = words1.intersection(words2)
        if len(common_words) > 0:
            score += len(common_words) * 0.1
            
        # 检查长度相关性（短回复通常是直接回复）
        if len(content2) <= 10 and len(content1) > 5:
            score += 0.2
            
        return min(score, 1.0)

    def _check_topic_continuation(self, content1: str, content2: str) -> bool:
        """检查主题连续性"""
        for keyword in self.simple_patterns['topic_keywords']:
            if keyword in content2:
                return True
        return False

    def _check_question_answer_pattern(self, content1: str, content2: str) -> bool:
        """检查问答模式"""
        # 第一条消息是问题
        is_question = any(indicator in content1 for indicator in self.simple_patterns['question_indicators'])
        
        # 第二条消息看起来是回答
        is_answer = not any(indicator in content2 for indicator in self.simple_patterns['question_indicators'])
        
        return is_question and is_answer

    async def _llm_relationship_analysis(self, msg1: Dict[str, Any], msg2: Dict[str, Any], 
                                       group_id: str) -> Optional[MessageRelationship]:
        """使用LLM进行深度关系分析"""
        try:
            if not self.llm_adapter or not self.llm_adapter.has_filter_provider():
                return None
                
            # 构建分析prompt
            prompt = self._build_relationship_analysis_prompt(msg1, msg2)
            
            # 调用LLM
            response = await self.llm_adapter.filter_chat_completion(
                prompt=prompt,
                system_prompt="你是一个专业的对话关系分析专家。请分析两条消息之间的对应关系。"
            )
            
            if not response:
                return None
                
            # 解析LLM响应
            analysis_result = safe_parse_llm_json(response)
            if not analysis_result or 'relationship_type' not in analysis_result:
                logger.warning("LLM返回格式不正确，使用简单规则分析")
                return None
                
            return MessageRelationship(
                sender_message_id=msg1.get('message_id', ''),
                sender_content=msg1.get('message', ''),
                sender_timestamp=msg1.get('timestamp', 0),
                reply_message_id=msg2.get('message_id', ''),
                reply_content=msg2.get('message', ''),
                reply_timestamp=msg2.get('timestamp', 0),
                confidence=analysis_result.get('confidence', 0.5),
                relationship_type=analysis_result.get('relationship_type', 'unrelated'),
                analysis_reason=analysis_result.get('reason', 'LLM分析结果')
            )
            
        except Exception as e:
            logger.error(f"LLM关系分析失败: {e}")
            return None

    def _build_relationship_analysis_prompt(self, msg1: Dict[str, Any], msg2: Dict[str, Any]) -> str:
        """构建关系分析prompt"""
        time1 = datetime.fromtimestamp(msg1.get('timestamp', 0)).strftime('%H:%M:%S')
        time2 = datetime.fromtimestamp(msg2.get('timestamp', 0)).strftime('%H:%M:%S')
        
        prompt = f"""
请分析以下两条群聊消息之间的对应关系：

消息A [{time1}] 用户{hash(msg1.get('sender_id', '')) % 100:02d}: {msg1.get('message', '')}
消息B [{time2}] 用户{hash(msg2.get('sender_id', '')) % 100:02d}: {msg2.get('message', '')}

请判断消息B是否是对消息A的回复，以及它们的关系类型。

返回JSON格式结果：
{{
    "relationship_type": "direct_reply|topic_continuation|unrelated",
    "confidence": 0.0-1.0,
    "reason": "分析原因说明"
}}

关系类型说明：
- direct_reply: 消息B直接回应消息A的内容
- topic_continuation: 消息B延续了消息A的话题，但不是直接回复
- unrelated: 两条消息没有明显关系

请只返回JSON，不要其他内容。
"""
        return prompt

    async def _analyze_complex_relationships(self, messages: List[Dict[str, Any]], 
                                           group_id: str) -> List[MessageRelationship]:
        """分析复杂的多消息关系（如跨多条消息的问答）"""
        relationships = []
        
        try:
            # 寻找问题和延迟回答的模式
            for i, msg in enumerate(messages):
                content = msg.get('message', '').strip().lower()
                
                # 检查是否是问题
                if any(indicator in content for indicator in self.simple_patterns['question_indicators']):
                    # 在后续消息中寻找可能的回答
                    for j in range(i + 1, min(i + 6, len(messages))):  # 最多向后看5条消息
                        candidate_msg = messages[j]
                        
                        # 跳过同一用户的消息
                        if msg.get('sender_id') == candidate_msg.get('sender_id'):
                            continue
                            
                        # 时间间隔检查
                        time_diff = candidate_msg.get('timestamp', 0) - msg.get('timestamp', 0)
                        if time_diff > 300:  # 超过5分钟
                            break
                            
                        # 检查是否可能是回答
                        if self._could_be_delayed_answer(msg, candidate_msg):
                            relationship = MessageRelationship(
                                sender_message_id=msg.get('message_id', ''),
                                sender_content=msg.get('message', ''),
                                sender_timestamp=msg.get('timestamp', 0),
                                reply_message_id=candidate_msg.get('message_id', ''),
                                reply_content=candidate_msg.get('message', ''),
                                reply_timestamp=candidate_msg.get('timestamp', 0),
                                confidence=0.4,  # 较低置信度
                                relationship_type='direct_reply',
                                analysis_reason='延迟回答模式'
                            )
                            relationships.append(relationship)
                            break
                            
        except Exception as e:
            logger.error(f"分析复杂关系失败: {e}")
            
        return relationships

    def _could_be_delayed_answer(self, question_msg: Dict[str, Any], 
                                answer_msg: Dict[str, Any]) -> bool:
        """检查是否可能是延迟回答"""
        question_content = question_msg.get('message', '').strip().lower()
        answer_content = answer_msg.get('message', '').strip().lower()
        
        # 检查答案是否包含问题中的关键词
        question_words = set(question_content.split())
        answer_words = set(answer_content.split())
        common_words = question_words.intersection(answer_words)
        
        if len(common_words) >= 2:  # 至少2个共同词
            return True
            
        # 检查是否是典型的回答模式
        answer_indicators = ['我觉得', '应该是', '可能是', '不知道', '不清楚', '没有', '有的']
        if any(indicator in answer_content for indicator in answer_indicators):
            return True
            
        return False

    def _cache_result(self, cache_key: str, result: MessageRelationship):
        """缓存分析结果"""
        self.analysis_cache[cache_key] = {
            'result': result,
            'timestamp': time.time()
        }
        
        # 清理过期缓存
        if len(self.analysis_cache) > 1000:  # 限制缓存大小
            current_time = time.time()
            expired_keys = [
                key for key, value in self.analysis_cache.items()
                if current_time - value['timestamp'] > self.cache_ttl
            ]
            for key in expired_keys:
                del self.analysis_cache[key]

    async def get_conversation_pairs(self, relationships: List[MessageRelationship]) -> List[Tuple[str, str]]:
        """
        从关系分析结果中提取对话对
        
        Returns:
            List[Tuple[str, str]]: (发送消息内容, 回复消息内容) 的列表
        """
        pairs = []
        
        for rel in relationships:
            if rel.relationship_type == 'direct_reply' and rel.confidence > 0.5:
                pairs.append((rel.sender_content, rel.reply_content))
                
        logger.info(f"从 {len(relationships)} 个关系中提取了 {len(pairs)} 个对话对")
        return pairs

    async def analyze_conversation_quality(self, relationships: List[MessageRelationship]) -> Dict[str, Any]:
        """分析对话质量"""
        if not relationships:
            return {
                'total_relationships': 0,
                'avg_confidence': 0.0,
                'direct_replies': 0,
                'topic_continuations': 0,
                'quality_score': 0.0
            }
            
        total = len(relationships)
        avg_confidence = sum(rel.confidence for rel in relationships) / total
        direct_replies = sum(1 for rel in relationships if rel.relationship_type == 'direct_reply')
        topic_continuations = sum(1 for rel in relationships if rel.relationship_type == 'topic_continuation')
        
        # 计算质量得分
        quality_score = (
            avg_confidence * 0.4 +  # 置信度权重
            (direct_replies / total) * 0.4 +  # 直接回复比例权重
            (topic_continuations / total) * 0.2  # 主题连续性权重
        )
        
        return {
            'total_relationships': total,
            'avg_confidence': avg_confidence,
            'direct_replies': direct_replies,
            'topic_continuations': topic_continuations,
            'quality_score': quality_score,
            'analysis_details': [
                {
                    'type': rel.relationship_type,
                    'confidence': rel.confidence,
                    'reason': rel.analysis_reason
                } for rel in relationships
            ]
        }