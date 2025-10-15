"""
高级学习机制服务 - 实现场景切换、情境感知、对抗性学习等高级功能
"""
import asyncio
import json
import time
import os
import random
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import deque, defaultdict

from astrbot.api import logger

try:
    from ..config import PluginConfig
except ImportError:
    from astrbot_plugin_self_learning.config import PluginConfig

try:
    from ..core.patterns import AsyncServiceBase
except ImportError:
    from astrbot_plugin_self_learning.core.patterns import AsyncServiceBase

try:
    from ..core.interfaces import IDataStorage, IPersonaManager
except ImportError:
    from astrbot_plugin_self_learning.core.interfaces import IDataStorage, IPersonaManager

try:
    from ..core.framework_llm_adapter import FrameworkLLMAdapter
except ImportError:
    from astrbot_plugin_self_learning.core.framework_llm_adapter import FrameworkLLMAdapter

try:
    from ..exceptions import LearningError
except ImportError:
    from astrbot_plugin_self_learning.exceptions import LearningError


class AdvancedLearningService(AsyncServiceBase):
    """高级学习机制服务"""
    
    def __init__(self, config: PluginConfig, 
                 database_manager: IDataStorage = None, persona_manager: IPersonaManager = None,
                 llm_adapter: Optional[FrameworkLLMAdapter] = None):
        super().__init__("advanced_learning")
        self.config = config
        self.llm_adapter = llm_adapter  # 使用框架适配器
        self.db_manager = database_manager
        self.persona_manager = persona_manager
        
        # 不再使用兼容性扩展，直接使用框架适配器
        # extensions = create_compatibility_extensions(config, llm_client, database_manager, persona_manager)
        # self.llm_ext = extensions['llm_client']
        # self.persona_ext = extensions['persona_manager']
        
        # 人格切换管理
        self.persona_contexts = {}  # group_id -> context_type -> persona_config
        self.current_contexts = {}  # group_id -> current_context
        
        # 情境感知学习
        self.context_analyzers = {}
        self.situation_memory = defaultdict(deque)  # 滑动窗口存储情境
        
        # 对抗性学习
        self.adversarial_samples = defaultdict(list)
        self.overfitting_indicators = defaultdict(float)
        
        # 增量学习
        self.incremental_vocabulary = defaultdict(set)
        self.learning_momentum = defaultdict(float)
        
    async def _do_start(self) -> bool:
        """启动高级学习服务"""
        try:
            await self._initialize_persona_contexts()
            await self._load_incremental_vocabulary()
            self._logger.info("高级学习服务启动成功")
            return True
        except Exception as e:
            self._logger.error(f"高级学习服务启动失败: {e}")
            return False
    
    async def _do_stop(self) -> bool:
        """停止高级学习服务"""
        await self._save_incremental_vocabulary()
        return True
    
    async def _initialize_persona_contexts(self):
        """初始化人格切换上下文"""
        # 定义不同场景下的人格配置
        self.default_persona_contexts = {
            "serious": {
                "name": "严肃模式",
                "description": "正式、理性、逻辑性强的交流方式",
                "style_adjustments": {
                    "formality": 0.8,
                    "emotional_intensity": 0.3,
                    "creativity": 0.4,
                    "vocabulary_complexity": 0.7
                }
            },
            "casual": {
                "name": "轻松模式", 
                "description": "轻松、友好、活泼的交流方式",
                "style_adjustments": {
                    "formality": 0.3,
                    "emotional_intensity": 0.7,
                    "creativity": 0.8,
                    "vocabulary_complexity": 0.4
                }
            },
            "supportive": {
                "name": "支持模式",
                "description": "温暖、理解、鼓励的交流方式",
                "style_adjustments": {
                    "formality": 0.5,
                    "emotional_intensity": 0.8,
                    "creativity": 0.6,
                    "empathy": 0.9
                }
            },
            "analytical": {
                "name": "分析模式",
                "description": "深入、客观、系统性的分析交流",
                "style_adjustments": {
                    "formality": 0.7,
                    "emotional_intensity": 0.2,
                    "creativity": 0.5,
                    "logical_structure": 0.9
                }
            }
        }
    
    async def detect_and_switch_context(self, group_id: str, message: str, 
                                      sender_id: str, chat_history: List[Dict]) -> Optional[str]:
        """检测情境并切换人格"""
        try:
            # 分析当前消息的情境
            current_context = await self._analyze_message_context(message, chat_history)
            
            # 检查是否需要切换人格
            last_context = self.current_contexts.get(group_id, "casual")
            
            if current_context != last_context:
                # 执行人格切换
                await self._switch_persona_context(group_id, current_context)
                self.current_contexts[group_id] = current_context
                
                self._logger.info(f"群组 {group_id} 人格切换: {last_context} -> {current_context}")
                return current_context
            
            return None
            
        except Exception as e:
            self._logger.error(f"情境检测和切换失败: {e}")
            return None
    
    async def _analyze_message_context(self, message: str, chat_history: List[Dict]) -> str:
        """分析消息的情境上下文"""
        try:
            # 构建情境分析提示
            context_analysis_prompt = f"""
            请分析以下消息的情境类型，选择最合适的情境：
            
            消息内容: {message}
            
            历史对话摘要: {self._summarize_chat_history(chat_history)}
            
            可选情境类型：
            1. serious - 严肃/正式讨论（工作、学习、重要决策等）
            2. casual - 轻松/日常聊天（闲聊、娱乐、轻松话题等）
            3. supportive - 需要支持/安慰（求助、分享困难、需要鼓励等）
            4. analytical - 深度分析/讨论（技术问题、复杂分析、学术讨论等）
            
            只返回情境类型的英文标识符，不要其他内容。
            """
            
            response = await self.llm_ext.generate_response(
                context_analysis_prompt,
                model_name='gpt-4o'  # 使用默认模型名
            )
            
            detected_context = response.strip().lower()
            
            # 验证返回的情境类型
            if detected_context in self.default_persona_contexts:
                return detected_context
            else:
                return "casual"  # 默认返回轻松模式
                
        except Exception as e:
            self._logger.error(f"情境分析失败: {e}")
            return "casual"
    
    def _summarize_chat_history(self, chat_history: List[Dict], max_messages: int = 5) -> str:
        """总结对话历史"""
        if not chat_history:
            return "无历史对话"
        
        recent_messages = chat_history[-max_messages:]
        summary_parts = []
        
        for msg in recent_messages:
            content = msg.get('message', '')
            sender = msg.get('sender_name', '用户')
            summary_parts.append(f"{sender}: {content[:50]}...")
        
        return " | ".join(summary_parts)
    
    async def _switch_persona_context(self, group_id: str, context_type: str):
        """切换人格上下文"""
        try:
            context_config = self.default_persona_contexts.get(context_type)
            if not context_config:
                return
            
            # 获取当前人格配置
            current_persona = await self.persona_ext.get_current_persona(group_id)
            
            if not current_persona:
                return
            
            # 应用情境调整
            adjusted_persona = self._apply_context_adjustments(
                current_persona, 
                context_config['style_adjustments']
            )
            
            # 临时保存调整后的人格（不覆盖原始人格）
            self.persona_contexts[group_id] = {
                'context_type': context_type,
                'original_persona': current_persona,
                'adjusted_persona': adjusted_persona,
                'switch_time': time.time()
            }
            
        except Exception as e:
            self._logger.error(f"人格上下文切换失败: {e}")
    
    def _apply_context_adjustments(self, persona: Dict, adjustments: Dict) -> Dict:
        """应用情境调整到人格配置"""
        adjusted_persona = persona.copy()
        style_profile = adjusted_persona.get('style_profile', {})
        
        # 应用风格调整
        for key, adjustment_value in adjustments.items():
            if key in style_profile:
                # 使用加权平均进行调整
                original_value = style_profile[key]
                adjusted_value = (original_value + adjustment_value) / 2
                style_profile[key] = max(0, min(1, adjusted_value))
        
        adjusted_persona['style_profile'] = style_profile
        return adjusted_persona
    
    async def apply_situation_aware_learning(self, group_id: str, messages: List[Dict]) -> Dict[str, Any]:
        """情境感知学习"""
        try:
            learning_results = []
            
            for message in messages:
                timestamp = message.get('timestamp', time.time())
                dt = datetime.fromtimestamp(timestamp)
                
                # 分析时间情境
                time_context = self._analyze_time_context(dt)
                
                # 分析群体氛围情境
                group_atmosphere = await self._analyze_group_atmosphere(group_id, message, messages)
                
                # 分析话题情境
                topic_context = await self._analyze_topic_context(message, messages)
                
                # 综合情境信息
                situation_context = {
                    'time_context': time_context,
                    'group_atmosphere': group_atmosphere,
                    'topic_context': topic_context,
                    'timestamp': timestamp
                }
                
                # 基于情境调整学习策略
                learning_adjustment = self._calculate_learning_adjustment(situation_context)
                
                learning_results.append({
                    'message_id': message.get('id'),
                    'situation_context': situation_context,
                    'learning_weight': learning_adjustment['weight'],
                    'priority_score': learning_adjustment['priority']
                })
                
                # 存储情境记忆
                self.situation_memory[group_id].append(situation_context)
                if len(self.situation_memory[group_id]) > 100:  # 保持滑动窗口大小
                    self.situation_memory[group_id].popleft()
            
            return {
                'success': True,
                'learning_results': learning_results,
                'context_summary': self._summarize_situation_context(group_id)
            }
            
        except Exception as e:
            self._logger.error(f"情境感知学习失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _analyze_time_context(self, dt: datetime) -> Dict[str, Any]:
        """分析时间情境"""
        hour = dt.hour
        weekday = dt.weekday()  # 0=Monday
        
        time_periods = {
            'early_morning': (5, 8),
            'morning': (8, 12),
            'afternoon': (12, 18),
            'evening': (18, 22),
            'night': (22, 24),
            'late_night': (0, 5)
        }
        
        period = 'unknown'
        for name, (start, end) in time_periods.items():
            if start <= hour < end:
                period = name
                break
        
        return {
            'period': period,
            'hour': hour,
            'weekday': weekday,
            'is_weekend': weekday >= 5,
            'is_work_time': 9 <= hour <= 17 and weekday < 5
        }
    
    async def _analyze_group_atmosphere(self, group_id: str, current_message: Dict, 
                                      recent_messages: List[Dict]) -> Dict[str, Any]:
        """分析群体氛围"""
        try:
            # 分析最近消息的情感倾向
            emotions = []
            message_intervals = []
            
            for i, msg in enumerate(recent_messages[-10:]):  # 分析最近10条消息
                content = msg.get('message', '')
                timestamp = msg.get('timestamp', time.time())
                
                # 简单的情感分析（可以后续升级为更复杂的模型）
                emotion_score = await self._analyze_message_emotion(content)
                emotions.append(emotion_score)
                
                # 计算消息间隔
                if i > 0:
                    prev_timestamp = recent_messages[-(11-i)].get('timestamp', timestamp)
                    interval = timestamp - prev_timestamp
                    message_intervals.append(interval)
            
            # 计算氛围指标
            avg_emotion = np.mean(emotions) if emotions else 0.5
            message_frequency = 1.0 / (np.mean(message_intervals) + 1) if message_intervals else 0.1
            
            atmosphere_type = "neutral"
            if avg_emotion > 0.7:
                atmosphere_type = "positive"
            elif avg_emotion < 0.3:
                atmosphere_type = "negative"
            
            if message_frequency > 0.01:  # 高频消息
                atmosphere_type += "_active"
            
            return {
                'type': atmosphere_type,
                'emotion_score': avg_emotion,
                'activity_level': message_frequency,
                'participant_count': len(set(msg.get('sender_id') for msg in recent_messages[-10:]))
            }
            
        except Exception as e:
            self._logger.error(f"群体氛围分析失败: {e}")
            return {'type': 'neutral', 'emotion_score': 0.5, 'activity_level': 0.1}
    
    async def _analyze_message_emotion(self, content: str) -> float:
        """分析消息情感（简单实现，可扩展）"""
        # 简单的情感词典方法
        positive_words = ['开心', '快乐', '好的', '棒', '优秀', '赞', '哈哈', '笑', '爱', '喜欢']
        negative_words = ['难过', '生气', '烦', '糟糕', '差', '恨', '讨厌', '愤怒', '失望']
        
        positive_count = sum(1 for word in positive_words if word in content)
        negative_count = sum(1 for word in negative_words if word in content)
        
        if positive_count + negative_count == 0:
            return 0.5  # 中性
        
        return positive_count / (positive_count + negative_count)
    
    async def _analyze_topic_context(self, message: Dict, recent_messages: List[Dict]) -> Dict[str, Any]:
        """分析话题情境"""
        content = message.get('message', '')
        
        # 简单的话题分类（可扩展为更复杂的主题模型）
        topic_keywords = {
            'technical': ['技术', '代码', '编程', '算法', '数据', '系统', '开发'],
            'personal': ['我', '心情', '感觉', '想法', '生活', '个人'],
            'work': ['工作', '任务', '项目', '会议', '报告', '业务'],
            'entertainment': ['游戏', '电影', '音乐', '娱乐', '搞笑', '有趣'],
            'learning': ['学习', '知识', '教程', '课程', '书籍', '研究']
        }
        
        topic_scores = {}
        for topic, keywords in topic_keywords.items():
            score = sum(1 for keyword in keywords if keyword in content)
            topic_scores[topic] = score
        
        # 确定主要话题
        main_topic = max(topic_scores.items(), key=lambda x: x[1])[0] if any(topic_scores.values()) else 'general'
        
        return {
            'main_topic': main_topic,
            'topic_scores': topic_scores,
            'content_length': len(content),
            'has_questions': '?' in content or '吗' in content,
            'has_exclamation': '!' in content or '！' in content
        }
    
    def _calculate_learning_adjustment(self, situation_context: Dict) -> Dict[str, float]:
        """基于情境计算学习调整参数"""
        base_weight = 1.0
        base_priority = 0.5
        
        # 时间情境调整
        time_ctx = situation_context['time_context']
        if time_ctx['is_work_time']:
            base_weight *= 1.2  # 工作时间消息权重更高
            base_priority += 0.1
        elif time_ctx['period'] in ['evening', 'night']:
            base_weight *= 0.8  # 晚间消息权重略低
        
        # 群体氛围调整
        atmosphere_ctx = situation_context['group_atmosphere']
        if atmosphere_ctx['type'].startswith('positive'):
            base_priority += 0.2  # 积极氛围优先学习
        elif atmosphere_ctx['activity_level'] > 0.05:
            base_weight *= 1.3  # 活跃讨论权重更高
        
        # 话题情境调整
        topic_ctx = situation_context['topic_context']
        if topic_ctx['main_topic'] in ['technical', 'learning']:
            base_weight *= 1.4  # 技术和学习类话题权重更高
            base_priority += 0.15
        
        return {
            'weight': max(0.1, min(2.0, base_weight)),
            'priority': max(0.0, min(1.0, base_priority))
        }
    
    def _summarize_situation_context(self, group_id: str) -> Dict[str, Any]:
        """总结情境上下文"""
        recent_situations = list(self.situation_memory[group_id])[-20:]  # 最近20个情境
        
        if not recent_situations:
            return {'message': '暂无情境数据'}
        
        # 统计情境模式
        time_patterns = defaultdict(int)
        topic_patterns = defaultdict(int)
        atmosphere_patterns = defaultdict(int)
        
        for situation in recent_situations:
            time_patterns[situation['time_context']['period']] += 1
            topic_patterns[situation['topic_context']['main_topic']] += 1
            atmosphere_patterns[situation['group_atmosphere']['type']] += 1
        
        return {
            'dominant_time_pattern': max(time_patterns.items(), key=lambda x: x[1])[0],
            'dominant_topic': max(topic_patterns.items(), key=lambda x: x[1])[0],
            'dominant_atmosphere': max(atmosphere_patterns.items(), key=lambda x: x[1])[0],
            'context_diversity': len(set(s['topic_context']['main_topic'] for s in recent_situations))
        }
    
    async def apply_adversarial_learning(self, group_id: str, learning_batch: List[Dict]) -> Dict[str, Any]:
        """应用对抗性学习防止过拟合"""
        try:
            # 检测过拟合指标
            overfitting_score = await self._detect_overfitting(group_id, learning_batch)
            self.overfitting_indicators[group_id] = overfitting_score
            
            if overfitting_score > 0.7:  # 过拟合阈值
                # 生成对抗性样本
                adversarial_samples = await self._generate_adversarial_samples(group_id, learning_batch)
                
                # 应用对抗性训练
                adjusted_batch = await self._apply_adversarial_training(learning_batch, adversarial_samples)
                
                return {
                    'success': True,
                    'overfitting_detected': True,
                    'overfitting_score': overfitting_score,
                    'adversarial_samples_count': len(adversarial_samples),
                    'adjusted_batch': adjusted_batch
                }
            else:
                return {
                    'success': True,
                    'overfitting_detected': False,
                    'overfitting_score': overfitting_score,
                    'original_batch': learning_batch
                }
                
        except Exception as e:
            self._logger.error(f"对抗性学习失败: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _detect_overfitting(self, group_id: str, learning_batch: List[Dict]) -> float:
        """检测过拟合程度"""
        try:
            # 检查学习样本的多样性
            message_contents = [msg.get('message', '') for msg in learning_batch]
            
            # 计算词汇重复率
            all_words = []
            for content in message_contents:
                words = content.split()
                all_words.extend(words)
            
            unique_words = set(all_words)
            repetition_rate = 1 - (len(unique_words) / max(1, len(all_words)))
            
            # 检查句式模式重复
            sentence_patterns = []
            for content in message_contents:
                pattern = self._extract_sentence_pattern(content)
                sentence_patterns.append(pattern)
            
            pattern_diversity = len(set(sentence_patterns)) / max(1, len(sentence_patterns))
            pattern_repetition = 1 - pattern_diversity
            
            # 综合过拟合指标
            overfitting_score = (repetition_rate * 0.6 + pattern_repetition * 0.4)
            
            return min(1.0, overfitting_score)
            
        except Exception as e:
            self._logger.error(f"过拟合检测失败: {e}")
            return 0.0
    
    def _extract_sentence_pattern(self, content: str) -> str:
        """提取句式模式"""
        # 简单的句式模式提取
        pattern_markers = []
        
        if '?' in content or '吗' in content:
            pattern_markers.append('QUESTION')
        if '!' in content or '！' in content:
            pattern_markers.append('EXCLAMATION')
        if len(content.split()) > 10:
            pattern_markers.append('LONG')
        elif len(content.split()) < 3:
            pattern_markers.append('SHORT')
        else:
            pattern_markers.append('MEDIUM')
        
        return '_'.join(pattern_markers) if pattern_markers else 'NEUTRAL'
    
    async def _generate_adversarial_samples(self, group_id: str, learning_batch: List[Dict]) -> List[Dict]:
        """生成对抗性样本"""
        adversarial_samples = []
        
        try:
            for sample in learning_batch[:5]:  # 对前5个样本生成对抗样本
                original_message = sample.get('message', '')
                
                # 生成多样化的对抗性变体
                variations = await self._create_message_variations(original_message)
                
                for variation in variations:
                    adversarial_sample = sample.copy()
                    adversarial_sample['message'] = variation
                    adversarial_sample['is_adversarial'] = True
                    adversarial_sample['original_message'] = original_message
                    adversarial_samples.append(adversarial_sample)
            
            return adversarial_samples
            
        except Exception as e:
            self._logger.error(f"生成对抗性样本失败: {e}")
            return []
    
    async def _create_message_variations(self, message: str) -> List[str]:
        """创建消息变体"""
        variations = []
        
        try:
            # 使用LLM生成变体
            variation_prompt = f"""
            请为以下消息生成3个保持意思相同但表达方式不同的变体：
            
            原消息: {message}
            
            要求：
            1. 保持原意不变
            2. 改变句式结构
            3. 使用不同的词汇
            4. 每个变体一行
            """
            
            response = await self.llm_ext.generate_response(
                variation_prompt,
                model_name='gpt-4o'  # 使用默认模型名
            )
            
            variations = [line.strip() for line in response.split('\n') if line.strip()]
            
        except Exception as e:
            self._logger.error(f"创建消息变体失败: {e}")
            # 简单的变体生成作为后备
            variations = [
                message + "。",  # 添加句号
                f"换句话说，{message}",  # 添加前缀
                message.replace("。", "！")  # 改变标点
            ]
        
        return variations[:3]
    
    async def _apply_adversarial_training(self, original_batch: List[Dict], 
                                        adversarial_samples: List[Dict]) -> List[Dict]:
        """应用对抗性训练"""
        # 混合原始样本和对抗性样本
        mixed_batch = original_batch.copy()
        
        # 按比例添加对抗性样本
        adversarial_ratio = 0.3  # 30%的对抗性样本
        adversarial_count = int(len(original_batch) * adversarial_ratio)
        
        selected_adversarial = random.sample(
            adversarial_samples, 
            min(adversarial_count, len(adversarial_samples))
        )
        
        mixed_batch.extend(selected_adversarial)
        
        # 随机打乱顺序
        random.shuffle(mixed_batch)
        
        return mixed_batch
    
    async def apply_incremental_learning(self, group_id: str, new_messages: List[Dict]) -> Dict[str, Any]:
        """应用增量学习"""
        try:
            # 提取新词汇和表达方式
            new_vocabulary = await self._extract_new_vocabulary(group_id, new_messages)
            
            # 更新增量词汇库
            self.incremental_vocabulary[group_id].update(new_vocabulary)
            
            # 调整学习动量
            learning_momentum = self._calculate_learning_momentum(group_id, new_messages)
            self.learning_momentum[group_id] = learning_momentum
            
            # 应用增量更新
            incremental_updates = await self._generate_incremental_updates(group_id, new_vocabulary)
            
            return {
                'success': True,
                'new_vocabulary_count': len(new_vocabulary),
                'total_vocabulary_size': len(self.incremental_vocabulary[group_id]),
                'learning_momentum': learning_momentum,
                'incremental_updates': incremental_updates
            }
            
        except Exception as e:
            self._logger.error(f"增量学习失败: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _extract_new_vocabulary(self, group_id: str, messages: List[Dict]) -> set:
        """提取新词汇"""
        new_vocabulary = set()
        existing_vocabulary = self.incremental_vocabulary.get(group_id, set())
        
        try:
            import jieba
            
            for message in messages:
                content = message.get('message', '')
                words = jieba.lcut(content)
                
                for word in words:
                    if (len(word) > 1 and 
                        word not in existing_vocabulary and
                        word.isalnum()):  # 过滤特殊字符
                        new_vocabulary.add(word)
            
        except Exception as e:
            self._logger.error(f"词汇提取失败: {e}")
        
        return new_vocabulary
    
    def _calculate_learning_momentum(self, group_id: str, messages: List[Dict]) -> float:
        """计算学习动量"""
        if not messages:
            return 0.5
        
        # 基于消息质量和频率计算动量
        message_quality = np.mean([msg.get('quality_score', 0.5) for msg in messages])
        message_frequency = len(messages) / max(1, 
            (messages[-1].get('timestamp', time.time()) - messages[0].get('timestamp', time.time())) / 3600
        )
        
        # 动量计算公式
        momentum = (message_quality * 0.7 + min(1.0, message_frequency / 10) * 0.3)
        
        return max(0.1, min(1.0, momentum))
    
    async def _generate_incremental_updates(self, group_id: str, new_vocabulary: set) -> List[Dict]:
        """生成增量更新"""
        updates = []
        
        if not new_vocabulary:
            return updates
        
        # 为新词汇生成使用示例
        for word in list(new_vocabulary)[:10]:  # 限制处理数量
            try:
                usage_example = await self._generate_word_usage_example(word)
                updates.append({
                    'type': 'vocabulary_expansion',
                    'word': word,
                    'usage_example': usage_example,
                    'timestamp': time.time()
                })
            except Exception as e:
                self._logger.error(f"生成词汇使用示例失败 {word}: {e}")
        
        return updates
    
    async def _generate_word_usage_example(self, word: str) -> str:
        """生成词汇使用示例"""
        try:
            example_prompt = f"""
            请为词汇"{word}"生成一个自然的使用示例句子：
            
            要求：
            1. 句子简洁自然
            2. 体现词汇的正确用法
            3. 适合日常对话语境
            
            只返回示例句子，不要其他内容。
            """
            
            response = await self.llm_ext.generate_response(
                example_prompt,
                model_name='gpt-4o'  # 使用默认模型名
            )
            
            return response.strip()
            
        except Exception as e:
            self._logger.error(f"生成使用示例失败: {e}")
            return f'这里可以使用"{word}"这个词'
    
    async def _load_incremental_vocabulary(self):
        """加载增量词汇库"""
        try:
            vocab_file = os.path.join(self.config.data_dir, "incremental_vocabulary.json")
            if os.path.exists(vocab_file):
                with open(vocab_file, 'r', encoding='utf-8') as f:
                    vocab_data = json.load(f)
                    for group_id, words in vocab_data.items():
                        self.incremental_vocabulary[group_id] = set(words)
                        
        except Exception as e:
            self._logger.error(f"加载增量词汇库失败: {e}")
    
    async def _save_incremental_vocabulary(self):
        """保存增量词汇库"""
        try:
            vocab_data = {}
            for group_id, words in self.incremental_vocabulary.items():
                vocab_data[group_id] = list(words)
            
            vocab_file = os.path.join(self.config.data_dir, "incremental_vocabulary.json")
            with open(vocab_file, 'w', encoding='utf-8') as f:
                json.dump(vocab_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self._logger.error(f"保存增量词汇库失败: {e}")
    
    async def get_learning_status(self, group_id: str) -> Dict[str, Any]:
        """获取高级学习状态"""
        return {
            'current_context': self.current_contexts.get(group_id, 'casual'),
            'available_contexts': list(self.default_persona_contexts.keys()),
            'overfitting_indicator': self.overfitting_indicators.get(group_id, 0.0),
            'learning_momentum': self.learning_momentum.get(group_id, 0.5),
            'vocabulary_size': len(self.incremental_vocabulary.get(group_id, set())),
            'situation_memory_size': len(self.situation_memory.get(group_id, []))
        }