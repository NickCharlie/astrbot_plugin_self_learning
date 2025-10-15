"""
人格更新服务 - 基于AstrBot框架的人格管理
"""
import logging
import time # 导入 time 模块
from datetime import datetime
from typing import Dict, List, Any, Optional

from astrbot.api.star import Context
from astrbot.core.provider.provider import Personality
try:
    from ..config import PluginConfig
except ImportError:
    from astrbot_plugin_self_learning.config import PluginConfig

try:
    from ..core.interfaces import IPersonaUpdater, IPersonaBackupManager, MessageData, AnalysisResult, PersonaUpdateRecord # 导入 PersonaUpdateRecord
except ImportError:
    from astrbot_plugin_self_learning.core.interfaces import IPersonaUpdater, IPersonaBackupManager, MessageData, AnalysisResult, PersonaUpdateRecord # 导入 PersonaUpdateRecord

try:
    from ..exceptions import PersonaUpdateError, SelfLearningError # 导入 PersonaUpdateError
except ImportError:
    from astrbot_plugin_self_learning.exceptions import PersonaUpdateError, SelfLearningError # 导入 PersonaUpdateError
from .database_manager import DatabaseManager # 导入 DatabaseManager


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
            
            # 更新对话风格模仿
            if filtered_messages: # 直接使用传入的 filtered_messages
                await self._update_mood_imitation_dialogs(current_persona, filtered_messages)
            
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

    async def stop(self):
        """停止服务"""
        try:
            self._logger.info("人格更新服务已停止")
            return True
        except Exception as e:
            self._logger.error(f"停止人格更新服务失败: {e}")
            return False
