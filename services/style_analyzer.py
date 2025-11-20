"""
风格分析服务 - 使用强模型深度分析对话风格并提炼特征
"""
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context

from ..core.framework_llm_adapter import FrameworkLLMAdapter  # 导入框架适配器

from ..config import PluginConfig

from ..exceptions import StyleAnalysisError, ModelAccessError

from .database_manager import DatabaseManager

from ..utils.json_utils import safe_parse_llm_json


@dataclass
class StyleProfile:
    """风格档案"""
    vocabulary_richness: float = 0.0      # 词汇丰富度
    sentence_complexity: float = 0.0      # 句式复杂度
    emotional_expression: float = 0.0     # 情感表达度
    interaction_tendency: float = 0.0     # 互动倾向
    topic_diversity: float = 0.0          # 话题多样性
    formality_level: float = 0.0          # 正式程度
    creativity_score: float = 0.0         # 创造性得分

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于JSON序列化"""
        return {
            'vocabulary_richness': self.vocabulary_richness,
            'sentence_complexity': self.sentence_complexity,
            'emotional_expression': self.emotional_expression,
            'interaction_tendency': self.interaction_tendency,
            'topic_diversity': self.topic_diversity,
            'formality_level': self.formality_level,
            'creativity_score': self.creativity_score
        }


@dataclass
class StyleEvolution:
    """风格演化记录"""
    timestamp: str
    old_profile: StyleProfile
    new_profile: StyleProfile
    evolution_vector: Dict[str, float]
    significance: float

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于JSON序列化"""
        return {
            'timestamp': self.timestamp,
            'old_profile': self.old_profile.to_dict(),
            'new_profile': self.new_profile.to_dict(),
            'evolution_vector': self.evolution_vector,
            'significance': self.significance
        }


class StyleAnalyzerService:
    """风格分析服务"""
    
    def __init__(self, config: PluginConfig, context: Context, database_manager: DatabaseManager, 
                 llm_adapter: Optional[FrameworkLLMAdapter] = None,
                 prompts: Any = None):
        self.config = config
        self.context = context
        self.db_manager = database_manager  # 注入 DatabaseManager 实例
        self.prompts = prompts  # 保存 prompts
        
        # 使用框架适配器
        self.llm_adapter = llm_adapter
        
        # 风格演化历史
        self.style_evolution_history: List[StyleEvolution] = []
        
        # 当前基准风格档案
        self.baseline_style: Optional[StyleProfile] = None
        
        logger.info("风格分析服务初始化完成")

    async def start(self):
        """服务启动时加载基准风格档案"""
        # 假设每个群组有独立的风格档案，这里需要一个 group_id
        # 为了简化，暂时假设加载一个默认的或全局的风格档案
        # 实际应用中，可能需要根据当前处理的群组ID来加载
        default_group_id = "global_style" # 或者从配置中获取
        loaded_profile_data = await self.db_manager.load_style_profile(default_group_id, "baseline_style_profile")
        if loaded_profile_data:
            self.baseline_style = StyleProfile(**loaded_profile_data)
            logger.info("已从数据库加载基准风格档案。")
        else:
            logger.info("未找到基准风格档案，将从零开始。")

    async def analyze_conversation_style(self, group_id: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析对话风格，使用强模型进行深度分析"""
        try:
            if not messages:
                return {"error": "没有消息数据"}
            
            # 检查框架适配器是否可用
            if not self.llm_adapter or not self.llm_adapter.has_refine_provider():
                return {"error": "提炼模型适配器未配置，无法进行风格分析。"}
            
            # 准备分析数据
            message_texts = [msg.get('message', '') for msg in messages]
            combined_text = '\n'.join(message_texts[:50])  # 限制长度避免token超限
            
            # 生成风格分析报告
            style_analysis = await self._generate_style_analysis(combined_text)
            
            # 提取数值化特征
            style_profile = await self._extract_style_profile(combined_text)
            
            # 检测风格变化
            style_evolution = None
            if self.baseline_style:
                style_evolution = self._detect_style_evolution(self.baseline_style, style_profile)
            
            # 更新基准风格并持久化
            self.baseline_style = style_profile
            await self.db_manager.save_style_profile(group_id, {"profile_name": "baseline_style_profile", **self.baseline_style.__dict__})
            
            # 准备返回结果
            result = {
                'style_analysis': style_analysis,
                'style_profile': self.baseline_style.__dict__, # 返回更新后的基准风格
                'style_evolution': style_evolution.__dict__ if style_evolution else None,
                'message_count': len(messages),
                'analysis_timestamp': datetime.now().isoformat(),
                'confidence': await self._calculate_analysis_confidence(messages),
                'analyzed_messages': [{'message': msg.get('message', ''), 'sender': msg.get('sender_name', '')} for msg in messages[:10]]  # 保存前10条消息用于分析记录
            }
            
            # 将分析结果保存到数据库
            await self._save_style_analysis_to_db(group_id, result)
            
            return result
            
        except Exception as e:
            logger.error(f"对话风格分析失败: {e}")
            raise StyleAnalysisError(f"风格分析失败: {str(e)}")

    async def _generate_style_analysis(self, text: str) -> Dict[str, Any]:
        """生成详细的风格分析报告"""
        try:
            prompt = self.prompts.STYLE_ANALYZER_GENERATE_STYLE_ANALYSIS_PROMPT.format(
                text=text
            )
            
            # 使用框架适配器
            if self.llm_adapter and self.llm_adapter.has_refine_provider():
                response = await self.llm_adapter.refine_chat_completion(prompt=prompt)
            else:
                logger.warning("没有可用的LLM服务")
                return {"error": "LLM服务不可用"}
            
            # 处理响应
            response_text = response if isinstance(response, str) else (response.text() if response and hasattr(response, 'text') else None)
            if response_text:
                # 使用安全的JSON解析
                default_analysis = {
                    "error": "JSON解析失败",
                    "raw_response": "响应解析失败"
                }
                
                analysis = safe_parse_llm_json(response_text, fallback_result=default_analysis)
                
                if analysis and not analysis.get("error"):
                    return analysis
                else:
                    return {"error": "JSON解析失败", "raw_response": response_text}
            return {"error": "LLM响应为空"}
                
        except Exception as e:
            logger.error(f"风格分析生成失败: {e}")
            return {"error": str(e)}

    async def _save_style_analysis_to_db(self, group_id: str, analysis_result: Dict[str, Any]) -> bool:
        """将风格分析结果保存到数据库"""
        try:
            if not self.db_manager:
                return False
            
            # 保存到style_learning_records表
            record_data = {
                'style_type': 'comprehensive_analysis',
                'learned_patterns': json.dumps(analysis_result, ensure_ascii=False),
                'confidence_score': analysis_result.get('confidence', 0.8),
                'sample_count': len(analysis_result.get('analyzed_messages', [])),
                'group_id': group_id,
                'learning_time': time.time()
            }
            
            await self.db_manager.save_style_learning_record(record_data)
            
            # 如果有常用短语，保存到language_style_patterns表
            if 'style_analysis' in analysis_result:
                style_data = analysis_result['style_analysis']
                if 'common_phrases' in style_data and isinstance(style_data['common_phrases'], list):
                    pattern_data = {
                        'language_style': 'common_expressions',
                        'example_phrases': json.dumps(style_data['common_phrases'], ensure_ascii=False),
                        'usage_frequency': len(style_data['common_phrases']),
                        'context_type': f'group_{group_id}',
                        'group_id': group_id,
                        'last_updated': time.time()
                    }
                    await self.db_manager.save_language_style_pattern(pattern_data)
            
            logger.info(f"风格分析结果已保存到数据库，群组: {group_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存风格分析结果到数据库失败: {e}")
            return False

    async def _extract_style_profile(self, text: str) -> StyleProfile:
        """提取数值化的风格档案"""
        try:
            prompt = self.prompts.STYLE_ANALYZER_EXTRACT_STYLE_PROFILE_PROMPT.format(
                text=text
            )
            
            # 使用框架适配器
            if self.llm_adapter and self.llm_adapter.has_refine_provider():
                response = await self.llm_adapter.refine_chat_completion(prompt=prompt)
            else:
                logger.warning("没有可用的LLM服务")
                return StyleProfile()
            
            # 处理响应
            response_text = response if isinstance(response, str) else (response.text() if response and hasattr(response, 'text') else None)
            if response_text:
                # 使用安全的JSON解析
                default_scores = StyleProfile()
                
                scores_dict = safe_parse_llm_json(response_text, fallback_result=default_scores.__dict__)
                
                if scores_dict and isinstance(scores_dict, dict):
                    try:
                        return StyleProfile(**scores_dict)
                    except TypeError:
                        # 返回默认值
                        return StyleProfile()
                else:
                    return StyleProfile()
            return StyleProfile() # LLM响应为空，返回默认值
                
        except Exception as e:
            logger.warning(f"风格档案提取失败: {e}")
            return StyleProfile()

    def _detect_style_evolution(self, old_style: StyleProfile, new_style: StyleProfile) -> StyleEvolution:
        """检测风格演化"""
        evolution_vector = {
            'vocabulary_richness': new_style.vocabulary_richness - old_style.vocabulary_richness,
            'sentence_complexity': new_style.sentence_complexity - old_style.sentence_complexity,
            'emotional_expression': new_style.emotional_expression - old_style.emotional_expression,
            'interaction_tendency': new_style.interaction_tendency - old_style.interaction_tendency,
            'topic_diversity': new_style.topic_diversity - old_style.topic_diversity,
            'formality_level': new_style.formality_level - old_style.formality_level,
            'creativity_score': new_style.creativity_score - old_style.creativity_score
        }
        
        # 计算变化显著性
        significance = sum(abs(v) for v in evolution_vector.values()) / len(evolution_vector)
        
        evolution = StyleEvolution(
            timestamp=datetime.now().isoformat(),
            old_profile=old_style,
            new_profile=new_style,
            evolution_vector=evolution_vector,
            significance=significance
        )
        
        # 存储演化记录
        self.style_evolution_history.append(evolution)
        
        # 保持最近20条记录
        if len(self.style_evolution_history) > 20:
            self.style_evolution_history = self.style_evolution_history[-20:]
        
        return evolution

    async def _calculate_analysis_confidence(self, messages: List[Dict[str, Any]]) -> float:
        """计算分析置信度"""
        confidence = 0.5  # 基础置信度
        
        # 消息数量影响
        message_count = len(messages)
        if message_count >= 100:
            confidence += 0.3
        elif message_count >= 50:
            confidence += 0.2
        elif message_count >= 20:
            confidence += 0.1
        
        # 消息内容质量影响
        total_chars = sum(len(msg.get('message', '')) for msg in messages)
        avg_length = total_chars / max(message_count, 1)
        
        if avg_length >= 50:
            confidence += 0.2
        elif avg_length >= 20:
            confidence += 0.1
        
        return min(confidence, 1.0)

    async def get_style_trends(self) -> Dict[str, Any]:
        """获取风格趋势分析"""
        if not self.style_evolution_history:
            return {"error": "暂无风格演化数据"}
        
        # 分析最近的风格变化趋势
        recent_evolutions = self.style_evolution_history[-10:]
        
        trends = {}
        for dimension in ['vocabulary_richness', 'sentence_complexity', 'emotional_expression',
                         'interaction_tendency', 'topic_diversity', 'formality_level', 'creativity_score']:
            values = [evo.evolution_vector.get(dimension, 0) for evo in recent_evolutions]
            trends[dimension] = {
                'trend': 'increasing' if sum(values) > 0 else 'decreasing' if sum(values) < 0 else 'stable',
                'average_change': sum(values) / len(values),
                'volatility': sum(abs(v - sum(values)/len(values)) for v in values) / len(values)
            }
        
        return {
            'trends': trends,
            'overall_stability': 1.0 - (sum(evo.significance for evo in recent_evolutions) / len(recent_evolutions)),
            'evolution_count': len(self.style_evolution_history),
            'analysis_period': {
                'start': self.style_evolution_history[0].timestamp if self.style_evolution_history else None,
                'end': self.style_evolution_history[-1].timestamp if self.style_evolution_history else None
            }
        }

    async def generate_style_recommendations(self, target_persona: str) -> Dict[str, Any]:
        """生成风格优化建议"""
        if not self.baseline_style:
            return {"error": "暂无基准风格数据"}
        
        try:
            # 使用框架适配器
            if not self.llm_adapter or not self.llm_adapter.has_refine_provider():
                return {"error": "提炼模型适配器未配置，无法生成风格建议。"}
            
            current_style_data = self.baseline_style.__dict__
            
            prompt = self.prompts.STYLE_ANALYZER_GENERATE_STYLE_RECOMMENDATIONS_PROMPT.format(
                current_style_data=json.dumps(current_style_data, ensure_ascii=False, indent=2),
                target_persona=target_persona
            )
            
            # 使用框架适配器
            response = await self.llm_adapter.refine_chat_completion(prompt=prompt)
            
            # 处理响应
            response_text = response if isinstance(response, str) else (response.text() if response and hasattr(response, 'text') else None)
            if response_text:
                # 使用安全的JSON解析
                default_recommendations = {
                    "error": "建议解析失败",
                    "raw_response": "响应解析失败"
                }
                
                recommendations = safe_parse_llm_json(response_text, fallback_result=default_recommendations)
                
                if recommendations and not recommendations.get("error"):
                    return recommendations
                else:
                    return {"error": "建议解析失败", "raw_response": response_text}
            return {"error": "LLM响应为空"}
                
        except Exception as e:
            logger.error(f"风格建议生成失败: {e}")
            return {"error": str(e)}

    async def stop(self):
        """停止服务"""
        try:
            logger.info("风格分析服务已停止")
            return True
        except Exception as e:
            logger.error(f"停止风格分析服务失败: {e}")
            return False
