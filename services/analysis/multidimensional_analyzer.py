"""
多维度学习引擎 - 全方位分析用户特征和社交关系 - 用户画像
"""
import re
import json
import time
import asyncio # 确保 asyncio 导入
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
import emoji # 导入 emoji 库

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import PluginConfig

from ...exceptions import StyleAnalysisError

from ...core.framework_llm_adapter import FrameworkLLMAdapter # 导入框架适配器

from ..database import DatabaseManager

from ...utils.json_utils import safe_parse_llm_json


@dataclass
class UserProfile:
    """用户画像"""
    qq_id: str
    qq_name: str
    nicknames: List[str] = None
    activity_pattern: Dict[str, Any] = None
    communication_style: Dict[str, float] = None
    social_connections: List[str] = None
    topic_preferences: Dict[str, float] = None
    emotional_tendency: Dict[str, float] = None
    last_active: float = None # 添加缺失的字段
    
    def __post_init__(self):
        if self.nicknames is None:
            self.nicknames = []
        if self.activity_pattern is None:
            self.activity_pattern = {}
        if self.communication_style is None:
            self.communication_style = {}
        if self.social_connections is None:
            self.social_connections = []
        if self.topic_preferences is None:
            self.topic_preferences = {}
        if self.emotional_tendency is None:
            self.emotional_tendency = {}
        if self.last_active is None:
            self.last_active = time.time()


@dataclass
class SocialRelation:
    """社交关系"""
    from_user: str
    to_user: str
    relation_type: str # mention, reply, frequent_interaction
    strength: float # 关系强度 0-1
    frequency: int # 交互频次
    last_interaction: str


@dataclass
class ContextualPattern:
    """情境模式"""
    context_type: str # time_based, topic_based, social_based
    pattern_name: str
    triggers: List[str]
    characteristics: Dict[str, Any]
    confidence: float


class MultidimensionalAnalyzer:
    """多维度分析器"""
    
    def __init__(self, config: PluginConfig, db_manager: DatabaseManager, context=None,
                 llm_adapter: Optional[FrameworkLLMAdapter] = None,
                 prompts: Any = None, temporary_persona_updater = None): # 添加 prompts 参数和临时人格更新器
        self.config = config
        self.context = context
        self.db_manager: DatabaseManager = db_manager # 直接传入 DatabaseManager 实例
        self.prompts = prompts # 保存 prompts
        self.temporary_persona_updater = temporary_persona_updater # 保存临时人格更新器引用

        # 使用框架适配器
        self.llm_adapter = llm_adapter

        # 友好的配置状态提示
        if self.llm_adapter:
            if not self.llm_adapter.has_filter_provider():
                logger.info(" 筛选模型未配置，将使用简化算法进行消息筛选")
            if not self.llm_adapter.has_refine_provider():
                logger.info(" 提炼模型未配置，将使用简化算法进行深度分析")
            if not self.llm_adapter.has_reinforce_provider():
                logger.info(" 强化模型未配置，将跳过强化学习功能")
        else:
            logger.info(" 框架LLM适配器未配置，将使用简化算法进行分析")
        
        # 用户画像存储
        self.user_profiles: Dict[str, UserProfile] = {}
        
        # 社交关系图谱
        self.social_graph: Dict[str, List[SocialRelation]] = defaultdict(list)
        
        # 昵称映射表
        self.nickname_mapping: Dict[str, str] = {} # nickname -> qq_id
        
        # 情境模式库
        self.contextual_patterns: List[ContextualPattern] = []
        
        # 话题分类器
        self.topic_keywords = {
            '日常聊天': ['吃饭', '睡觉', '上班', '下班', '休息', '忙'],
            '游戏娱乐': ['游戏', '电影', '音乐', '小说', '动漫', '综艺'],
            '学习工作': ['学习', '工作', '项目', '考试', '会议', '任务'],
            '情感交流': ['开心', '难过', '生气', '担心', '兴奋', '无聊'],
            '技术讨论': ['代码', '程序', '算法', '技术', '开发', '编程'],
            '生活分享': ['旅游', '美食', '购物', '健身', '宠物', '家庭']
        }
        
        logger.info("多维度学习引擎初始化完成")

    async def start(self):
        """服务启动时加载用户画像和社交关系"""
        try:
            logger.info("多维度分析器启动中...")
            
            # 初始化用户画像存储
            self.user_profiles = {}
            self.social_graph = {}
            
            # 从数据库加载已有的用户画像数据
            try:
                await self._load_user_profiles_from_db()
            except Exception as e:
                logger.warning(f"从数据库加载用户画像失败: {e}")
            
            # 从数据库加载社交关系数据
            try:
                await self._load_social_relations_from_db()
            except Exception as e:
                logger.warning(f"从数据库加载社交关系失败: {e}")
            
            # 初始化分析缓存
            self._analysis_cache = {}
            self._cache_timeout = 3600 # 1小时缓存
            
            # 启动定期清理任务
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            
            logger.info(f"多维度分析器启动完成，已加载 {len(self.user_profiles)} 个用户画像，{len(self.social_graph)} 个社交关系")
            
        except Exception as e:
            logger.error(f"多维度分析器启动失败: {e}")
            raise
    
    async def _load_user_profiles_from_db(self):
        """从数据库加载用户画像"""
        try:
            cutoff = time.time() - 7 * 24 * 3600  # 最近7天

            async with self.db_manager.get_session() as session:
                from sqlalchemy import select, func
                from ...models.orm.message import RawMessage

                stmt = (
                    select(
                        RawMessage.group_id,
                        RawMessage.sender_id,
                        func.max(RawMessage.sender_name).label('sender_name'),
                        func.count().label('msg_count'),
                    )
                    .where(RawMessage.timestamp > cutoff)
                    .group_by(RawMessage.group_id, RawMessage.sender_id)
                    .having(func.count() >= 5)
                    .order_by(func.count().desc())
                    .limit(500)
                )
                result = await session.execute(stmt)
                rows = result.fetchall()

                for group_id, sender_id, sender_name, msg_count in rows:
                    if group_id and sender_id:
                        user_key = f"{group_id}:{sender_id}"
                        self.user_profiles[user_key] = {
                            'user_id': sender_id,
                            'name': sender_name or f"用户{sender_id}",
                            'group_id': group_id,
                            'message_count': msg_count,
                            'topics': [],
                            'communication_style': {},
                            'last_activity': time.time(),
                            'created_at': time.time()
                        }

            logger.info(f"从数据库加载了 {len(self.user_profiles)} 个用户画像")

        except Exception as e:
            logger.error(f"从数据库加载用户画像失败: {e}")
    
    async def _load_social_relations_from_db(self):
        """从数据库加载社交关系"""
        try:
            # 初始化社交图谱
            self.social_graph = {}

            cutoff = time.time() - 7 * 24 * 3600  # 最近7天

            async with self.db_manager.get_session() as session:
                from sqlalchemy import select, func
                from ...models.orm.message import RawMessage

                stmt = (
                    select(
                        RawMessage.group_id,
                        RawMessage.sender_id,
                        func.count().label('interaction_count'),
                    )
                    .where(RawMessage.timestamp > cutoff)
                    .where(RawMessage.group_id.isnot(None))
                    .group_by(RawMessage.group_id, RawMessage.sender_id)
                    .having(func.count() >= 3)
                )
                result = await session.execute(stmt)
                rows = result.fetchall()

                # 构建基础社交关系
                for group_id, sender_id, count in rows:
                    if sender_id not in self.social_graph:
                        self.social_graph[sender_id] = []

                    # 为简化，暂时记录用户在各群组的活跃度
                    relation_info = {
                        'target_user': group_id,
                        'relation_type': 'group_member',
                        'strength': min(1.0, count / 100.0),  # 基于消息数量计算关系强度
                        'last_interaction': time.time()
                    }
                    self.social_graph[sender_id].append(relation_info)

            logger.info(f"构建了 {len(self.social_graph)} 个用户的社交关系")

        except Exception as e:
            logger.error(f"加载社交关系失败: {e}")
    
    async def _periodic_cleanup(self):
        """定期清理过期缓存和数据"""
        try:
            while True:
                await asyncio.sleep(3600) # 每小时执行一次
                
                current_time = time.time()
                
                # 清理分析缓存
                if hasattr(self, '_analysis_cache'):
                    expired_keys = [
                        k for k, v in self._analysis_cache.items()
                        if current_time - v.get('timestamp', 0) > self._cache_timeout
                    ]
                    for key in expired_keys:
                        del self._analysis_cache[key]
                    
                    if expired_keys:
                        logger.debug(f"清理了 {len(expired_keys)} 个过期的分析缓存")
                
                # 清理过期的用户活动记录
                cutoff_time = current_time - 30 * 24 * 3600 # 30天前
                expired_users = [
                    k for k, v in self.user_profiles.items()
                    if v.get('last_activity', 0) < cutoff_time
                ]
                
                for user_key in expired_users:
                    del self.user_profiles[user_key]
                    
                if expired_users:
                    logger.info(f"清理了 {len(expired_users)} 个过期的用户画像")
                    
        except asyncio.CancelledError:
            logger.info("定期清理任务已取消")
        except Exception as e:
            logger.error(f"定期清理任务异常: {e}")

    async def filter_message_with_llm(self, message_text: str, current_persona_description: str) -> bool:
        """
        使用 LLM 对消息进行智能筛选，判断其是否与当前人格匹配、特征鲜明且有学习意义。
        返回 True 表示消息通过筛选，False 表示不通过。
        """
        # 使用框架适配器
        if self.llm_adapter and self.llm_adapter.has_filter_provider() and self.llm_adapter.providers_configured > 0:
            prompt = self.prompts.MULTIDIMENSIONAL_ANALYZER_FILTER_MESSAGE_PROMPT.format(
                current_persona_description=current_persona_description,
                message_text=message_text
            )
            try:
                response = await self.llm_adapter.filter_chat_completion(
                    prompt=prompt,
                    temperature=0.1
                )
                if response:
                    # 解析置信度
                    numbers = re.findall(r'0\.\d+|1\.0|0', response.strip())
                    if numbers:
                        confidence = min(float(numbers[0]), 1.0)
                        logger.debug(f"消息筛选置信度: {confidence} (阈值: {self.config.confidence_threshold})")
                        return confidence >= self.config.confidence_threshold
                logger.warning(f"框架适配器筛选未返回有效置信度，消息默认不通过筛选。")
                return False
            except Exception as e:
                logger.error(f"LLM消息筛选失败: {e}")
                return False
        else:
            logger.warning("筛选模型未配置，无法进行LLM消息筛选，跳过此步骤")
            return True

    async def evaluate_message_quality_with_llm(self, message_text: str, current_persona_description: str) -> Dict[str, float]:
        """
        使用 LLM 对消息进行多维度量化评分。
        评分维度包括：内容质量、相关性、情感积极性、互动性、学习价值。
        返回一个包含各维度评分的字典。
        """
        default_scores = {
            "content_quality": 0.5,
            "relevance": 0.5,
            "emotional_positivity": 0.5,
            "interactivity": 0.5,
            "learning_value": 0.5
        }

        # 优先使用框架适配器
        if self.llm_adapter and self.llm_adapter.has_refine_provider() and self.llm_adapter.providers_configured >= 2:
            prompt = self.prompts.JSON_ONLY_SYSTEM_PROMPT + "\n\n" + self.prompts.MULTIDIMENSIONAL_ANALYZER_EVALUATE_MESSAGE_QUALITY_PROMPT.format(
                current_persona_description=current_persona_description,
                message_text=message_text
            )
            try:
                response = await self.llm_adapter.refine_chat_completion(prompt=prompt)
                if response:
                    scores = safe_parse_llm_json(response, fallback_result=default_scores)
                    
                    if scores and isinstance(scores, dict):
                        # 确保所有分数都在0-1之间
                        for key, value in scores.items():
                            scores[key] = max(0.0, min(float(value), 1.0))
                        logger.debug(f"消息多维度评分: {scores}")
                        return scores
                    else:
                        return default_scores
                logger.warning(f"LLM多维度评分模型未返回有效响应，返回默认评分。")
                return default_scores
            except Exception as e:
                logger.error(f"LLM多维度评分失败: {e}")
                return default_scores
        else:
            logger.warning("提炼模型未配置，无法进行消息质量评分，返回默认评分")
            return default_scores

    def _debug_dict_keys(self, data: Dict, context_name: str = "") -> Dict:
        """调试字典键，确保没有tuple键"""
        try:
            import json
            from collections import Counter
            
            # 递归清理数据结构
            def clean_data(obj):
                if isinstance(obj, Counter):
                    # Counter转换为普通字典
                    return dict(obj)
                elif isinstance(obj, dict):
                    # 清理字典的键和值
                    cleaned = {}
                    for key, value in obj.items():
                        # 确保键是可序列化的基本类型
                        if isinstance(key, (tuple, list, set)):
                            clean_key = str(key)
                        elif key is None:
                            clean_key = "null"
                        else:
                            clean_key = key
                        
                        cleaned[clean_key] = clean_data(value)
                    return cleaned
                elif isinstance(obj, (list, tuple)):
                    return [clean_data(item) for item in obj]
                elif hasattr(obj, '__dict__'):
                    # 处理自定义对象
                    return clean_data(obj.__dict__)
                else:
                    return obj
            
            cleaned_data = clean_data(data)
            
            # 尝试序列化以确认没有问题
            json.dumps(cleaned_data)
            return cleaned_data
            
        except TypeError as e:
            logger.error(f"JSON序列化错误在 {context_name}: {e}")
            logger.error(f"问题数据类型: {type(data)}")
            # 返回空字典避免崩溃
            return {}

    def _clean_user_profiles(self):
        """清理user_profiles中的问题数据"""
        try:
            from collections import Counter
            
            profiles_to_fix = []
            for user_key, profile in self.user_profiles.items():
                if isinstance(profile, dict):
                    # 检查并修复activity_pattern中的Counter
                    if 'activity_pattern' in profile and isinstance(profile['activity_pattern'], dict):
                        activity_pattern = profile['activity_pattern']
                        if 'activity_hours' in activity_pattern and isinstance(activity_pattern['activity_hours'], Counter):
                            profiles_to_fix.append((user_key, 'activity_hours'))
            
            # 修复发现的问题
            for user_key, issue_type in profiles_to_fix:
                if issue_type == 'activity_hours':
                    counter_obj = self.user_profiles[user_key]['activity_pattern']['activity_hours']
                    self.user_profiles[user_key]['activity_pattern']['activity_hours'] = dict(counter_obj)
                    logger.debug(f"修复了用户 {user_key} 的Counter对象")
                    
        except Exception as e:
            logger.error(f"清理user_profiles失败: {e}")

    def _clean_profile_for_serialization(self, profile_dict: Dict[str, Any]) -> Dict[str, Any]:
        """清理用户档案数据，确保可以安全进行JSON序列化"""
        try:
            from collections import Counter
            
            def clean_data_recursive(obj):
                if isinstance(obj, Counter):
                    # Counter转换为普通字典，确保键是基本类型
                    return {str(k) if isinstance(k, (tuple, list, set)) else k: v for k, v in obj.items()}
                elif isinstance(obj, dict):
                    cleaned = {}
                    for key, value in obj.items():
                        # 确保键是可序列化的
                        clean_key = str(key) if isinstance(key, (tuple, list, set)) else key
                        if clean_key is None:
                            clean_key = "null"
                        cleaned[clean_key] = clean_data_recursive(value)
                    return cleaned
                elif isinstance(obj, (list, tuple)):
                    return [clean_data_recursive(item) for item in obj]
                else:
                    return obj
            
            cleaned_profile = clean_data_recursive(profile_dict)
            
            # 尝试JSON序列化测试
            import json
            json.dumps(cleaned_profile)
            
            return cleaned_profile
            
        except Exception as e:
            logger.error(f"清理用户档案数据失败: {e}")
            # 返回基础的空档案，确保不会崩溃
            return {
                'qq_id': profile_dict.get('qq_id', ''),
                'qq_name': profile_dict.get('qq_name', ''),
                'nicknames': [],
                'activity_pattern': {},
                'communication_style': {},
                'topic_preferences': {},
                'emotional_tendency': {}
            }

    async def analyze_message_context(self, event: AstrMessageEvent, message_text: str) -> Dict[str, Any]:
        """分析消息的多维度上下文"""
        try:
            # 检查event是否为None
            if event is None:
                logger.info("使用简化分析方式（无event对象）")
                return await self._analyze_message_context_without_event(message_text)
            
            sender_id = event.get_sender_id()
            sender_name = event.get_sender_name()
            group_id = event.get_group_id() or event.get_sender_id() # 私聊时使用 sender_id 作为会话 ID
            
            # 预先清理user_profiles中的任何问题数据
            self._clean_user_profiles()
            
            # 更新用户画像
            await self._update_user_profile(group_id, sender_id, sender_name, message_text, event) # 传入 group_id
            
            # 分析社交关系
            social_context = await self._analyze_social_context(event, message_text)
            
            # 分析话题偏好
            topic_context = await self._analyze_topic_context(message_text)
            
            # 分析情感倾向
            emotional_context = await self._analyze_emotional_context(message_text)
            
            # 分析时间模式
            temporal_context = await self._analyze_temporal_context(event)
            
            # 分析沟通风格
            style_context = await self._analyze_communication_style(message_text)
            
            # 构建分析结果，使用简化的清理方法
            user_profile_data = self._get_user_profile_activity(group_id, sender_id)
            
            analysis_result = {
                'user_profile': user_profile_data,
                'social_context': social_context or {},
                'topic_context': topic_context or {},
                'emotional_context': emotional_context or {},
                'temporal_context': temporal_context or {},
                'style_context': style_context or {},
                'contextual_relevance': await self._calculate_contextual_relevance(
                    sender_id, message_text, event
                )
            }
            
            # 使用清理方法确保没有序列化问题
            analysis_result = self._debug_dict_keys(analysis_result, 'final_analysis_result')
            
            # 尝试将分析结果集成到system_prompt
            if self.temporary_persona_updater:
                try:
                    # 准备多维度更新数据
                    update_data = {}
                    
                    # 用户档案更新
                    user_key = f"{group_id}:{sender_id}"
                    if user_key in self.user_profiles:
                        profile = self.user_profiles[user_key]
                        update_data['user_profile'] = {
                            'preferences': self._safe_get_profile_attr(profile, 'activity_pattern', {}).get('frequency', '正常'),
                            'communication_style': style_context.get('style_summary', ''),
                            'personality_traits': f"情感倾向{emotional_context.get('sentiment', '中性')}"
                        }
                    
                    # 社交关系更新
                    if social_context:
                        update_data['social_relationship'] = {
                            'user_relationships': social_context.get('relationship_level', ''),
                            'group_atmosphere': social_context.get('group_dynamics', ''),
                            'interaction_style': social_context.get('interaction_pattern', '')
                        }
                    
                    # 上下文感知更新
                    if topic_context:
                        update_data['context_awareness'] = {
                            'current_topic': topic_context.get('main_topics', [''])[0] if topic_context.get('main_topics') else '',
                            'recent_focus': topic_context.get('topic_shift', ''),
                            'dialogue_flow': f"话题相关度: {topic_context.get('relevance_score', 0)}"
                        }
                    
                    # 应用综合更新到system_prompt
                    if update_data:
                        await self.temporary_persona_updater.apply_comprehensive_update_to_system_prompt(
                            group_id, update_data
                        )
                        logger.info(f"成功将多维度分析结果集成到system_prompt: {group_id}")
                    
                except Exception as e:
                    logger.error(f"集成分析结果到system_prompt失败: {e}")
                    # 这里不抛出异常，让分析结果正常返回
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"多维度上下文分析失败: {e}")
            return {}

    async def analyze_message_batch(self, 
                                   message_text: str,
                                   sender_id: str = '',
                                   sender_name: str = '',
                                   group_id: str = '',
                                   timestamp: float = None) -> Dict[str, Any]:
        """
        批量分析消息上下文（用于学习流程中的批量处理）
        
        Args:
            message_text: 消息文本
            sender_id: 发送者ID
            sender_name: 发送者名称
            group_id: 群组ID
            timestamp: 时间戳
            
        Returns:
            Dict[str, Any]: 分析结果
        """
        try:
            logger.debug(f"批量分析消息: 发送者={sender_id}, 群组={group_id}, 消息长度={len(message_text)}")
            
            # 添加批量分析计数器和限制
            if not hasattr(self, '_batch_analysis_count'):
                self._batch_analysis_count = {}
                self._batch_analysis_start_time = time.time()
            
            # 重置计数器（每小时重置一次）
            if time.time() - self._batch_analysis_start_time > 3600:
                self._batch_analysis_count = {}
                self._batch_analysis_start_time = time.time()
            
            # 检查是否超过批量分析限制（每小时最多100次LLM调用）
            current_time = time.time()
            hour_key = int(current_time // 3600)
            
            if hour_key not in self._batch_analysis_count:
                self._batch_analysis_count[hour_key] = 0
            
            if self._batch_analysis_count[hour_key] >= 100:
                logger.warning("批量分析达到限制，使用简化分析")
                return await self._analyze_message_context_without_event(message_text)
            
            # 增加分析计数
            self._batch_analysis_count[hour_key] += 1
            
            # 更新用户画像（如果有足够信息）
            if sender_id and group_id:
                await self._update_user_profile_batch(group_id, sender_id, sender_name, message_text, timestamp)
            
            # 分析话题偏好
            topic_context = await self._analyze_topic_context(message_text)
            
            # 分析情感倾向（已有缓存机制）
            emotional_context = await self._analyze_emotional_context(message_text)
            
            # 分析沟通风格（添加限制）
            style_context = {}
            if self._batch_analysis_count[hour_key] <= 50: # 限制风格分析的调用次数
                style_context = await self._analyze_communication_style(message_text)
            else:
                # 使用简化的风格分析
                style_context = {
                    'length_preference': len(message_text),
                    'emoji_usage': self._calculate_emoji_usage(message_text),
                    'punctuation_style': self._calculate_punctuation_style(message_text)
                }
            
            # 计算相关性得分
            contextual_relevance = await self._calculate_enhanced_relevance(
                message_text, sender_id, group_id, timestamp
            )
            
            # 构建简化的社交上下文
            social_context = {}
            if sender_id and group_id:
                social_context = await self._get_user_social_context(group_id, sender_id)
            
            return {
                'user_profile': self.user_profiles.get(f"{group_id}:{sender_id}", {}) if sender_id and group_id else {},
                'social_context': social_context,
                'topic_context': topic_context,
                'emotional_context': emotional_context,
                'temporal_context': {'timestamp': timestamp or time.time()},
                'style_context': style_context,
                'contextual_relevance': contextual_relevance
            }
            
        except Exception as e:
            logger.error(f"批量消息分析失败: {e}")
            # 返回基础分析结果
            return await self._analyze_message_context_without_event(message_text)

    async def _update_user_profile_batch(self, group_id: str, sender_id: str, sender_name: str, 
                                       message_text: str, timestamp: float = None):
        """批量更新用户画像（简化版本）"""
        try:
            user_key = f"{group_id}:{sender_id}"
            current_time = timestamp or time.time()
            
            if user_key not in self.user_profiles:
                # 创建UserProfile对象而不是字典
                profile = UserProfile(qq_id=sender_id, qq_name=sender_name)
                self.user_profiles[user_key] = profile
            else:
                profile = self.user_profiles[user_key]
                
            # 更新基本信息 - 使用属性访问而不是字典访问
            if hasattr(profile, 'message_count'):
                if isinstance(profile.communication_style, dict) and 'message_count' in profile.communication_style:
                    profile.communication_style['message_count'] += 1
                else:
                    profile.communication_style['message_count'] = 1
            
            # 更新沟通风格
            style = await self._analyze_communication_style(message_text)
            if style:
                if not isinstance(profile.communication_style, dict):
                    profile.communication_style = {}
                profile.communication_style.update(style)
                
        except Exception as e:
            logger.error(f"批量更新用户画像失败: {e}")

    def _safe_get_profile_attr(self, profile, attr_name: str, default=None):
        """安全获取profile属性，兼容UserProfile对象和dict"""
        try:
            if isinstance(profile, dict):
                return profile.get(attr_name, default)
            else:
                return getattr(profile, attr_name, default)
        except Exception:
            return default

    def _get_user_profile_activity(self, group_id: str, sender_id: str) -> Dict[str, Any]:
        """安全获取用户档案活动模式"""
        try:
            user_key = f"{group_id}:{sender_id}"
            if user_key in self.user_profiles:
                profile = self.user_profiles[user_key]
                if isinstance(profile, dict):
                    return profile.get('activity_pattern', {})
                else:
                    # UserProfile对象
                    return getattr(profile, 'activity_pattern', {})
            return {}
        except Exception as e:
            logger.error(f"获取用户档案活动模式失败: {e}")
            return {}

    async def _calculate_enhanced_relevance(self, message_text: str, sender_id: str = '', 
                                          group_id: str = '', timestamp: float = None) -> float:
        """计算增强的相关性得分"""
        try:
            # 基础相关性
            base_relevance = await self._calculate_basic_relevance(message_text)
            
            # 用户活跃度加成
            user_bonus = 0.0
            if sender_id and group_id:
                user_key = f"{group_id}:{sender_id}"
                if user_key in self.user_profiles:
                    user_profile = self.user_profiles[user_key]
                    # 活跃用户的消息获得更高权重
                    message_count = user_profile.get('message_count', 0) if isinstance(user_profile, dict) else getattr(user_profile, 'message_count', 0)
                    if message_count > 10:
                        user_bonus = 0.1
                    
            return min(1.0, base_relevance + user_bonus)
            
        except Exception as e:
            logger.error(f"计算增强相关性失败: {e}")
            return await self._calculate_basic_relevance(message_text)

    async def _get_user_social_context(self, group_id: str, sender_id: str) -> Dict[str, Any]:
        """获取用户社交上下文"""
        try:
            user_key = f"{group_id}:{sender_id}"
            if user_key in self.user_profiles:
                profile = self.user_profiles[user_key]
                message_count = self._safe_get_profile_attr(profile, 'message_count', 0)
                last_activity = self._safe_get_profile_attr(profile, 'last_activity', 0)
                return {
                    'message_count': message_count,
                    'activity_level': 'high' if message_count > 50 else 'low',
                    'last_activity': last_activity
                }
            return {}
            
        except Exception as e:
            logger.error(f"获取用户社交上下文失败: {e}")
            return {}

    async def _analyze_message_context_without_event(self, message_text: str) -> Dict[str, Any]:
        """在没有event对象时分析消息上下文（简化版本）"""
        try:
            # 分析话题偏好
            topic_context = await self._analyze_topic_context(message_text)
            
            # 分析情感倾向
            emotional_context = await self._analyze_emotional_context(message_text)
            
            # 分析沟通风格
            style_context = await self._analyze_communication_style(message_text)
            
            # 计算基础相关性得分
            contextual_relevance = await self._calculate_basic_relevance(message_text)
            
            return {
                'user_profile': {},
                'social_context': {},
                'topic_context': topic_context,
                'emotional_context': emotional_context,
                'temporal_context': {},
                'style_context': style_context,
                'contextual_relevance': contextual_relevance
            }
            
        except Exception as e:
            logger.error(f"简化上下文分析失败: {e}")
            return {
                'user_profile': {},
                'social_context': {},
                'topic_context': {},
                'emotional_context': {},
                'temporal_context': {},
                'style_context': {},
                'contextual_relevance': 0.5
            }

    async def _calculate_basic_relevance(self, message_text: str) -> float:
        """计算基础相关性得分"""
        try:
            # 基于消息长度和内容质量的简单评分
            message_length = len(message_text.strip())
            if message_length < 5:
                return 0.2
            elif message_length < 20:
                return 0.4
            elif message_length < 50:
                return 0.6
            else:
                return 0.8
        except Exception:
            return 0.5

    async def _update_user_profile(self, group_id: str, qq_id: str, qq_name: str, message_text: str, event: AstrMessageEvent):
        """更新用户画像并持久化"""
        try:
            profile_data = await self.db_manager.load_user_profile(group_id, qq_id)
            if profile_data:
                profile = UserProfile(**profile_data)
            else:
                profile = UserProfile(qq_id=qq_id, qq_name=qq_name)
            
            # 更新活动模式
            current_hour = datetime.now().hour
            if 'activity_hours' not in profile.activity_pattern:
                profile.activity_pattern['activity_hours'] = Counter()
            elif not isinstance(profile.activity_pattern['activity_hours'], Counter):
                # 如果从数据库加载的是普通字典，转换为Counter
                profile.activity_pattern['activity_hours'] = Counter(profile.activity_pattern['activity_hours'])
            
            profile.activity_pattern['activity_hours'][current_hour] += 1
            
            # 更新消息长度偏好
            msg_length = len(message_text)
            if 'message_lengths' not in profile.activity_pattern:
                profile.activity_pattern['message_lengths'] = []
            profile.activity_pattern['message_lengths'].append(msg_length)
            
            # 保持最近100条消息的长度记录
            if len(profile.activity_pattern['message_lengths']) > 100:
                profile.activity_pattern['message_lengths'] = profile.activity_pattern['message_lengths'][-100:]
            
            # 更新话题偏好
            topics = await self._extract_topics(message_text)
            for topic in topics:
                if topic not in profile.topic_preferences:
                    profile.topic_preferences[topic] = 0
                profile.topic_preferences[topic] += 1
            
            # 更新沟通风格
            style_features = await self._extract_style_features(message_text)
            for feature, value in style_features.items():
                if feature not in profile.communication_style:
                    profile.communication_style[feature] = []
                profile.communication_style[feature].append(value)
                
                # 保持最近50个特征值
                if len(profile.communication_style[feature]) > 50:
                    profile.communication_style[feature] = profile.communication_style[feature][-50:]
            
            # 使用一致的用户键格式
            user_key = f"{group_id}:{qq_id}"
            self.user_profiles[user_key] = profile # 更新内存中的画像
            
            # 清理profile数据以确保JSON序列化安全
            profile_dict = asdict(profile)
            profile_dict = self._clean_profile_for_serialization(profile_dict)
            await self.db_manager.save_user_profile(group_id, profile_dict) # 持久化到数据库
            
        except Exception as e:
            logger.error(f"更新用户画像失败 (群:{group_id}, 用户:{qq_id}): {e}", exc_info=True)
            raise

    async def _analyze_social_context(self, event: AstrMessageEvent, message_text: str) -> Dict[str, Any]:
        """分析社交关系上下文"""
        try:
            sender_id = event.get_sender_id()
            group_id = event.get_group_id() or event.get_sender_id() # 私聊时使用 sender_id 作为会话 ID
            
            social_context = {
                'mentions': [],
                'replies': [],
                'interaction_strength': {},
                'group_role': 'member'
            }
            
            # 提取@消息
            mentions = self._extract_mentions(message_text)
            social_context['mentions'] = mentions

            logger.debug(f"[社交关系] 群组 {group_id} 用户 {sender_id} 提及了 {len(mentions)} 个用户: {mentions}")

            # 更新社交关系
            for mentioned_user in mentions:
                await self._update_social_relation(
                    sender_id, mentioned_user, 'mention', group_id
                )
                logger.debug(f"[社交关系] 保存提及关系: {sender_id} -> {mentioned_user}")

            # 分析回复关系（如果框架支持）
            if hasattr(event, 'get_reply_info') and event.get_reply_info():
                reply_info = event.get_reply_info()
                replied_user = reply_info.get('user_id')
                if replied_user:
                    social_context['replies'].append(replied_user)
                    await self._update_social_relation(
                        sender_id, replied_user, 'reply', group_id
                    )
                    logger.debug(f"[社交关系] 保存回复关系: {sender_id} -> {replied_user}")
            else:
                logger.debug(f"[社交关系] 消息事件不支持get_reply_info或没有回复信息")

            # 新增：基于时间窗口的对话关系分析(去除@限制)
            await self._analyze_conversation_interactions(sender_id, group_id, message_text)

            # 计算与群内成员的交互强度
            if sender_id in self.social_graph:
                for relation in self.social_graph[sender_id]:
                    social_context['interaction_strength'][relation.to_user] = relation.strength
            
            # 分析群内角色（基于发言频率和@次数）
            group_role = await self._analyze_group_role(sender_id, group_id)
            social_context['group_role'] = group_role
            
            return social_context
        
        except Exception as e:
            logger.warning(f"社交上下文分析失败: {e}")
            return {}

    async def _analyze_topic_context(self, message_text: str) -> Dict[str, float]:
        """分析话题上下文"""
        topic_scores = {}
        
        for topic, keywords in self.topic_keywords.items():
            score = 0
            for keyword in keywords:
                if keyword in message_text:
                    score += 1
            
            if score > 0:
                topic_scores[topic] = score / len(keywords)
        
        return topic_scores

    async def _analyze_emotional_context(self, message_text: str) -> Dict[str, float]:
        """使用LLM分析情感上下文"""
        # 检查缓存，避免重复分析相同内容
        cache_key = f"emotion_cache_{hash(message_text)}"
        if hasattr(self, '_analysis_cache') and cache_key in self._analysis_cache:
            cached_result = self._analysis_cache[cache_key]
            if time.time() - cached_result.get('timestamp', 0) < 300: # 5分钟缓存
                logger.debug(f"使用缓存的情感分析结果")
                return cached_result.get('result', self._simple_emotional_analysis(message_text))
        
        # 优先使用框架适配器
        if self.llm_adapter and self.llm_adapter.has_refine_provider() and self.llm_adapter.providers_configured >= 2:
            prompt = self.prompts.JSON_ONLY_SYSTEM_PROMPT + "\n\n" + self.prompts.MULTIDIMENSIONAL_ANALYZER_EMOTIONAL_CONTEXT_PROMPT.format(
                message_text=message_text
            )
            try:
                response = await self.llm_adapter.refine_chat_completion(
                    prompt=prompt,
                    temperature=0.2
                )
                
                if response:
                    # 使用安全的JSON解析方法
                    emotion_scores = safe_parse_llm_json(
                        response.strip(), 
                        fallback_result=self._simple_emotional_analysis(message_text)
                    )
                    
                    if emotion_scores and isinstance(emotion_scores, dict):
                        # 确保所有分数都在0-1之间
                        for key, value in emotion_scores.items():
                            emotion_scores[key] = max(0.0, min(float(value), 1.0))
                        
                        # 缓存结果
                        if not hasattr(self, '_analysis_cache'):
                            self._analysis_cache = {}
                        self._analysis_cache[cache_key] = {
                            'result': emotion_scores,
                            'timestamp': time.time()
                        }
                        
                        logger.debug(f"情感上下文分析结果: {emotion_scores}")
                        return emotion_scores
                    else:
                        logger.warning(f"LLM情感分析返回格式不正确，使用简化算法")
                        return self._simple_emotional_analysis(message_text)
                else:
                    logger.warning(f"LLM情感分析未返回有效结果，使用简化算法")
                    return self._simple_emotional_analysis(message_text)
                    
            except Exception as e:
                logger.error(f"LLM情感分析失败: {e}")
                return self._simple_emotional_analysis(message_text)
        else:
            logger.warning("提炼模型未配置，无法进行LLM情感分析，使用简化算法")
            return self._simple_emotional_analysis(message_text)
        
    def _simple_emotional_analysis(self, message_text: str) -> Dict[str, float]:
        """简化的情感分析（备用）"""
        emotions = {
            '积极': ['开心', '高兴', '兴奋', '满意', '喜欢', '爱', '好棒', '太好了', '哈哈', '', '', ''],
            '消极': ['难过', '生气', '失望', '无聊', '烦', '讨厌', '糟糕', '不好', '', '', ''],
            '中性': ['知道', '明白', '可以', '好的', '嗯', '哦', '这样', '然后'],
            '疑问': ['吗', '呢', '？', '什么', '怎么', '为什么', '哪里', ''],
            '惊讶': ['哇', '天哪', '真的', '不会吧', '太', '竟然', '居然', '', '']
        }
        
        emotion_scores = {}
        # 将消息文本按空格或标点符号分割成单词，并过滤掉空字符串
        words = [word for word in re.split(r'\s+|[，。！？；：]', message_text) if word]
        total_words = len(words) # 已经修改为单词总数
        
        for emotion, keywords in emotions.items():
            count = 0
            for keyword in keywords:
                # 检查关键词是否在单词列表中
                count += words.count(keyword)
            
            emotion_scores[emotion] = count / max(total_words, 1)
        
        return emotion_scores

    async def _analyze_temporal_context(self, event: AstrMessageEvent) -> Dict[str, Any]:
        """分析时间上下文"""
        now = datetime.now()
        
        time_context = {
            'hour': now.hour,
            'weekday': now.weekday(),
            'time_period': self._get_time_period(now.hour),
            'is_weekend': now.weekday() >= 5,
            'season': self._get_season(now.month)
        }
        
        return time_context

    async def _analyze_communication_style(self, message_text: str) -> Dict[str, float]:
        """分析沟通风格（优化版，减少LLM调用）"""
        try:
            # 检查缓存
            cache_key = f"style_cache_{hash(message_text)}"
            if hasattr(self, '_analysis_cache') and cache_key in self._analysis_cache:
                cached_result = self._analysis_cache[cache_key]
                if time.time() - cached_result.get('timestamp', 0) < 600: # 10分钟缓存
                    logger.debug(f"使用缓存的风格分析结果")
                    return cached_result.get('result', {})
            
            # 优化：优先使用简化计算，减少LLM调用
            style_features = {
                'formal_level': self._simple_formal_level(message_text),
                'enthusiasm_level': self._simple_enthusiasm_level(message_text),
                'question_tendency': self._simple_question_tendency(message_text),
                'emoji_usage': self._calculate_emoji_usage(message_text),
                'length_preference': len(message_text),
                'punctuation_style': self._calculate_punctuation_style(message_text)
            }
            
            # 只有在批量分析计数较低时才使用LLM增强分析
            if (hasattr(self, '_batch_analysis_count') and 
                any(count <= 20 for count in self._batch_analysis_count.values())):
                # 选择性地使用LLM增强某些特征
                try:
                    style_features['formal_level'] = await self._calculate_formal_level(message_text)
                except Exception as e:
                    logger.debug(f"LLM正式程度分析失败，使用简化版本: {e}")
            
            # 缓存结果
            if not hasattr(self, '_analysis_cache'):
                self._analysis_cache = {}
            self._analysis_cache[cache_key] = {
                'result': style_features,
                'timestamp': time.time()
            }
            
            return style_features
        except Exception as e:
            logger.error(f'分析沟通风格失败：{e}')
            # 返回最基本的风格特征
            return {
                'formal_level': 0.5,
                'enthusiasm_level': self._simple_enthusiasm_level(message_text),
                'question_tendency': self._simple_question_tendency(message_text),
                'emoji_usage': self._calculate_emoji_usage(message_text),
                'length_preference': len(message_text),
                'punctuation_style': self._calculate_punctuation_style(message_text)
            }

    async def _extract_topics(self, message_text: str) -> List[str]:
        """提取消息话题"""
        detected_topics = []
        
        for topic, keywords in self.topic_keywords.items():
            for keyword in keywords:
                if keyword in message_text:
                    detected_topics.append(topic)
                    break
        
        return detected_topics

    async def _extract_style_features(self, message_text: str) -> Dict[str, float]:
        """提取风格特征"""
        return {
            'length': len(message_text),
            'punctuation_ratio': len([c for c in message_text if c in '，。！？；：']) / max(len(message_text), 1),
            'emoji_count': emoji.emoji_count(message_text),
            'question_count': message_text.count('？') + message_text.count('?'),
            'exclamation_count': message_text.count('！') + message_text.count('!')
        }

    def _extract_mentions(self, message_text: str) -> List[str]:
        """提取@消息"""
        # 匹配@用户模式
        at_pattern = r'@(\w+|\d+)'
        matches = re.findall(at_pattern, message_text)
        
        # 尝试解析昵称到QQ号的映射
        mentioned_users = []
        for match in matches:
            if match.isdigit():
                # 直接@的QQ号
                mentioned_users.append(match)
            else:
                # @的昵称，尝试找到对应的QQ号
                if match in self.nickname_mapping:
                    mentioned_users.append(self.nickname_mapping[match])
                else:
                    # 记录未知昵称
                    mentioned_users.append(f"nickname:{match}")
        
        return mentioned_users

    async def _update_social_relation(self, from_user: str, to_user: str, relation_type: str, group_id: str):
        """更新社交关系"""
        logger.debug(f"[社交关系更新] 开始更新: {from_user} -> {to_user}, 类型: {relation_type}, 群组: {group_id}")

        # 查找现有关系
        existing_relation = None
        for relation in self.social_graph[from_user]:
            if relation.to_user == to_user and relation.relation_type == relation_type:
                existing_relation = relation
                break

        if existing_relation:
            # 更新现有关系
            old_frequency = existing_relation.frequency
            old_strength = existing_relation.strength
            existing_relation.frequency += 1
            existing_relation.last_interaction = datetime.now().isoformat()
            existing_relation.strength = min(existing_relation.strength + 0.1, 1.0)
            logger.info(f"[社交关系更新] 更新已存在的关系: {from_user} -> {to_user} ({relation_type}), "
                       f"频率: {old_frequency} -> {existing_relation.frequency}, "
                       f"强度: {old_strength:.2f} -> {existing_relation.strength:.2f}")
        else:
            # 创建新关系
            new_relation = SocialRelation(
                from_user=from_user,
                to_user=to_user,
                relation_type=relation_type,
                strength=0.1,
                frequency=1,
                last_interaction=datetime.now().isoformat()
            )
            self.social_graph[from_user].append(new_relation)
            logger.info(f"[社交关系更新] 创建新关系: {from_user} -> {to_user} ({relation_type}), "
                       f"初始强度: 0.1, 频率: 1")

        # 持久化社交关系
        relation_data = asdict(existing_relation if existing_relation else new_relation)
        relation_data = self._debug_dict_keys(relation_data, 'social_relation')

        try:
            await self.db_manager.save_social_relation(group_id, relation_data)
            logger.debug(f"[社交关系更新] 成功保存到数据库: {from_user} -> {to_user}")
        except Exception as e:
            logger.error(f"[社交关系更新] 保存到数据库失败: {e}", exc_info=True)

    async def _analyze_conversation_interactions(self, sender_id: str, group_id: str, message_text: str):
        """
        基于时间窗口分析对话互动关系(不需要@)

        分析逻辑:
        1. 获取最近一定时间内的消息
        2. 判断用户之间的对话连续性
        3. 建立conversation类型的社交关系
        """
        try:
            # 获取最近5分钟内的消息
            recent_messages = await self.db_manager.get_messages_by_group_and_timerange(
                group_id=group_id,
                start_time=time.time() - 300, # 5分钟
                limit=20
            )

            if len(recent_messages) < 2:
                return

            # 找到当前用户之前的最近一条其他人的消息
            previous_sender = None
            for msg in reversed(recent_messages): # 按时间倒序
                if msg['sender_id'] != sender_id and msg['sender_id'] != 'bot':
                    previous_sender = msg['sender_id']
                    previous_message = msg['message']
                    time_diff = time.time() - msg['timestamp']
                    break

            if not previous_sender:
                return

            # 如果时间间隔小于60秒,认为是在对话
            if time_diff <= 60:
                # 使用LLM判断是否在回应
                is_responding, reason = await self._is_likely_responding_llm(previous_message, message_text)

                if is_responding:
                    await self._update_social_relation(
                        sender_id, previous_sender, 'conversation', group_id
                    )
                    logger.info(f"[社交关系-对话] 检测到对话关系: {sender_id} -> {previous_sender}, "
                               f"时间间隔: {time_diff:.1f}秒, 判断理由: {reason}")

        except Exception as e:
            logger.debug(f"[社交关系-对话] 分析对话互动失败: {e}")

    async def _is_likely_responding_llm(self, previous_message: str, current_message: str) -> tuple[bool, str]:
        """
        使用LLM判断是否在回应上一条消息

        Returns:
            (是否在回应, 判断理由)
        """
        if not self.llm_adapter:
            logger.debug("[社交关系-LLM] LLM适配器未初始化,使用简单规则判断")
            is_responding = self._is_likely_responding_simple(previous_message, current_message)
            return is_responding, "规则判断"

        try:
            prompt = f"""分析以下两条消息的关系,判断"当前消息"是否在回应"上一条消息"。

上一条消息: {previous_message}
当前消息: {current_message}

请根据以下标准判断:
1. 语义相关性: 两条消息是否在讨论同一个话题
2. 回应性: 当前消息是否包含回应、回答、评论上一条消息的内容
3. 对话连贯性: 两条消息是否构成连贯的对话

请以JSON格式返回:
{{
  "is_responding": true/false,
  "reason": "判断理由",
  "confidence": 0.0-1.0 (置信度)
}}"""

            response = await self.llm_adapter.call_llm(
                prompt=prompt,
                system_prompt="你是一个专业的对话分析专家,擅长判断消息之间的关系。",
                temperature=0.3
            )

            # 解析JSON响应
            result = safe_parse_llm_json(response)

            if result and 'is_responding' in result:
                is_responding = result.get('is_responding', False)
                reason = result.get('reason', '未知')
                confidence = result.get('confidence', 0.5)

                logger.debug(f"[社交关系-LLM] LLM判断结果: {is_responding}, 置信度: {confidence}, 理由: {reason}")

                # 只有当置信度足够高时才返回True
                return is_responding and confidence >= 0.6, reason

            else:
                logger.warning(f"[社交关系-LLM] LLM返回格式错误,使用简单规则: {response[:100]}")
                is_responding = self._is_likely_responding_simple(previous_message, current_message)
                return is_responding, "LLM解析失败,使用规则判断"

        except Exception as e:
            logger.warning(f"[社交关系-LLM] LLM判断失败: {e}, 使用简单规则")
            is_responding = self._is_likely_responding_simple(previous_message, current_message)
            return is_responding, f"LLM异常: {str(e)}"

    def _is_likely_responding_simple(self, previous_message: str, current_message: str) -> bool:
        """
        简单判断是否在回应上一条消息

        判断规则:
        1. 包含回应性词汇
        2. 话题相关性(关键词重合)
        3. 不是纯表情/符号
        """
        # 回应性词汇
        response_keywords = [
            '是的', '不是', '对', '没错', '确实', '同意', '赞同',
            '好的', '行', '可以', '不行', '不可以',
            '哈哈', '笑死', '？', '?', '！', '!',
            '嗯', '哦', '额', '呃', '啊',
            '为什么', '怎么', '什么', '哪里', '哪个'
        ]

        # 检查是否包含回应性词汇
        for keyword in response_keywords:
            if keyword in current_message:
                return True

        # 检查关键词重合(简单的话题相关性)
        import re
        prev_words = set(re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+', previous_message))
        curr_words = set(re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+', current_message))

        # 移除常见停用词
        stopwords = {'的', '了', '是', '在', '有', '和', '就', '不', '人', '都', '一', '个'}
        prev_words -= stopwords
        curr_words -= stopwords

        # 如果有共同关键词,认为可能在讨论同一话题
        if prev_words and curr_words:
            overlap = len(prev_words & curr_words)
            if overlap > 0:
                return True

        return False

    async def _analyze_group_role(self, user_id: str, group_id: str) -> str:
        """分析用户在群内的角色"""
        # 这里可以基于发言频率、被@次数等判断用户角色
        # 简化实现
        user_key = f"{group_id}:{user_id}"
        if user_key in self.user_profiles:
            profile = self.user_profiles[user_key]
            mention_count = sum(1 for relations in self.social_graph.values() 
                              for relation in relations 
                              if relation.to_user == user_id and relation.relation_type == 'mention')
            
            if mention_count > 10:
                return 'active_member'
            elif mention_count > 5:
                return 'regular_member'
            else:
                return 'member'
        
        return 'member'

    async def _calculate_contextual_relevance(self, sender_id: str, message_text: str, event: AstrMessageEvent) -> float:
        """计算上下文相关性得分"""

        try:

            relevance_score = 0.0
            group_id = event.get_group_id() if event else ''
            
            # 基于用户历史行为的相关性
            user_key = f"{group_id}:{sender_id}"
            if user_key in self.user_profiles:
                profile = self.user_profiles[user_key]
                
                # 兼容处理UserProfile对象和dict
                if hasattr(profile, 'topic_preferences'):
                    topic_preferences = profile.topic_preferences
                else:
                    topic_preferences = profile.get('topic_preferences', {})
                
                # 话题一致性
                current_topics = await self._extract_topics(message_text)
                for topic in current_topics:
                    if topic in topic_preferences:
                        relevance_score += 0.2
                
                # 风格一致性
                current_style = await self._extract_style_features(message_text)
                communication_style = profile.communication_style if hasattr(profile, 'communication_style') else profile.get('communication_style', {})
                
                if 'length' in communication_style:
                    avg_length = sum(communication_style['length'][-10:]) / min(10, len(communication_style['length']))
                    length_similarity = 1.0 - abs(current_style['length'] - avg_length) / max(avg_length, 1)
                    relevance_score += length_similarity * 0.1
            
                # 时间上下文相关性
                current_hour = datetime.now().hour
                if user_key in self.user_profiles:
                    profile = self.user_profiles[user_key]
                    activity_pattern = profile.activity_pattern if hasattr(profile, 'activity_pattern') else profile.get('activity_pattern', {})
                    if 'activity_hours' in activity_pattern:
                        hour_frequency = activity_pattern['activity_hours'].get(current_hour, 0)
                        total_messages = sum(activity_pattern['activity_hours'].values())
                        if total_messages > 0:
                            time_relevance = hour_frequency / total_messages
                            relevance_score += time_relevance * 0.2
            
            return min(relevance_score, 1.0)
        except Exception as e:
            logger.warning(f"计算上下文相关性得分-计算失败: {e}")
            return None

    def _get_time_period(self, hour: int) -> str:
        """获取时间段"""
        if 6 <= hour < 12:
            return '上午'
        elif 12 <= hour < 18:
            return '下午'
        elif 18 <= hour < 22:
            return '晚上'
        else:
            return '深夜'

    def _get_season(self, month: int) -> str:
        """获取季节"""
        if month in [1, 2, 12]:
            return '冬季'
        elif month in [3, 4, 5]:
            return '春季'
        elif month in [6, 7, 8]:
            return '夏季'
        else:
            return '秋季'

    async def _call_llm_for_style_analysis(self, text: str, prompt_template: str, fallback_function: callable, analysis_name: str) -> float:
        """
        通用的LLM风格分析辅助函数。
        Args:
            text: 待分析的文本。
            prompt_template: LLM提示模板。
            fallback_function: LLM客户端未初始化或调用失败时使用的备用函数。
            analysis_name: 分析名称，用于日志记录。
        Returns:
            0-1之间的评分。
        """
        # 检查适配器和refine provider是否可用
        if not self.llm_adapter or not self.llm_adapter.has_refine_provider() or self.llm_adapter.providers_configured < 2:
            logger.warning(f"提炼模型LLM客户端未初始化，无法使用LLM计算{analysis_name}，使用简化算法。")
            return fallback_function(text)

        try:
            prompt = prompt_template.format(text=text)
            response = await self.llm_adapter.refine_chat_completion(
                prompt=prompt,
                temperature=0.1
            )
            
            if response:
                # response 是字符串
                numbers = re.findall(r'0\.\d+|1\.0|0', response.strip())
                if numbers:
                    return min(float(numbers[0]), 1.0)
            
            return 0.5 # 默认值
            
        except Exception as e:
            logger.warning(f"LLM{analysis_name}计算失败，使用简化算法: {e}")
            return fallback_function(text)

    async def _calculate_formal_level(self, text: str) -> float:
        """使用LLM计算正式程度"""
        prompt_template = self.prompts.MULTIDIMENSIONAL_ANALYZER_FORMAL_LEVEL_PROMPT
        return await self._call_llm_for_style_analysis(text, prompt_template, self._simple_formal_level, "正式程度")

    def _simple_formal_level(self, text: str) -> float:
        """简化的正式程度计算（备用）"""
        formal_indicators = ['您', '请', '谢谢您', '不好意思', '打扰了', '恕我直言', '请问']
        informal_indicators = ['哈哈', '嘿', '啊', '呀', '哦', '嗯嗯', '哇']
        
        formal_count = sum(text.count(word) for word in formal_indicators)
        informal_count = sum(text.count(word) for word in informal_indicators)
        
        total = formal_count + informal_count
        return formal_count / max(total, 1) if total > 0 else 0.5

    async def _calculate_enthusiasm_level(self, text: str) -> float:
        """使用LLM计算热情程度"""
        prompt_template = self.prompts.MULTIDIMENSIONAL_ANALYZER_ENTHUSIASM_LEVEL_PROMPT
        return await self._call_llm_for_style_analysis(text, prompt_template, self._simple_enthusiasm_level, "热情程度")

    def _simple_enthusiasm_level(self, text: str) -> float:
        """简化的热情程度计算（备用）"""
        enthusiasm_indicators = ['！', '!', '哈哈', '太好了', '棒', '赞', '', '', '', '厉害', 'awesome']
        count = sum(text.count(indicator) for indicator in enthusiasm_indicators)
        return min(count / max(len(text), 1) * 20, 1.0)

    async def _calculate_question_tendency(self, text: str) -> float:
        """使用LLM计算提问倾向"""
        prompt_template = self.prompts.MULTIDIMENSIONAL_ANALYZER_QUESTION_TENDENCY_PROMPT
        return await self._call_llm_for_style_analysis(text, prompt_template, self._simple_question_tendency, "提问倾向")

    def _simple_question_tendency(self, text: str) -> float:
        """简化的提问倾向计算（备用）"""
        question_indicators = ['？', '?', '吗', '呢', '什么', '怎么', '为什么', '哪里', '如何']
        count = sum(text.count(indicator) for indicator in question_indicators)
        return min(count / max(len(text), 1) * 10, 1.0)

    def _calculate_emoji_usage(self, text: str) -> float:
        """计算表情符号使用程度"""
        emoji_count = emoji.emoji_count(text)
        return min(emoji_count / max(len(text), 1) * 10, 1.0)

    def _calculate_punctuation_style(self, text: str) -> float:
        """计算标点符号风格"""
        punctuation_count = len([c for c in text if c in '，。！？；：""''()（）'])
        return punctuation_count / max(len(text), 1)

    async def get_user_insights(self, group_id: str, qq_id: str) -> Dict[str, Any]:
        """使用LLM生成深度用户洞察"""
        user_key = f"{group_id}:{qq_id}"
        if user_key not in self.user_profiles:
            return {"error": "用户不存在"}
        
        profile = self.user_profiles[user_key]
        
        # 计算活跃时段
        active_hours = []
        activity_pattern = profile.activity_pattern if hasattr(profile, 'activity_pattern') else profile.get('activity_pattern', {})
        if 'activity_hours' in activity_pattern:
            sorted_hours = sorted(activity_pattern['activity_hours'].items(), 
                                key=lambda x: x[1], reverse=True) # 修正排序键
            active_hours = [hour for hour, count in sorted_hours[:3]]
        
        # 计算主要话题
        topic_preferences = profile.topic_preferences if hasattr(profile, 'topic_preferences') else profile.get('topic_preferences', {})
        main_topics = sorted(topic_preferences.items(), 
                           key=lambda x: x[1], reverse=True)[:3] # 修正排序键
        
        # 计算社交活跃度
        social_activity = len(self.social_graph.get(qq_id, []))
        
        # 使用LLM生成深度洞察
        deep_insights = await self._generate_deep_insights(profile)
        
        return {
            'user_id': qq_id,
            'user_name': profile.qq_name if hasattr(profile, 'qq_name') else profile.get('name', f'用户{qq_id}'),
            'nicknames': profile.nicknames if hasattr(profile, 'nicknames') else profile.get('nicknames', []),
            'active_hours': active_hours,
            'main_topics': [topic for topic, count in main_topics],
            'social_activity': social_activity,
            'communication_style_summary': self._summarize_communication_style(profile),
            'activity_summary': self._summarize_activity_pattern(profile),
            'deep_insights': deep_insights,
            'personality_analysis': await self._analyze_personality_traits(profile),
            'social_behavior': await self._analyze_social_behavior(qq_id)
        }

    async def _generate_deep_insights(self, profile) -> Dict[str, Any]:
        """使用LLM生成深度用户洞察"""
        # 检查适配器和refine provider是否可用
        if not self.llm_adapter or not self.llm_adapter.has_refine_provider():
            logger.warning("提炼模型LLM客户端未初始化，无法使用LLM生成深度用户洞察。")
            return {"error": "LLM服务不可用"}

        try:
            # 兼容处理UserProfile对象和dict
            def get_attr(obj, attr, default=None):
                if hasattr(obj, attr):
                    return getattr(obj, attr)
                elif isinstance(obj, dict):
                    return obj.get(attr, default)
                return default
                
            # 准备用户数据摘要
            qq_name = get_attr(profile, 'qq_name', get_attr(profile, 'name', '未知用户'))
            nicknames = get_attr(profile, 'nicknames', [])
            topic_preferences = get_attr(profile, 'topic_preferences', {})
            activity_pattern = get_attr(profile, 'activity_pattern', {})
            social_connections = get_attr(profile, 'social_connections', [])
            
            user_data_summary = {
                'qq_name': qq_name,
                'nicknames': nicknames,
                'topic_preferences': dict(list(topic_preferences.items())[:5]) if topic_preferences else {},
                'activity_pattern': {
                    'peak_hours': [k for k, v in sorted(
                        activity_pattern.get('activity_hours', {}).items(),
                        key=lambda item: item[1], reverse=True
                    )[:3]],
                    'avg_message_length': sum(activity_pattern.get('message_lengths', [])) / 
                                        max(len(activity_pattern.get('message_lengths', [])), 1)
                },
                'social_connections': len(social_connections)
            }
            
            prompt = self.prompts.JSON_ONLY_SYSTEM_PROMPT + "\n\n" + self.prompts.MULTIDIMENSIONAL_ANALYZER_DEEP_INSIGHTS_PROMPT.format(
                user_data_summary=json.dumps(user_data_summary, ensure_ascii=False, indent=2)
            )
            
            if self.llm_adapter and self.llm_adapter.has_refine_provider():
                response = await self.llm_adapter.refine_chat_completion(
                    prompt=prompt,
                    temperature=0.1
                )
            else:
                response = None
            
            if response:
                # response 是字符串
                try:
                    insights = safe_parse_llm_json(response.strip())
                    return insights
                except json.JSONDecodeError:
                    logger.warning(f"LLM响应JSON解析失败，返回简化分析。响应内容: {response.strip()}")
                    return {
                        "personality_type": "分析中",
                        "communication_preference": "待深入分析",
                        "social_role": "群体成员",
                        "learning_potential": 0.7
                    }
            return {"error": "LLM未返回有效响应"}
                
        except Exception as e:
            logger.warning(f"深度洞察生成失败: {e}")
            return {"error": "洞察生成失败"}

    async def _analyze_personality_traits(self, profile) -> Dict[str, float]:
        """分析用户人格特质"""
        # 检查适配器和refine provider是否可用
        if not self.llm_adapter or not self.llm_adapter.has_refine_provider():
            logger.warning("提炼模型LLM客户端未初始化，无法使用LLM分析人格特质，使用简化算法。")
            return self._simple_personality_analysis(profile)

        try:
            # 兼容处理UserProfile对象和dict
            communication_style = profile.communication_style if hasattr(profile, 'communication_style') else profile.get('communication_style', {})
            
            # 获取最近的沟通风格数据
            recent_styles = {}
            for feature, values in communication_style.items():
                if values:
                    recent_styles[feature] = sum(values[-10:]) / min(len(values), 10)
            
            prompt = self.prompts.JSON_ONLY_SYSTEM_PROMPT + "\n\n" + self.prompts.MULTIDIMENSIONAL_ANALYZER_PERSONALITY_TRAITS_PROMPT.format(
                communication_style_data=json.dumps(recent_styles, ensure_ascii=False, indent=2)
            )
            
            if self.llm_adapter and self.llm_adapter.has_refine_provider():
                response = await self.llm_adapter.refine_chat_completion(
                    prompt=prompt,
                    temperature=0.1
                )
            else:
                response = None
            
            if response:
                # response 是字符串
                try:
                    traits = safe_parse_llm_json(response.strip())
                    return traits
                except json.JSONDecodeError:
                    logger.warning(f"LLM响应JSON解析失败，返回简化人格分析。响应内容: {response.strip()}")
                    return self._simple_personality_analysis(profile)
            return self._simple_personality_analysis(profile)
                
        except Exception as e:
            logger.warning(f"人格特质分析失败: {e}")
            return self._simple_personality_analysis(profile)

    def _simple_personality_analysis(self, profile) -> Dict[str, float]:
        """简化的人格分析（备用）"""
        # 兼容处理UserProfile对象和dict
        communication_style = profile.communication_style if hasattr(profile, 'communication_style') else profile.get('communication_style', {})
        topic_preferences = profile.topic_preferences if hasattr(profile, 'topic_preferences') else profile.get('topic_preferences', {})
        
        # 基于基础数据的简单分析
        style_data = communication_style
        
        # 外向性：基于消息频率和长度
        extraversion = 0.5
        if 'length' in style_data and style_data['length']:
            avg_length = sum(style_data['length'][-20:]) / min(len(style_data['length']), 20)
            extraversion = min(avg_length / 100, 1.0)
        
        # 开放性：基于话题多样性
        openness = len(topic_preferences) / 10 if topic_preferences else 0.5
        
        return {
            "openness": min(openness, 1.0),
            "conscientiousness": 0.6, # 默认值
            "extraversion": extraversion,
            "agreeableness": 0.7, # 默认值
            "neuroticism": 0.3 # 默认值
        }

    async def _analyze_social_behavior(self, qq_id: str) -> Dict[str, Any]:
        """分析社交行为模式"""
        if qq_id not in self.social_graph:
            return {"interaction_count": 0, "relationship_strength": {}}
        
        relations = self.social_graph[qq_id]
        
        # 统计不同类型的社交行为
        behavior_stats = {
            "mention_frequency": len([r for r in relations if r.relation_type == 'mention']),
            "reply_frequency": len([r for r in relations if r.relation_type == 'reply']),
            "total_interactions": len(relations),
            "avg_relationship_strength": sum(r.strength for r in relations) / max(len(relations), 1),
            "top_connections": [
                {"user": r.to_user, "strength": r.strength, "frequency": r.frequency}
                for r in sorted(relations, key=lambda x: x.strength, reverse=True)[:5]
            ]
        }
        
        return behavior_stats

    def _summarize_communication_style(self, profile) -> Dict[str, str]:
        """总结沟通风格"""
        style_summary = {}
        
        # 兼容处理UserProfile对象和dict
        communication_style = profile.communication_style if hasattr(profile, 'communication_style') else profile.get('communication_style', {})
        
        if 'length' in communication_style and communication_style['length']:
            avg_length = sum(communication_style['length']) / len(communication_style['length'])
            if avg_length > 50:
                style_summary['length_style'] = '详细型'
            elif avg_length > 20:
                style_summary['length_style'] = '适中型'
            else:
                style_summary['length_style'] = '简洁型'
        
        return style_summary

    def _summarize_activity_pattern(self, profile) -> Dict[str, Any]:
        """总结活动模式"""
        activity_summary = {}
        
        # 兼容处理UserProfile对象和dict
        activity_pattern = profile.activity_pattern if hasattr(profile, 'activity_pattern') else profile.get('activity_pattern', {})
        
        if 'activity_hours' in activity_pattern:
            hours = activity_pattern['activity_hours']
            if hours:
                peak_hour = max(hours.items(), key=lambda x: x[1])[0] # 修正为获取键
                activity_summary['peak_hour'] = peak_hour
                activity_summary['peak_period'] = self._get_time_period(peak_hour)
        
        return activity_summary

    async def export_social_graph(self) -> Dict[str, Any]:
        """导出社交关系图谱"""
        graph_data = {
            'nodes': [],
            'edges': [],
            'statistics': {}
        }
        
        # 导出节点（用户）
        # 从数据库加载所有用户画像，而不是只���内存中获取
        # 为了简化，这里仍然使用内存中的 user_profiles，但实际应该从数据库加载
        for user_key, profile in self.user_profiles.items():
            # 从user_key中提取用户ID用于显示
            display_id = user_key.split(':')[-1] if ':' in user_key else user_key
            
            # 兼容处理UserProfile对象和dict
            if hasattr(profile, 'qq_name'):
                name = profile.qq_name
                nicknames = profile.nicknames
                activity_level = len(profile.activity_pattern.get('activity_hours', {}))
            else:
                name = profile.get('name', f'用户{display_id}')
                nicknames = profile.get('nicknames', [])
                activity_level = len(profile.get('activity_pattern', {}).get('activity_hours', {}))
            
            graph_data['nodes'].append({
                'id': display_id,
                'name': name,
                'nicknames': nicknames,
                'user_key': user_key,
                'activity_level': activity_level
            })
        
        # 导出边（关系）
        # 从数据库加载所有社交关系，而不是只从内存中获取
        # 为了简化，这里仍然使用内存中的 social_graph，但实际应该从数据库加载
        for from_user, relations in self.social_graph.items():
            for relation in relations:
                graph_data['edges'].append({
                    'from': from_user,
                    'to': relation.to_user,
                    'type': relation.relation_type,
                    'strength': relation.strength,
                    'frequency': relation.frequency
                })
        
        # 统计信息
        graph_data['statistics'] = {
            'total_users': len(self.user_profiles),
            'total_relations': sum(len(relations) for relations in self.social_graph.values()),
            'nickname_mappings': len(self.nickname_mapping)
        }
        
        return graph_data
    
    async def stop(self):
        """停止多维度分析器服务"""
        try:
            # 取消定期清理任务
            if hasattr(self, '_cleanup_task') and self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
                self._cleanup_task = None
            
            # 保存重要的用户画像数据到数据库（如果需要持久化）
            try:
                await self._save_user_profiles_to_db()
            except Exception as e:
                logger.warning(f"保存用户画像到数据库失败: {e}")
            
            # 清理内存数据
            if hasattr(self, 'user_profiles'):
                self.user_profiles.clear()
            if hasattr(self, 'social_graph'):
                self.social_graph.clear()
            if hasattr(self, '_analysis_cache'):
                self._analysis_cache.clear()
            if hasattr(self, 'nickname_mapping'):
                self.nickname_mapping.clear()
            
            logger.info("多维度分析器已停止")
            return True
            
        except Exception as e:
            logger.error(f"停止多维度分析器失败: {e}")
            return False
    
    async def _save_user_profiles_to_db(self):
        """保存用户画像数据到数据库"""
        try:
            if not self.user_profiles:
                return
                
            # 这里可以实现将用户画像数据保存到专门的用户画像表
            # 当前简化实现，仅记录统计信息
            logger.info(f"需要保存 {len(self.user_profiles)} 个用户画像到数据库")
            
            # TODO: 实现具体的数据库保存逻辑
            # 例如：CREATE TABLE user_profiles (group_id, user_id, profile_data, updated_at)
            
        except Exception as e:
            logger.error(f"保存用户画像到数据库失败: {e}")
