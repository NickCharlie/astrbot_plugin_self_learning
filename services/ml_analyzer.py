"""
轻量级机器学习分析器 - 使用简单的ML算法进行数据分析
"""
import numpy as np
import json
import time
import pandas as pd # 导入 pandas
import asyncio # 导入 asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import Counter, defaultdict

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import KMeans
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.linear_model import LogisticRegression # 导入 LogisticRegression
    from sklearn.tree import DecisionTreeClassifier # 导入 DecisionTreeClassifier
    SKLEARN_AVAILABLE = True
except ImportError: 
    SKLEARN_AVAILABLE = False

from astrbot.api import logger

from ..config import PluginConfig

from ..exceptions import StyleAnalysisError

from ..core.framework_llm_adapter import FrameworkLLMAdapter # 导入框架适配器

from .database_manager import DatabaseManager # 确保 DatabaseManager 被正确导入

from ..utils.json_utils import safe_parse_llm_json, clean_llm_json_response


class LightweightMLAnalyzer:
    """轻量级机器学习分析器 - 使用简单的ML算法进行数据分析"""
    
    def __init__(self, config: PluginConfig, db_manager: DatabaseManager, 
                 llm_adapter: Optional[FrameworkLLMAdapter] = None,
                 prompts: Any = None, temporary_persona_updater = None): # 使用框架适配器替代LLMClient
        self.config = config
        self.db_manager = db_manager
        self.llm_adapter = llm_adapter  # 使用框架适配器
        self.prompts = prompts # 保存 prompts
        self.temporary_persona_updater = temporary_persona_updater # 保存临时人格更新器引用
        
        # 设置分析限制以节省资源
        self.max_sample_size = 100  # 最大样本数量
        self.max_features = 50      # 最大特征数量
        self.analysis_cache = {}    # 分析结果缓存
        self.cache_timeout = 3600   # 缓存1小时
        
        if not SKLEARN_AVAILABLE:
            logger.warning("scikit-learn未安装，将使用基础统计分析")
            self.strategy_model = None
        else:
            # 初始化策略模型
            self.strategy_model: Optional[LogisticRegression | DecisionTreeClassifier] = None
            # 可以在这里选择使用 LogisticRegression 或 DecisionTreeClassifier
            # self.strategy_model = LogisticRegression(max_iter=1000) 
            # self.strategy_model = DecisionTreeClassifier(max_depth=5)
        
        logger.info("轻量级ML分析器初始化完成")

    async def reinforcement_memory_replay(self, group_id: str, new_messages: List[Dict[str, Any]], current_persona: Dict[str, Any]) -> Dict[str, Any]:
        """
        强化学习记忆重放：通过强化模型分析历史数据和新数据的关联性，优化学习策略
        """
        if not self.llm_adapter or not self.llm_adapter.has_reinforce_provider() and self.llm_adapter.providers_configured < 3:
            logger.warning("强化模型未配置，跳过强化学习记忆重放功能")
            return {}

        try:
            # 检查是否在学习流程中，避免在force_learning过程中重复调用
            import inspect
            current_frame = inspect.currentframe()
            call_stack = []
            frame = current_frame
            while frame:
                call_stack.append(frame.f_code.co_name)
                frame = frame.f_back
            
            learning_methods = ['_execute_learning_batch', 'force_learning_command']
            if any(method in call_stack for method in learning_methods):
                logger.debug(f"检测到正在强制学习流程中，适度降低强化学习记忆重放的调用频率")
                # 在学习流程中仍然执行，但减少复杂度
                pass

            # 获取历史学习数据
            historical_data = await self.db_manager.get_learning_history_for_reinforcement(group_id, limit=50)
            
            # 过滤掉None值，准备数据格式
            filtered_historical_data = [h for h in historical_data if h is not None]
            filtered_new_messages = [msg for msg in new_messages if msg is not None]
            
            historical_summary = {
                "successful_patterns": [h.get('successful_pattern', '') for h in filtered_historical_data if h.get('success')],
                "failed_patterns": [h.get('failed_pattern', '') for h in filtered_historical_data if not h.get('success')],
                "average_quality_score": sum([h.get('quality_score', 0) for h in filtered_historical_data]) / max(len(filtered_historical_data), 1),
                "learning_trends": self._analyze_learning_trends(filtered_historical_data)
            }
            
            new_data_summary = {
                "message_count": len(filtered_new_messages),
                "avg_message_length": sum([len(msg.get('message', '')) for msg in filtered_new_messages]) / max(len(filtered_new_messages), 1),
                "dominant_topics": self._extract_dominant_topics(filtered_new_messages),
                "emotional_distribution": await self._analyze_emotional_distribution(filtered_new_messages)
            }

            # 调用强化模型进行记忆重放分析
            response = await self.llm_adapter.reinforce_chat_completion(
                prompt=self.prompts.JSON_ONLY_SYSTEM_PROMPT + "\n\n" + self.prompts.REINFORCEMENT_LEARNING_MEMORY_REPLAY_PROMPT.format(
                    historical_learning_data=json.dumps(historical_summary, ensure_ascii=False, indent=2),
                    new_learning_data=json.dumps(new_data_summary, ensure_ascii=False, indent=2),
                    current_persona=json.dumps(current_persona, ensure_ascii=False, indent=2)
                ),
                temperature=0.7
            )

            if response:
                # response 是字符串，清理响应文本，移除markdown标识符
                clean_response = clean_llm_json_response(response)
                
                try:
                    reinforcement_result = safe_parse_llm_json(clean_response)
                    
                    # 保存强化学习结果到数据库
                    await self.db_manager.save_reinforcement_learning_result(group_id, {
                        'timestamp': time.time(),
                        'replay_analysis': reinforcement_result.get('replay_analysis', {}),
                        'optimization_strategy': reinforcement_result.get('optimization_strategy', {}),
                        'reinforcement_feedback': reinforcement_result.get('reinforcement_feedback', {}),
                        'next_action': reinforcement_result.get('next_action', '')
                    })
                    
                    logger.info(f"强化学习记忆重放完成，奖励分数: {reinforcement_result.get('reinforcement_feedback', {}).get('reward_score', 0)}")
                    return reinforcement_result
                    
                except json.JSONDecodeError:
                    logger.error(f"强化模型返回的JSON格式不正确: {clean_response}")
                    return {}
            return {}
            
        except Exception as e:
            logger.error(f"执行强化学习记忆重放失败: {e}")
            return {}

    async def reinforcement_incremental_tuning(self, group_id: str, base_persona: Dict[str, Any], 
                                               incremental_updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        强化学习增量微调：通过强化模型智能融合基础人格和增量更新
        """
        if (not self.llm_adapter or not self.llm_adapter.has_reinforce_provider()) and self.llm_adapter.providers_configured < 3:
            logger.warning("强化模型未配置，跳过增量微调功能")
            return {}

        try:
            # 获取融合历史数据
            fusion_history = await self.db_manager.get_persona_fusion_history(group_id, limit=10)
            
            # 保护原始prompt内容，避免被过度精简
            original_prompt = base_persona.get('prompt', '')
            original_prompt_length = len(original_prompt)
            
            # 如果原始prompt太短，直接跳过强化学习微调
            if original_prompt_length < 100:
                logger.info(f"原始prompt过短({original_prompt_length}字符)，跳过强化学习微调以避免过度精简")
                return {}
            
            # 调用强化模型进行增量微调分析
            response = await self.llm_adapter.reinforce_chat_completion(
                prompt=self.prompts.JSON_ONLY_SYSTEM_PROMPT + "\n\n" + self.prompts.REINFORCEMENT_LEARNING_INCREMENTAL_TUNING_PROMPT.format(
                    base_persona=json.dumps(base_persona, ensure_ascii=False, indent=2),
                    incremental_updates=json.dumps(incremental_updates, ensure_ascii=False, indent=2),
                    fusion_history=json.dumps(fusion_history, ensure_ascii=False, indent=2)
                ),
                temperature=0.6
            )

            if response:
                # response 是字符串，清理响应文本，移除markdown标识符
                clean_response = clean_llm_json_response(response)
                
                try:
                    tuning_result = safe_parse_llm_json(clean_response, fallback_result={})
                    
                    # 确保tuning_result不为None且是字典类型
                    if not tuning_result or not isinstance(tuning_result, dict):
                        logger.warning("强化学习增量微调: 解析结果为空或格式不正确，使用默认结果")
                        tuning_result = {}
                    
                    # 重要保护：防止prompt被过度精简
                    if 'updated_persona' in tuning_result and 'prompt' in tuning_result['updated_persona']:
                        new_prompt = tuning_result['updated_persona']['prompt']
                        new_prompt_length = len(new_prompt)
                        
                        # 如果新prompt比原prompt短太多，则进行保护性处理
                        if new_prompt_length < original_prompt_length * 0.8:
                            logger.warning(f"强化学习生成的prompt过短({new_prompt_length} vs {original_prompt_length})，采用保守融合策略")
                            
                            # 采用保守的增量融合，而不是完全替换
                            enhanced_prompt = self._conservative_prompt_fusion(original_prompt, new_prompt, tuning_result)
                            tuning_result['updated_persona']['prompt'] = enhanced_prompt
                            
                            # 降低期望改进值，因为我们采用了保守策略
                            if 'performance_prediction' in tuning_result:
                                original_improvement = tuning_result['performance_prediction'].get('expected_improvement', 0)
                                tuning_result['performance_prediction']['expected_improvement'] = min(original_improvement * 0.7, 0.6)
                        
                        logger.info(f"强化学习prompt长度变化: {original_prompt_length} -> {len(tuning_result['updated_persona']['prompt'])}")
                    
                    # 保存融合结果到历史记录
                    await self.db_manager.save_persona_fusion_result(group_id, {
                        'timestamp': time.time(),
                        'base_persona_hash': hash(str(base_persona)),
                        'incremental_hash': hash(str(incremental_updates)),
                        'fusion_result': tuning_result,
                        'compatibility_score': tuning_result.get('compatibility_analysis', {}).get('feature_compatibility', 0)
                    })
                    
                    logger.info(f"强化学习增量微调完成，预期改进: {tuning_result.get('performance_prediction', {}).get('expected_improvement', 0)}")
                    return tuning_result
                    
                except json.JSONDecodeError:
                    logger.error(f"强化模型返回的JSON格式不正确: {clean_response}")
                    return {}
            return {}
            
        except Exception as e:
            logger.error(f"执行强化学习增量微调失败: {e}")
            return {}

    async def reinforcement_strategy_optimization(self, group_id: str) -> Dict[str, Any]:
        """
        强化学习策略优化：基于历史表现数据动态调整学习策略
        """
        if (not self.llm_adapter or not self.llm_adapter.has_reinforce_provider())  and self.llm_adapter.providers_configured < 3:
            logger.warning("强化模型未配置，跳过策略优化功能")
            return {}

        try:
            # 获取学习历史数据和性能指标
            learning_history = await self.db_manager.get_learning_performance_history(group_id, limit=30)
            current_strategy = {
                "learning_rate": self.config.learning_interval_hours / 24.0,
                "batch_size": self.config.max_messages_per_batch,
                "confidence_threshold": self.config.confidence_threshold,
                "quality_threshold": self.config.style_update_threshold
            }
            
            performance_metrics = self._calculate_performance_metrics(learning_history)
            
            # 调用强化模型进行策略优化
            response = await self.llm_adapter.reinforce_chat_completion(
                prompt=self.prompts.JSON_ONLY_SYSTEM_PROMPT + "\n\n" + self.prompts.REINFORCEMENT_LEARNING_STRATEGY_OPTIMIZATION_PROMPT.format(
                    learning_history=json.dumps(learning_history, ensure_ascii=False, indent=2),
                    current_strategy=json.dumps(current_strategy, ensure_ascii=False, indent=2),
                    performance_metrics=json.dumps(performance_metrics, ensure_ascii=False, indent=2)
                ),
                temperature=0.5
            )

            if response:
                # response 是字符串，清理响应文本，移除markdown标识符
                clean_response = clean_llm_json_response(response)
                
                try:
                    optimization_result = safe_parse_llm_json(clean_response)
                    
                    # 保存策略优化结果
                    await self.db_manager.save_strategy_optimization_result(group_id, {
                        'timestamp': time.time(),
                        'original_strategy': current_strategy,
                        'optimization_result': optimization_result,
                        'expected_improvement': optimization_result.get('expected_improvements', {})
                    })
                    
                    logger.info(f"强化学习策略优化完成，预期学习速度提升: {optimization_result.get('expected_improvements', {}).get('learning_speed', 0)}")
                    return optimization_result
                    
                except json.JSONDecodeError:
                    logger.error(f"强化模型返回的JSON格式不正确: {clean_response}")
                    return {}
            return {}
        except Exception as e:
            logger.error(f"策略优化执行失败: {e}")
            return {}

    def _conservative_prompt_fusion(self, original_prompt: str, new_prompt: str, tuning_result: Dict[str, Any]) -> str:
        """
        保守的prompt融合策略，避免过度精简原始prompt
        """
        try:
            # 如果新prompt明显太短，只提取其中的增量信息
            if len(new_prompt) < len(original_prompt) * 0.5:
                # 尝试从tuning_result中提取关键变化信息
                key_changes = tuning_result.get('updated_persona', {}).get('key_changes', [])
                
                if key_changes:
                    # 将关键变化以增量方式添加到原始prompt末尾
                    enhancement_text = f"\n\n## 学习增强特征:\n" + "\n".join([f"- {change}" for change in key_changes[:3]])
                    return original_prompt + enhancement_text
                else:
                    # 如果没有关键变化，返回原始prompt
                    logger.info("未发现明显的关键变化，保持原始prompt不变")
                    return original_prompt
            
            # 如果新prompt长度合理，但仍然比原来短，进行智能融合
            elif len(new_prompt) < len(original_prompt) * 0.8:
                # 尝试保留原始prompt的主要结构，添加新的特征
                lines = original_prompt.split('\n')
                new_lines = new_prompt.split('\n')
                
                # 找到可能的增量内容（出现在新prompt但不在原prompt中的内容）
                new_content = []
                for line in new_lines:
                    if line.strip() and line.strip() not in original_prompt:
                        new_content.append(line.strip())
                
                if new_content:
                    # 将新内容作为增量添加
                    enhancement = f"\n\n## 最新学习特征:\n" + "\n".join([f"- {content}" for content in new_content[:5]])
                    return original_prompt + enhancement
                else:
                    return original_prompt
            
            else:
                # 长度差异不大，使用新prompt
                return new_prompt
                
        except Exception as e:
            logger.error(f"保守融合失败: {e}")
            return original_prompt

    async def replay_memory(self, group_id: str, new_messages: List[Dict[str, Any]], current_persona: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        记忆重放：将历史数据与新数据混合，并交给提炼模型进行处理。
        这模拟了LLM的"增量微调"过程，通过重新暴露历史数据来巩固学习。
        """
        if (not self.llm_adapter or not self.llm_adapter.has_refine_provider())  and self.llm_adapter.providers_configured < 2:
            logger.warning("提炼模型未配置，跳过记忆重放功能")
            return []

        try:
            # 获取最近一段时间的历史消息
            # 假设我们获取过去30天的消息作为历史数据
            history_messages = await self.db_manager.get_messages_for_replay(group_id, days=30, limit=self.config.max_messages_per_batch * 2)
            
            # 将新消息与历史消息混合
            # 可以根据时间戳进行排序，或者简单地拼接
            # 过滤掉None值
            filtered_history_messages = [msg for msg in history_messages if msg is not None]
            filtered_new_messages = [msg for msg in new_messages if msg is not None]
            
            all_messages = filtered_history_messages + filtered_new_messages
            # 确保消息不重复，并按时间排序
            unique_messages = {msg.get('message_id', id(msg)): msg for msg in all_messages if msg.get('message_id') or id(msg)}
            sorted_messages = sorted(unique_messages.values(), key=lambda x: x.get('timestamp', 0))
            
            # 限制总消息数量，避免过大的上下文
            if len(sorted_messages) > self.config.max_messages_per_batch * 2:
                sorted_messages = sorted_messages[-self.config.max_messages_per_batch * 2:]

            logger.info(f"执行记忆重放，混合消息数量: {len(sorted_messages)}")

            # 将混合后的消息交给提炼模型进行处理
            # 这里可以设计一个更复杂的prompt，让LLM从这些消息中提炼新的知识或风格
            # 示例：让LLM总结这些消息的特点，并与当前人格进行对比
            messages_text = "\n".join([msg.get('message', '') for msg in sorted_messages if msg.get('message')])
            
            prompt = f"""{self.prompts.JSON_ONLY_SYSTEM_PROMPT}

{self.prompts.ML_ANALYZER_REPLAY_MEMORY_SYSTEM_PROMPT.format(
                current_persona_description=current_persona['description']
            )}

{self.prompts.ML_ANALYZER_REPLAY_MEMORY_PROMPT.format(
                messages_text=messages_text
            )}"""

            response = await self.llm_adapter.refine_chat_completion(
                prompt=prompt,
                temperature=0.3
            )

            if response:
                # response 是字符串，清理响应文本，移除markdown标识符
                clean_response = clean_llm_json_response(response)
                
                try:
                    refined_data = safe_parse_llm_json(clean_response)
                    logger.info(f"记忆重放提炼结果: {refined_data}")
                    
                    # 将强化学习结果集成到system_prompt
                    if self.temporary_persona_updater:
                        try:
                            # 检查是否在强制学习过程中，避免无限循环
                            # 通过检查调用栈来判断是否已经在学习流程中
                            import inspect
                            current_frame = inspect.currentframe()
                            call_stack = []
                            frame = current_frame
                            while frame:
                                call_stack.append(frame.f_code.co_name)
                                frame = frame.f_back
                            
                            # 如果调用栈中包含学习相关的方法，说明正在学习流程中，跳过system_prompt更新
                            learning_methods = ['_execute_learning_batch', 'force_learning_command', '_apply_learning_updates']
                            if any(method in call_stack for method in learning_methods):
                                logger.debug(f"检测到正在学习流程中，跳过记忆重放的system_prompt集成以避免循环")
                            else:
                                # 准备学习洞察更新数据
                                insights_data = {
                                    'learning_insights': {
                                        'interaction_patterns': refined_data.get('interaction_patterns', '通过记忆重放发现的交互模式'),
                                        'improvement_suggestions': refined_data.get('suggested_improvements', '基于历史消息的改进建议'),
                                        'effective_strategies': refined_data.get('effective_responses', '有效的回复策略'),
                                        'learning_focus': f"记忆重放学习 - 处理了{len(new_messages)}条历史消息"
                                    }
                                }
                                
                                await self.temporary_persona_updater.apply_comprehensive_update_to_system_prompt(
                                    group_id, insights_data
                                )
                                logger.info(f"成功将强化学习结果集成到system_prompt: {group_id}")
                            
                        except Exception as e:
                            logger.error(f"集成强化学习结果到system_prompt失败: {e}")
                    
                    
                    # 这里可以将 refined_data 传递给 PersonaUpdater 进行人格更新
                    # 或者在 ProgressiveLearning 模块中处理
                    return refined_data
                except json.JSONDecodeError:
                    logger.error(f"提炼模型返回的JSON格式不正确: {clean_response}")
                    return {}
            return {}
        except Exception as e:
            logger.error(f"执行记忆重放失败: {e}")
            return {}

    def _analyze_learning_trends(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析学习趋势"""
        # 过滤掉None值
        filtered_data = [h for h in historical_data if h is not None]
        
        if not filtered_data:
            return {}
        
        quality_scores = [h.get('quality_score', 0) for h in filtered_data]
        success_rate = sum([1 for h in filtered_data if h.get('success', False)]) / len(filtered_data)
        
        # 计算趋势
        if len(quality_scores) >= 3:
            recent_avg = sum(quality_scores[-3:]) / 3
            early_avg = sum(quality_scores[:3]) / 3
            trend = (recent_avg - early_avg) / max(early_avg, 0.1)
        else:
            trend = 0.0
        
        return {
            "average_quality": sum(quality_scores) / len(quality_scores),
            "success_rate": success_rate,
            "quality_trend": trend,
            "total_sessions": len(filtered_data)
        }

    def _extract_dominant_topics(self, messages: List[Dict[str, Any]]) -> List[str]:
        """提取主要话题"""
        # 过滤掉None值
        filtered_messages = [msg for msg in messages if msg is not None]
        
        if not SKLEARN_AVAILABLE or len(filtered_messages) < 5:
            return []
        
        try:
            texts = [msg.get('message', '') for msg in filtered_messages if len(msg.get('message', '')) > 10]
            if len(texts) < 3:
                return []
            
            # 使用TF-IDF提取关键词
            vectorizer = TfidfVectorizer(max_features=10, ngram_range=(1, 2))
            tfidf_matrix = vectorizer.fit_transform(texts)
            feature_names = vectorizer.get_feature_names_out()
            
            # 获取平均TF-IDF分数
            mean_scores = tfidf_matrix.mean(axis=0).A1
            top_indices = mean_scores.argsort()[-5:][::-1]
            
            return [feature_names[i] for i in top_indices]
            
        except Exception as e:
            logger.error(f"提取主要话题失败: {e}")
            return []

    async def _analyze_emotional_distribution(self, messages: List[Dict[str, Any]]) -> Dict[str, float]:
        """分析情感分布"""
        try:
            # 过滤掉None值
            filtered_messages = [msg for msg in messages if msg is not None]
            # 使用现有的情感分析方法
            return await self._analyze_sentiment_with_llm(filtered_messages)
        except Exception as e:
            logger.error(f"分析情感分布失败: {e}")
            # 过滤掉None值再传给简单情感分析
            filtered_messages = [msg for msg in messages if msg is not None]
            return self._simple_sentiment_analysis(filtered_messages)

    def _calculate_performance_metrics(self, learning_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算性能指标"""
        # 过滤掉None值
        filtered_history = [h for h in learning_history if h is not None]
        
        if not filtered_history:
            return {}
        
        quality_scores = [h.get('quality_score', 0) for h in filtered_history]
        learning_times = [h.get('learning_time', 0) for h in filtered_history]
        success_count = sum([1 for h in filtered_history if h.get('success', False)])
        
        return {
            "average_quality": sum(quality_scores) / len(quality_scores),
            "quality_variance": np.var(quality_scores),
            "success_rate": success_count / len(filtered_history),
            "average_learning_time": sum(learning_times) / max(len(learning_times), 1),
            "total_sessions": len(filtered_history),
            "improvement_rate": self._calculate_improvement_rate(quality_scores)
        }

    def _calculate_improvement_rate(self, quality_scores: List[float]) -> float:
        """计算改进率"""
        if len(quality_scores) < 4:
            return 0.0
        
        # 比较前半部分和后半部分的平均分
        mid = len(quality_scores) // 2
        first_half_avg = sum(quality_scores[:mid]) / mid
        second_half_avg = sum(quality_scores[mid:]) / (len(quality_scores) - mid)
        
        if first_half_avg == 0:
            return 0.0
        
        return (second_half_avg - first_half_avg) / first_half_avg

    async def train_strategy_model(self, X: np.ndarray, y: np.ndarray, model_type: str = "logistic_regression"):
        """
        训练策略模型（逻辑回归或决策树）。
        X: 特征矩阵 (e.g., 消息长度, 情感分数, 相关性分数)
        y: 目标变量 (e.g., 消息是否被采纳/学习价值高低)
        """
        if not SKLEARN_AVAILABLE:
            logger.warning("scikit-learn未安装，无法训练策略模型。")
            return

        if model_type == "logistic_regression":
            self.strategy_model = LogisticRegression(max_iter=1000, random_state=42)
        elif model_type == "decision_tree":
            self.strategy_model = DecisionTreeClassifier(max_depth=5, random_state=42)
        else:
            logger.error(f"不支持的模型类型: {model_type}")
            self.strategy_model = None
            return

        try:
            # 将阻塞的fit操作放到单独的线程中执行
            await asyncio.to_thread(self.strategy_model.fit, X, y)
            logger.info(f"策略模型 ({model_type}) 训练完成。")
        except Exception as e:
            logger.error(f"训练策略模型失败: {e}")
            self.strategy_model = None

    def predict_learning_value(self, features: np.ndarray) -> float:
        """
        使用训练好的策略模型预测消息的学习价值。
        features: 单个消息的特征向量。
        返回预测的学习价值（0-1之间）。
        """
        if not self.strategy_model:
            logger.warning("策略模型未训练，返回默认学习价值0.5。")
            return 0.5
        
        try:
            # 确保特征维度匹配训练时的维度
            if features.ndim == 1:
                features = features.reshape(1, -1)

            if hasattr(self.strategy_model, 'predict_proba'):
                # 对于分类模型，通常预测为正类的概率
                proba = self.strategy_model.predict_proba(features)
                # 假设正类是索引1
                return float(proba[0][1])
            elif hasattr(self.strategy_model, 'predict'):
                # 对于回归模型，直接预测值
                return float(self.strategy_model.predict(features)[0])
            else:
                logger.warning("策略模型不支持预测概率或直接预测，返回默认学习价值0.5。")
                return 0.5
        except Exception as e:
            logger.error(f"预测学习价值失败: {e}")
            return 0.5

    async def analyze_user_behavior_pattern(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """分析用户行为模式"""
        try:
            # 检查缓存
            cache_key = f"behavior_{group_id}_{user_id}"
            if self._check_cache(cache_key):
                return self.analysis_cache[cache_key]['data']
            
            # 获取用户最近消息（限制数量）
            messages = await self._get_user_messages(group_id, user_id, limit=self.max_sample_size)
            
            if not messages:
                return {}
            
            # 基础统计分析
            pattern = {
                'message_count': len(messages),
                'avg_message_length': np.mean([len(msg['message']) for msg in messages]),
                'activity_hours': self._analyze_activity_hours(messages),
                'message_frequency': self._analyze_message_frequency(messages),
                'interaction_patterns': await self._analyze_interaction_patterns(group_id, user_id, messages)
            }
            
            # 如果有sklearn，进行文本聚类
            if SKLEARN_AVAILABLE and len(messages) >= 5:
                pattern['topic_clusters'] = self._analyze_topic_clusters(messages)
            
            # 缓存结果
            self._cache_result(cache_key, pattern)
            
            return pattern
            
        except Exception as e:
            logger.error(f"分析用户行为模式失败: {e}")
            raise StyleAnalysisError(f"分析用户行为模式失败: {str(e)}")

    async def _get_user_messages(self, group_id: str, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """获取用户消息（限制数量）"""
        try:
            # 从全局消息数据库获取连接
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                await cursor.execute('''
                    SELECT message, timestamp, sender_name, sender_id, group_id
                    FROM raw_messages 
                    WHERE sender_id = ? AND group_id = ? AND timestamp > ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (user_id, group_id, time.time() - 86400 * 7, limit))  # 最近7天
                
                messages = []
                for row in await cursor.fetchall():
                    messages.append({
                        'message': row[0],
                        'timestamp': row[1],
                        'sender_name': row[2],
                        'sender_id': row[3],
                        'group_id': row[4]
                    })
                
                return messages
            
        except Exception as e:
            logger.error(f"获取用户消息失败: {e}")
            return []

    def _analyze_activity_hours(self, messages: List[Dict[str, Any]]) -> Dict[str, float]:
        """分析活动时间模式"""
        if not messages:
            return {}
        
        hour_counts = defaultdict(int)
        for msg in messages:
            hour = datetime.fromtimestamp(msg['timestamp']).hour
            hour_counts[hour] += 1
        
        total_messages = len(messages)
        hour_distribution = {
            str(hour): count / total_messages 
            for hour, count in hour_counts.items()
        }
        
        # 确定最活跃时段
        most_active_hour = max(hour_counts.items(), key=lambda x: x)[1]
        
        return {
            'distribution': hour_distribution,
            'most_active_hour': most_active_hour,
            'activity_variance': np.var(list(hour_counts.values()))
        }

    def _analyze_message_frequency(self, messages: List[Dict[str, Any]]) -> Dict[str, float]:
        """分析消息频率模式"""
        if len(messages) < 2:
            return {}
        
        # 计算消息间隔
        intervals = []
        sorted_messages = sorted(messages, key=lambda x: x['timestamp'])
        
        for i in range(1, len(sorted_messages)):
            interval = sorted_messages[i]['timestamp'] - sorted_messages[i-1]['timestamp']
            intervals.append(interval / 60)  # 转换为分钟
        
        if not intervals:
            return {}
        
        return {
            'avg_interval_minutes': np.mean(intervals),
            'interval_std': np.std(intervals),
            'burst_tendency': len([x for x in intervals if x < 5]) / len(intervals)  # 5分钟内连续消息比例
        }

    async def _analyze_interaction_patterns(self, group_id: str, user_id: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析互动模式"""
        try:
            # 分析@消息和回复
            mention_count = len([msg for msg in messages if '@' in msg['message']])
            question_count = len([msg for msg in messages if '?' in msg['message'] or '？' in msg['message']])
            
            # 获取社交关系强度
            social_relations = await self.db_manager.load_social_graph(group_id)
            user_relations = [rel for rel in social_relations if rel['from_user'] == user_id or rel['to_user'] == user_id]
            
            return {
                'mention_ratio': mention_count / max(len(messages), 1),
                'question_ratio': question_count / max(len(messages), 1),
                'social_connections': len(user_relations),
                'avg_relation_strength': np.mean([rel['strength'] for rel in user_relations]) if user_relations else 0.0
            }
            
        except Exception as e:
            logger.error(f"分析互动模式失败: {e}")
            return {}

    def _analyze_topic_clusters(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """使用TF-IDF和K-means进行话题聚类"""
        if not SKLEARN_AVAILABLE or len(messages) < 3:
            return {}
        
        try:
            # 提取消息文本
            texts = [msg['message'] for msg in messages if len(msg['message']) > 5]
            
            if len(texts) < 3:
                return {}
            
            # TF-IDF向量化（限制特征数量）
            vectorizer = TfidfVectorizer(
                max_features=min(self.max_features, len(texts) * 2),
                stop_words=None,  # 不使用停用词以节省内存
                ngram_range=(1, 1)  # 只使用单词
            )
            
            tfidf_matrix = vectorizer.fit_transform(texts)
            
            # K-means聚类（限制簇数量）
            n_clusters = min(3, len(texts) // 2)
            if n_clusters < 2:
                return {}
            
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            cluster_labels = kmeans.fit_predict(tfidf_matrix)
            
            # 分析聚类结果
            clusters = defaultdict(list)
            for i, label in enumerate(cluster_labels):
                clusters[int(label)].append(texts[i][:50])  # 限制文本长度
            
            # 提取关键词
            feature_names = vectorizer.get_feature_names_out()
            cluster_keywords = {}
            
            for i in range(n_clusters):
                center = kmeans.cluster_centers_[i]
                top_indices = center.argsort()[-5:][::-1]  # 前5个关键词
                cluster_keywords[i] = [feature_names[idx] for idx in top_indices]
            
            return {
                'n_clusters': n_clusters,
                'cluster_keywords': cluster_keywords,
                'cluster_sizes': {str(k): len(v) for k, v in clusters.items()}
            }
            
        except Exception as e:
            logger.error(f"话题聚类分析失败: {e}")
            return {}

    async def analyze_group_sentiment_trend(self, group_id: str) -> Dict[str, Any]:
        """分析群聊情感趋势"""
        try:
            cache_key = f"sentiment_{group_id}"
            if self._check_cache(cache_key):
                return self.analysis_cache[cache_key]['data']
            
            # 获取最近消息（限制数量）
            recent_messages = await self._get_recent_group_messages(group_id, limit=self.max_sample_size)
            
            if not recent_messages:
                return {}
            
            # 简单情感分析（基于关键词）
            sentiment_trend = self._analyze_sentiment_keywords(recent_messages)
            
            # 活跃度分析
            activity_trend = self._analyze_activity_trend(recent_messages)
            
            result = {
                'sentiment_trend': sentiment_trend,
                'activity_trend': activity_trend,
                'analysis_time': datetime.now().isoformat(),
                'sample_size': len(recent_messages)
            }
            
            self._cache_result(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"分析群聊情感趋势失败: {e}")
            return {}

    async def _get_recent_group_messages(self, group_id: str, limit: int) -> List[Dict[str, Any]]:
        """获取群聊最近消息"""
        try:
            # 从全局消息数据库获取连接
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                await cursor.execute('''
                    SELECT message, timestamp, sender_id, group_id
                    FROM raw_messages 
                    WHERE group_id = ? AND timestamp > ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (group_id, time.time() - 3600 * 6, limit))  # 最近6小时
                
                messages = []
                for row in await cursor.fetchall():
                    messages.append({
                        'message': row[0],
                        'timestamp': row[1],
                        'sender_id': row[2],
                        'group_id': row[3]
                    })
                
                return messages
            
        except Exception as e:
            logger.error(f"获取群聊最近消息失败: {e}")
            return []

    async def _analyze_sentiment_with_llm(self, messages: List[Dict[str, Any]]) -> Dict[str, float]:
        """使用LLM对消息列表进行情感分析"""
        # 确保消息列表已经过滤掉None值
        filtered_messages = [msg for msg in messages if msg is not None]
        
        if (not self.llm_adapter or not self.llm_adapter.has_refine_provider()) and self.llm_adapter.providers_configured < 2:
            logger.warning("提炼模型未配置，无法进行LLM情感分析，使用简化算法")
            return self._simple_sentiment_analysis(filtered_messages)

        messages_text = "\n".join([msg.get('message', '') for msg in filtered_messages])
        
        prompt = self.prompts.JSON_ONLY_SYSTEM_PROMPT + "\n\n" + self.prompts.ML_ANALYZER_SENTIMENT_ANALYSIS_PROMPT.format(
            messages_text=messages_text
        )
        try:
            response = await self.llm_adapter.refine_chat_completion(
                prompt=prompt,
                temperature=0.3
            )
            
            if response:
                try:
                    sentiment_scores = safe_parse_llm_json(response)
                    # 确保所有分数都在0-1之间
                    for key, value in sentiment_scores.items():
                        sentiment_scores[key] = max(0.0, min(float(value), 1.0))
                    return sentiment_scores
                except json.JSONDecodeError:
                    logger.warning(f"LLM响应JSON解析失败，返回简化情感分析。响应内容: {response}")
                    return self._simple_sentiment_analysis(filtered_messages)
            return self._simple_sentiment_analysis(filtered_messages)
        except Exception as e:
            logger.warning(f"LLM情感分析失败，使用简化算法: {e}")
            return self._simple_sentiment_analysis(filtered_messages)

    def _simple_sentiment_analysis(self, messages: List[Dict[str, Any]]) -> Dict[str, float]:
        """基于关键词的简单情感分析（备用）"""
        # 确保消息列表已经过滤掉None值
        filtered_messages = [msg for msg in messages if msg is not None]
        
        positive_keywords = ['哈哈', '好的', '谢谢', '赞', '棒', '开心', '高兴', '😊', '👍', '❤️']
        negative_keywords = ['不行', '差', '烦', '无聊', '生气', '😢', '😡', '💔']
        
        positive_count = 0
        negative_count = 0
        total_messages = len(filtered_messages)
        
        for msg in filtered_messages:
            text = msg.get('message', '').lower()
            for keyword in positive_keywords:
                if keyword in text:
                    positive_count += 1
                    break
            for keyword in negative_keywords:
                if keyword in text:
                    negative_count += 1
                    break
        
        return {
            'positive_ratio': positive_count / max(total_messages, 1),
            'negative_ratio': negative_count / max(total_messages, 1),
            'neutral_ratio': (total_messages - positive_count - negative_count) / max(total_messages, 1)
        }

    def _analyze_activity_trend(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析活跃度趋势"""
        if not messages:
            return {}
        
        # 按小时分组统计
        hourly_counts = defaultdict(int)
        for msg in messages:
            hour = datetime.fromtimestamp(msg['timestamp']).hour
            hourly_counts[hour] += 1
        
        # 计算趋势
        hours = sorted(hourly_counts.keys())
        counts = [hourly_counts[hour] for hour in hours]
        
        if len(counts) >= 3:
            # 简单线性趋势计算
            x = np.array(range(len(counts)))
            y = np.array(counts)
            trend_slope = np.polyfit(x, y, 1)[0] # 取第一个元素
        else:
            trend_slope = 0.0 # 确保为浮点数
        
        peak_hour = None
        if hourly_counts:
            peak_hour = max(hourly_counts.items(), key=lambda x: x[1])[0] # 获取小时而不是计数
        
        return {
            'hourly_activity': dict(hourly_counts),
            'trend_slope': float(trend_slope),
            'peak_hour': peak_hour,
            'total_activity': sum(counts)
        }

    def _check_cache(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self.analysis_cache:
            return False
        
        cache_time = self.analysis_cache[cache_key]['timestamp']
        return time.time() - cache_time < self.cache_timeout

    def _cache_result(self, cache_key: str, data: Dict[str, Any]):
        """缓存分析结果"""
        self.analysis_cache[cache_key] = {
            'data': data,
            'timestamp': time.time()
        }
        
        # 清理过期缓存
        current_time = time.time()
        expired_keys = [
            key for key, value in self.analysis_cache.items()
            if current_time - value['timestamp'] > self.cache_timeout
        ]
        
        for key in expired_keys:
            del self.analysis_cache[key]

    async def get_analysis_summary(self, group_id: str) -> Dict[str, Any]:
        """获取分析摘要"""
        try:
            # 获取群统计
            group_stats = await self.db_manager.get_group_statistics(group_id)
            
            # 获取情感趋势
            sentiment_trend = await self.analyze_group_sentiment_trend(group_id)
            
            # 获取最活跃用户
            active_users = await self._get_most_active_users(group_id, limit=5)
            
            return {
                'group_statistics': group_stats,
                'sentiment_analysis': sentiment_trend,
                'active_users': active_users,
                'analysis_capabilities': {
                    'sklearn_available': SKLEARN_AVAILABLE,
                    'max_sample_size': self.max_sample_size,
                    'cache_status': len(self.analysis_cache)
                }
            }
            
        except Exception as e:
            logger.error(f"获取分析摘要失败: {e}")
            return {}

    async def _get_most_active_users(self, group_id: str, limit: int) -> List[Dict[str, Any]]:
        """获取最活跃用户"""
        try:
            # 从全局消息数据库获取连接
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                await cursor.execute('''
                    SELECT sender_id, sender_name, COUNT(*) as message_count
                    FROM raw_messages 
                    WHERE group_id = ? AND timestamp > ?
                    GROUP BY sender_id, sender_name
                    ORDER BY message_count DESC
                    LIMIT ?
                ''', (group_id, time.time() - 86400, limit))  # 最近24小时
                
                users = []
                for row in await cursor.fetchall():
                    users.append({
                        'user_id': row[0],
                        'user_name': row[1],
                        'message_count': row[2]
                    })
                
                return users
            
        except Exception as e:
            logger.error(f"获取最活跃用户失败: {e}")
            return []
