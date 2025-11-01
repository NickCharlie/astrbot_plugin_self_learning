"""
人格更新服务 - 基于AstrBot框架的人格管理
"""
import os
import logging
import time # 导入 time 模块
from datetime import datetime
from typing import Dict, List, Any, Optional

from astrbot.api.star import Context
from astrbot.core.provider.provider import Personality
from ..config import PluginConfig

from ..core.interfaces import IPersonaUpdater, IPersonaBackupManager, MessageData, AnalysisResult, PersonaUpdateRecord # 导入 PersonaUpdateRecord

from ..exceptions import PersonaUpdateError, SelfLearningError # 导入 PersonaUpdateError
from .database_manager import DatabaseManager # 导入 DatabaseManager

# MaiBot功能模块导入 - 结合MaiBot的学习功能
from .expression_pattern_learner import ExpressionPatternLearner
from .memory_graph_manager import MemoryGraphManager
from .knowledge_graph_manager import KnowledgeGraphManager


class PersonaUpdater(IPersonaUpdater):
    """
    基于AstrBot框架的人格更新器
    直接操作框架的 curr_personality 属性
    """
    
    def __init__(self, config: PluginConfig, context: Context, backup_manager: IPersonaBackupManager, llm_client: Optional[Any] = None, db_manager: DatabaseManager = None):
        self.config = config
        self.context = context
        self.backup_manager = backup_manager
        # llm_client参数保持为了兼容性，但不使用
        self.db_manager = db_manager # 添加 db_manager
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # 初始化MaiBot组件 - 结合MaiBot功能
        self.expression_learner = ExpressionPatternLearner.get_instance()
        self.memory_graph_manager = MemoryGraphManager.get_instance()
        self.knowledge_graph_manager = KnowledgeGraphManager.get_instance()
        
        self._logger.info("PersonaUpdater初始化完成，已集成MaiBot功能模块")
        
    async def update_persona_with_style(self, group_id: str, style_analysis: Dict[str, Any], filtered_messages: List[MessageData]) -> bool:
        """根据风格分析和筛选过的消息更新人格"""
        try:
            # 获取当前提供商
            provider = self.context.get_using_provider()
            if not provider:
                self._logger.error("无法获取当前LLM提供商")
                return False
            
            # 检查是否有当前人格
            # 这里需要考虑如何根据 group_id 获取特定会话的人格
            # 暂时仍然使用 curr_personality，但如果 astrbot 核心支持会话人格，这里需要修改
            if not hasattr(provider, 'curr_personality') or not provider.curr_personality:
                self._logger.error("当前提供商没有设置人格")
                return False
            
            current_persona = provider.curr_personality
            self._logger.info(f"当前人格: {current_persona.get('name', 'unknown')} for group {group_id}")
            
            # 1. 生成基于风格分析的增量更新特征并写入txt文件
            await self._generate_and_save_style_features(group_id, style_analysis)
            
            # 更新人格prompt
            if 'enhanced_prompt' in style_analysis:
                original_prompt = current_persona.get('prompt', '')
                enhanced_prompt = self._merge_prompts(original_prompt, style_analysis['enhanced_prompt'])
                
                # 记录人格更新以便人工审查
                await self.record_persona_update_for_review(PersonaUpdateRecord(
                    timestamp=time.time(),
                    group_id=group_id,
                    update_type="prompt_update",
                    original_content=original_prompt,
                    new_content=enhanced_prompt,
                    reason="风格分析建议更新prompt"
                ))
                
                current_persona['prompt'] = enhanced_prompt
                self._logger.info(f"人格prompt已更新，长度: {len(enhanced_prompt)} for group {group_id}")
            
            # 3. 更新对话风格特征（使用MaiBot的表达模式学习而不是直接保存对话）
            if filtered_messages:
                await self._update_style_based_features_with_maibot(current_persona, style_analysis, filtered_messages)
            
            # 更新其他风格属性
            if 'style_attributes' in style_analysis: # 从 style_analysis 中获取 style_attributes
                await self._apply_style_attributes(current_persona, style_analysis['style_attributes'])
            
            self._logger.info(f"人格更新成功 for group {group_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"人格更新失败 for group {group_id}: {e}")
            raise SelfLearningError(f"人格更新失败: {str(e)}")
    
    async def record_persona_update_for_review(self, record: PersonaUpdateRecord) -> int:
        """记录需要人工审查的人格更新"""
        try:
            record_dict = record.__dict__
            # 移除 id 字段，因为它是自增的
            record_dict.pop('id', None) 
            record_id = await self.db_manager.save_persona_update_record(record_dict)
            self._logger.info(f"已记录人格更新待审查，ID: {record_id}")
            return record_id
        except Exception as e:
            self._logger.error(f"记录人格更新待审查失败: {e}")
            raise PersonaUpdateError(f"记录人格更新待审查失败: {str(e)}")

    async def get_pending_persona_updates(self) -> List[PersonaUpdateRecord]:
        """获取所有待审查的人格更新"""
        try:
            records_data = await self.db_manager.get_pending_persona_update_records()
            return [PersonaUpdateRecord(**data) for data in records_data]
        except Exception as e:
            self._logger.error(f"获取待审查人格更新失败: {e}")
            return []

    async def review_persona_update(self, update_id: int, status: str, reviewer_comment: Optional[str] = None) -> bool:
        """审查人格更新"""
        try:
            result = await self.db_manager.update_persona_update_record_status(update_id, status, reviewer_comment)
            if result:
                self._logger.info(f"人格更新 {update_id} 已审查为 {status}")
            return result
        except Exception as e:
            self._logger.error(f"审查人格更新失败: {e}")
            raise PersonaUpdateError(f"审查人格更新失败: {str(e)}")

    async def get_current_persona_description(self, group_id: str) -> Optional[str]:
        """获取当前人格的描述"""
        try:
            # 这里需要考虑如何根据 group_id 获取特定会话的人格
            provider = self.context.get_using_provider()
            if provider and provider.curr_personality:
                return provider.curr_personality.get('prompt', '')
            return None
        except Exception as e:
            self._logger.error(f"获取当前人格描述失败 for group {group_id}: {e}")
            return None

    async def get_current_persona(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取当前人格信息"""
        try:
            # 这里需要考虑如何根据 group_id 获取特定会话的人格
            provider = self.context.get_using_provider()
            if provider and provider.curr_personality:
                return dict(provider.curr_personality)
            return None
            
        except Exception as e:
            self._logger.error(f"获取当前人格失败 for group {group_id}: {e}")
            return None
    
    def _merge_prompts(self, original: str, enhancement: str) -> str:
        """合并原始prompt和增强prompt"""
        if not original:
            return enhancement
        
        if not enhancement:
            return original
        
        # 智能合并策略
        if self.config.persona_merge_strategy == "replace":
            return enhancement
        elif self.config.persona_merge_strategy == "append":
            return f"{original}\n\n{enhancement}"
        elif self.config.persona_merge_strategy == "prepend":
            return f"{enhancement}\n\n{original}"
        else:  # smart merge
            return self._smart_merge_prompts(original, enhancement)
    
    def _smart_merge_prompts(self, original: str, enhancement: str) -> str:
        """智能合并prompt"""
        # 检查重叠内容，避免重复
        words_original = set(original.lower().split())
        words_enhancement = set(enhancement.lower().split())
        
        overlap_ratio = len(words_original.intersection(words_enhancement)) / max(len(words_original), 1)
        
        if overlap_ratio > 0.7:  # 高重叠，选择较长的
            return enhancement if len(enhancement) > len(original) else original
        else:  # 低重叠，合并
            return f"{original}\n\n补充风格特征：{enhancement}"
    
    async def _update_mood_imitation_dialogs(self, persona: Personality, filtered_messages: List[Dict[str, Any]]):
        """更新对话风格模仿"""
        try:
            current_dialogs = persona.get('mood_imitation_dialogs', [])
            
            # 从过滤后的消息中提取高质量对话
            new_dialogs = []
            for msg in filtered_messages[-10:]:  # 取最近10条
                message_text = msg.get('message', '').strip()
                if message_text and len(message_text) > self.config.message_min_length:
                    if message_text not in current_dialogs:
                        new_dialogs.append(message_text)
            
            if new_dialogs:
                # 保持对话列表长度合理
                max_dialogs = self.config.max_mood_imitation_dialogs or 20
                all_dialogs = current_dialogs + new_dialogs
                
                if len(all_dialogs) > max_dialogs:
                    # 保留最新的对话
                    all_dialogs = all_dialogs[-max_dialogs:]
                
                persona['mood_imitation_dialogs'] = all_dialogs
                self._logger.info(f"更新对话风格模仿，新增{len(new_dialogs)}条，总计{len(all_dialogs)}条")
            
        except Exception as e:
            self._logger.error(f"更新对话风格模仿失败: {e}")
    
    async def _apply_style_attributes(self, persona: Personality, style_attributes: Dict[str, Any]):
        """应用风格属性"""
        try:
            current_prompt = persona.get('prompt', '')
            
            # 根据风格属性调整prompt
            if 'tone' in style_attributes:
                tone = style_attributes['tone']
                tone_instruction = f"请保持{tone}的语调。"
                if tone_instruction not in current_prompt:
                    current_prompt = f"{current_prompt}\n\n{tone_instruction}"
            
            if 'formality' in style_attributes:
                formality = style_attributes['formality']
                if formality == 'formal':
                    formality_instruction = "请使用正式的表达方式。"
                elif formality == 'casual':
                    formality_instruction = "请使用轻松随意的表达方式。"
                else:
                    formality_instruction = ""
                
                if formality_instruction and formality_instruction not in current_prompt:
                    current_prompt = f"{current_prompt}\n\n{formality_instruction}"
            
            if 'emotion' in style_attributes:
                emotion = style_attributes['emotion']
                if emotion and f"情感倾向：{emotion}" not in current_prompt:
                    current_prompt = f"{current_prompt}\n\n情感倾向：{emotion}"
            
            persona['prompt'] = current_prompt
            self._logger.info("风格属性应用成功")
            
        except Exception as e:
            self._logger.error(f"应用风格属性失败: {e}")
    
    async def analyze_persona_compatibility(self, target_style: Dict[str, Any]) -> AnalysisResult:
        """分析目标风格与当前人格的兼容性"""
        try:
            current_persona = await self.get_current_persona()
            if not current_persona:
                return AnalysisResult(
                    success=False,
                    confidence=0.0,
                    data={},
                    error="无法获取当前人格"
                )
            
            current_prompt = current_persona.get('prompt', '')
            target_attributes = target_style.get('style_attributes', {})
            
            # 简单的兼容性评分
            compatibility_score = 0.8  # 基础分数
            
            # 检查风格冲突
            conflicts = []
            if 'tone' in target_attributes:
                target_tone = target_attributes['tone'].lower()
                if ('严肃' in current_prompt.lower() and target_tone == 'humor') or \
                   ('幽默' in current_prompt.lower() and target_tone == 'serious'):
                    conflicts.append('语调冲突')
                    compatibility_score -= 0.2
            
            return AnalysisResult(
                success=True,
                confidence=compatibility_score,
                data={
                    'compatibility_score': compatibility_score,
                    'conflicts': conflicts,
                    'current_persona_name': current_persona.get('name', 'unknown'),
                    'recommended_action': 'merge' if compatibility_score > 0.6 else 'replace'
                }
            )
            
        except Exception as e:
            self._logger.error(f"人格兼容性分析失败: {e}")
            return AnalysisResult(
                success=False,
                confidence=0.0,
                data={},
                error=str(e)
            )


class PersonaAnalyzer:
    """人格分析器 - 分析人格特征和变化"""
    
    def __init__(self, config: PluginConfig):
        self.config = config
        self._logger = logging.getLogger(self.__class__.__name__)
    
    async def analyze_persona_evolution(self, persona_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析人格演化趋势"""
        if len(persona_history) < 2:
            return {
                'evolution_detected': False,
                'message': '人格历史数据不足'
            }
        
        try:
            # 分析prompt长度变化
            prompt_lengths = [len(p.get('prompt', '')) for p in persona_history]
            length_trend = 'increasing' if prompt_lengths[-1] > prompt_lengths else 'decreasing'
            
            # 分析关键词变化
            all_keywords = []
            for persona in persona_history:
                prompt = persona.get('prompt', '').lower()
                keywords = self._extract_keywords(prompt)
                all_keywords.extend(keywords)
            
            keyword_frequency = {}
            for keyword in all_keywords:
                keyword_frequency[keyword] = keyword_frequency.get(keyword, 0) + 1
            
            most_common_keywords = sorted(keyword_frequency.items(), key=lambda x: x, reverse=True)[:10][1]
            
            return {
                'evolution_detected': True,
                'prompt_length_trend': length_trend,
                'most_common_keywords': most_common_keywords,
                'total_versions': len(persona_history),
                'analysis_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            self._logger.error(f"人格演化分析失败: {e}")
            return {
                'evolution_detected': False,
                'error': str(e)
            }
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        # 简单的关键词提取
        words = text.split()
        keywords = []
        
        important_words = ['友好', '专业', '幽默', '严肃', '活泼', '温和', '耐心', '热情']
        
        for word in words:
            if any(important in word for important in important_words):
                keywords.append(word)
        
        return keywords

    async def _generate_and_save_style_features(self, group_id: str, style_analysis: Dict[str, Any]) -> bool:
        """
        基于风格分析生成增量更新特征并保存到persona_updates.txt文件
        结合MaiBot的表达模式学习功能
        """
        try:
            self._logger.info(f"开始生成风格特征 for group {group_id}")
            
            # 从风格分析中提取关键信息
            style_features = []
            
            # 1. 从style_analysis中提取通用风格特征
            if 'style_analysis' in style_analysis:
                analysis_data = style_analysis['style_analysis']
                
                # 提取语言风格特征
                if 'language_style' in analysis_data:
                    lang_style = analysis_data['language_style']
                    if isinstance(lang_style, dict):
                        if lang_style.get('formality', 0) > 0.7:
                            style_features.append("+ 使用正式礼貌的表达方式")
                        elif lang_style.get('formality', 0) < 0.3:
                            style_features.append("+ 使用轻松随意的语调")
                        
                        if lang_style.get('enthusiasm', 0) > 0.7:
                            style_features.append("+ 表现出热情活跃的态度")
                        elif lang_style.get('enthusiasm', 0) < 0.3:
                            style_features.append("+ 保持冷静内敛的风格")
                
                # 提取情绪表达特征
                if 'emotional_patterns' in analysis_data:
                    emotions = analysis_data['emotional_patterns']
                    if isinstance(emotions, dict):
                        dominant_emotion = emotions.get('dominant_emotion')
                        if dominant_emotion:
                            emotion_map = {
                                'positive': '+ 更多使用积极正面的表达',
                                'cheerful': '+ 表现出开朗乐观的性格',
                                'calm': '+ 保持平和理性的语调',
                                'enthusiastic': '+ 展现热情饱满的精神状态'
                            }
                            if dominant_emotion in emotion_map:
                                style_features.append(emotion_map[dominant_emotion])
                
                # 提取交互特征
                if 'interaction_style' in analysis_data:
                    interaction = analysis_data['interaction_style']
                    if isinstance(interaction, dict):
                        if interaction.get('response_length') == 'detailed':
                            style_features.append("~ 回复时提供更详细的解释")
                        elif interaction.get('response_length') == 'concise':
                            style_features.append("~ 回复时保持简洁明了")
                        
                        if interaction.get('question_tendency', 0) > 0.6:
                            style_features.append("+ 适当主动提问以了解更多信息")
            
            # 2. 使用MaiBot的表达模式学习来生成场景-表达特征
            if hasattr(self, 'expression_learner') and self.expression_learner:
                try:
                    # 将style_analysis转换为消息格式供表达学习器使用
                    mock_messages = []
                    if 'common_phrases' in style_analysis.get('style_analysis', {}):
                        phrases = style_analysis['style_analysis']['common_phrases']
                        if isinstance(phrases, list):
                            for i, phrase in enumerate(phrases[:5]):  # 取前5个短语
                                mock_messages.append(MessageData(
                                    sender_id=f"style_user_{i}",
                                    sender_name=f"分析用户{i}",
                                    message=phrase,
                                    group_id=group_id,
                                    timestamp=time.time(),
                                    platform="style_analysis"
                                ))
                    
                    if mock_messages:
                        # 使用表达模式学习器分析
                        patterns = await self.expression_learner.learn_expression_patterns(mock_messages, group_id)
                        
                        # 将学习到的表达模式转换为增量特征
                        for pattern in patterns[:3]:  # 取前3个模式
                            if hasattr(pattern, 'scene') and hasattr(pattern, 'expression'):
                                feature = f"~ 当{pattern.scene}时，使用\"{pattern.expression}\"这样的表达方式"
                                style_features.append(feature)
                
                except Exception as e:
                    self._logger.warning(f"MaiBot表达模式学习失败: {e}")
            
            # 3. 如果没有提取到足够特征，添加通用特征
            if len(style_features) < 2:
                style_features.extend([
                    "~ 根据对话风格调整回复的语气和表达方式",
                    "+ 保持与用户交流风格的一致性"
                ])
            
            # 4. 保存特征到persona_updates.txt文件
            if style_features:
                # 创建persona_updates.txt文件路径
                persona_updates_file = os.path.join(self.config.data_dir, "persona_updates.txt")
                
                # 写入增量更新特征
                update_content = "\n".join(style_features)
                await self._append_to_persona_updates_file(update_content, persona_updates_file)
                
                self._logger.info(f"已保存 {len(style_features)} 个风格特征到 persona_updates.txt")
                return True
            else:
                self._logger.warning("未能提取到风格特征")
                return False
                
        except Exception as e:
            self._logger.error(f"生成和保存风格特征失败: {e}")
            return False

    async def _update_style_based_features_with_maibot(self, persona: Personality, style_analysis: Dict[str, Any], filtered_messages: List[MessageData]) -> bool:
        """
        使用MaiBot功能更新风格特征，而不是直接保存对话内容
        """
        try:
            self._logger.info("使用MaiBot功能更新风格特征...")
            
            # 1. 使用记忆图管理器处理消息
            if hasattr(self, 'memory_graph_manager') and self.memory_graph_manager:
                try:
                    for message in filtered_messages[-5:]:  # 处理最近5条消息
                        # 转换格式
                        if isinstance(message, dict):
                            msg_data = MessageData(
                                sender_id=message.get('sender_id', ''),
                                sender_name=message.get('sender_name', ''),
                                message=message.get('message', ''),
                                group_id=message.get('group_id', ''),
                                timestamp=message.get('timestamp', time.time()),
                                platform=message.get('platform', 'unknown')
                            )
                        else:
                            msg_data = message
                        
                        # 添加到记忆图
                        await self.memory_graph_manager.add_memory_from_message(msg_data, msg_data.group_id)
                    
                    self._logger.info("记忆图更新完成")
                except Exception as e:
                    self._logger.warning(f"记忆图更新失败: {e}")
            
            # 2. 使用知识图谱管理器提取语言模式
            if hasattr(self, 'knowledge_graph_manager') and self.knowledge_graph_manager:
                try:
                    for message in filtered_messages[-3:]:  # 处理最近3条消息
                        # 转换格式
                        if isinstance(message, dict):
                            msg_data = MessageData(
                                sender_id=message.get('sender_id', ''),
                                sender_name=message.get('sender_name', ''),
                                message=message.get('message', ''),
                                group_id=message.get('group_id', ''),
                                timestamp=message.get('timestamp', time.time()),
                                platform=message.get('platform', 'unknown')
                            )
                        else:
                            msg_data = message
                        
                        # 处理知识图谱
                        await self.knowledge_graph_manager.process_message_for_knowledge_graph(msg_data, msg_data.group_id)
                    
                    self._logger.info("知识图谱更新完成")
                except Exception as e:
                    self._logger.warning(f"知识图谱更新失败: {e}")
            
            # 3. 更新人格的mood_imitation_dialogs为分析出的特征而不是原始对话
            current_dialogs = persona.get('mood_imitation_dialogs', [])
            
            # 从风格分析中提取代表性表达方式
            new_features = []
            if 'style_analysis' in style_analysis:
                analysis_data = style_analysis['style_analysis']
                
                # 提取常用短语作为特征示例
                if 'common_phrases' in analysis_data:
                    phrases = analysis_data['common_phrases']
                    if isinstance(phrases, list):
                        for phrase in phrases[:5]:  # 最多5个特征短语
                            if phrase and len(phrase.strip()) > 3:
                                new_features.append(f"风格特征: {phrase.strip()}")
                
                # 提取语调特征
                if 'tone_indicators' in analysis_data:
                    tones = analysis_data['tone_indicators']
                    if isinstance(tones, list):
                        for tone in tones[:3]:  # 最多3个语调特征
                            if tone:
                                new_features.append(f"语调特征: {tone}")
            
            # 如果没有提取到特征，使用默认的风格描述
            if not new_features:
                new_features = [
                    "风格特征: 基于对话分析的个性化表达",
                    "交流特征: 适应用户的交流偏好"
                ]
            
            # 合并现有特征和新特征
            max_features = self.config.max_mood_imitation_dialogs or 20
            all_features = current_dialogs + new_features
            
            if len(all_features) > max_features:
                # 保留最新的特征
                all_features = all_features[-max_features:]
            
            persona['mood_imitation_dialogs'] = all_features
            self._logger.info(f"使用MaiBot功能更新风格特征，新增{len(new_features)}个特征，总计{len(all_features)}个")
            
            return True
            
        except Exception as e:
            self._logger.error(f"使用MaiBot功能更新风格特征失败: {e}")
            return False

    async def _append_to_persona_updates_file(self, update_content: str, file_path: str):
        """向人格更新文件追加内容"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                # 创建文件头部
                header_content = """# 增量人格更新文件
# 本文件用于存储增量的人格文本更新
# 每次执行时会读取此文件的新内容并应用到当前人格

# 格式：每行一条增量更新，支持以下格式：
# 1. 直接添加特征：+ 特征描述
# 2. 修改行为：~ 行为描述
# 3. 注释行：# 开头的行会被忽略

# 示例：
# + 更加幽默风趣，喜欢使用轻松的语调
# ~ 回复时更加亲切，经常使用感叹号
# + 对新技术话题表现出浓厚兴趣

# 以下是待应用的增量更新：

"""
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(header_content)
            
            # 追加新内容
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{update_content}\n")
            
            self._logger.info(f"已向 {file_path} 追加增量更新内容")
            
        except Exception as e:
            self._logger.error(f"写入人格更新文件失败: {e}")

    async def stop(self):
        """停止服务"""
        try:
            self._logger.info("人格更新服务已停止")
            return True
        except Exception as e:
            self._logger.error(f"停止人格更新服务失败: {e}")
            return False
