"""
学习质量监控服务 - 监控学习效果，防止人格崩坏
"""
import json
import time
import re # 移动到文件顶部
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context

from ...core.framework_llm_adapter import FrameworkLLMAdapter # 导入框架适配器

from ...config import PluginConfig

from ...exceptions import StyleAnalysisError

from ...utils.json_utils import safe_parse_llm_json


@dataclass
class PersonaMetrics:
    """人格指标"""
    consistency_score: float = 0.0 # 一致性得分
    style_stability: float = 0.0 # 风格稳定性
    vocabulary_diversity: float = 0.0 # 词汇多样性
    emotional_balance: float = 0.0 # 情感平衡性
    coherence_score: float = 0.0 # 逻辑连贯性


@dataclass
class LearningAlert:
    """学习警报"""
    alert_type: str
    severity: str # low, medium, high, critical
    message: str
    timestamp: str
    metrics: Dict[str, float]
    suggestions: List[str]


class LearningQualityMonitor:
    """学习质量监控器"""
    
    def __init__(self, config: PluginConfig, context: Context, 
                 llm_adapter: Optional[FrameworkLLMAdapter] = None,
                 prompts: Any = None):
        self.config = config
        self.context = context
        self.prompts = prompts
        
        # 使用框架适配器
        self.llm_adapter = llm_adapter
        
        # 监控阈值 - 调整为更合理的值
        self.consistency_threshold = 0.5 # 一致性阈值 (从0.7降低到0.5)
        self.stability_threshold = 0.4 # 稳定性阈值 (从0.6降低到0.4)
        self.drift_threshold = 0.4 # 风格偏移阈值 (从0.3提高到0.4)
        
        # 历史指标存储
        self.historical_metrics: List[PersonaMetrics] = []
        self.alerts_history: List[LearningAlert] = []
        
        logger.info("学习质量监控服务初始化完成")

    async def evaluate_learning_batch(self, 
                                    original_persona: Dict[str, Any],
                                    updated_persona: Dict[str, Any],
                                    learning_messages: List[Dict[str, Any]]) -> PersonaMetrics:
        """评估学习批次质量"""
        try:
            # 计算各项指标
            consistency_score = await self._calculate_consistency(
                original_persona, updated_persona
            )
            
            style_stability = await self._calculate_style_stability(
                learning_messages
            )
            
            vocabulary_diversity = await self._calculate_vocabulary_diversity(
                learning_messages
            )
            
            emotional_balance = await self._calculate_emotional_balance(
                learning_messages
            )
            
            coherence_score = await self._calculate_coherence(
                updated_persona
            )
            
            metrics = PersonaMetrics(
                consistency_score=consistency_score,
                style_stability=style_stability,
                vocabulary_diversity=vocabulary_diversity,
                emotional_balance=emotional_balance,
                coherence_score=coherence_score
            )
            
            # 存储历史指标
            self.historical_metrics.append(metrics)
            
            # 调整阈值
            await self.adjust_thresholds_based_on_history()
            
            # 检查是否需要发出警报
            await self._check_quality_alerts(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"学习质量评估失败: {e}")
            raise StyleAnalysisError(f"学习质量评估失败: {str(e)}")

    async def _calculate_consistency(self, 
                                   original_persona: Dict[str, Any],
                                   updated_persona: Dict[str, Any]) -> float:
        """计算人格一致性得分 - 使用强LLM进行专业评估"""
        try:
            original_prompt = original_persona.get('prompt', '')
            updated_prompt = updated_persona.get('prompt', '')
            
            # 增强的空值检查和默认值处理
            if not original_prompt and not updated_prompt:
                logger.debug("原始和更新人格都为空，返回中等一致性")
                return 0.7 # 提高默认值，因为两者都空可以认为是一致的
            elif not original_prompt or not updated_prompt:
                logger.debug("其中一个人格为空，返回较低一致性")
                return 0.6 # 提高默认值，避免因数据问题导致的低分
            
            # 如果两个prompt完全相同，直接返回高一致性
            if original_prompt.strip() == updated_prompt.strip():
                logger.debug("人格完全相同，返回高一致性")
                return 0.95
            
            # 优先使用框架适配器
            if self.llm_adapter and self.llm_adapter.has_filter_provider():
                try:
                    prompt = self.prompts.LEARNING_QUALITY_MONITOR_CONSISTENCY_PROMPT.format(
                        original_persona_prompt=original_prompt,
                        updated_persona_prompt=updated_prompt
                    )
                    
                    response = await self.llm_adapter.filter_chat_completion(prompt=prompt)
                    
                    if response:
                        try:
                            # 解析LLM返回的一致性得分
                            consistency_text = response.strip()
                            logger.debug(f"LLM一致性评估原始响应: {consistency_text}")
                            
                            # 增强的数值提取逻辑
                            import re
                            # 先尝试提取明确的分数格式
                            score_patterns = [
                                r'一致性[：:]\s*([0-9]*\.?[0-9]+)',
                                r'得分[：:]\s*([0-9]*\.?[0-9]+)',
                                r'分数[：:]\s*([0-9]*\.?[0-9]+)',
                                r'([0-9]*\.?[0-9]+)', # 任何数字
                            ]
                            
                            for pattern in score_patterns:
                                numbers = re.findall(pattern, consistency_text)
                                if numbers:
                                    try:
                                        score = float(numbers[0])
                                        # 如果分数大于1，可能是百分制，转换为小数
                                        if score > 1.0:
                                            score = score / 100.0
                                        # 确保分数在合理范围内
                                        consistency_score = max(0.1, min(score, 1.0)) # 最低0.1，避免0.0
                                        logger.debug(f"解析得到一致性得分: {consistency_score}")
                                        return consistency_score
                                    except ValueError:
                                        continue
                            
                            # 如果无法解析数值，根据关键词判断
                            consistency_text_lower = consistency_text.lower()
                            if any(word in consistency_text_lower for word in ['很好', '高', '优秀', 'good', 'high']):
                                logger.debug("基于关键词判断为高一致性")
                                return 0.8
                            elif any(word in consistency_text_lower for word in ['中等', '一般', 'medium', 'average']):
                                logger.debug("基于关键词判断为中等一致性")
                                return 0.6
                            elif any(word in consistency_text_lower for word in ['低', '差', 'low', 'poor']):
                                logger.debug("基于关键词判断为低一致性")
                                return 0.4
                            else:
                                logger.debug("无法解析一致性评估，返回中等默认值")
                                return 0.6 # 提高默认值
                        except (ValueError, IndexError) as e:
                            logger.warning(f"解析一致性得分失败: {e}, 响应: {consistency_text}")
                            return 0.6 # 提高默认值
                    else:
                        logger.warning("LLM一致性评估无响应")
                        return 0.6 # 提高默认值
                except Exception as e:
                    logger.error(f"框架适配器计算人格一致性失败: {e}")
                    return 0.6 # 提高默认值
            else:
                logger.warning("没有可用的Filter Provider，使用简单文本相似度计算")
                # 简单的文本相似度计算作为后备方案
                return self._calculate_text_similarity(original_prompt, updated_prompt)
            
        except Exception as e:
            logger.error(f"计算人格一致性失败: {e}")
            return 0.6 # 提高默认值，避免阻塞学习

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度作为后备方案"""
        try:
            if not text1 or not text2:
                return 0.6
            
            # 简单的字符级相似度计算
            text1_clean = text1.strip().lower()
            text2_clean = text2.strip().lower()
            
            if text1_clean == text2_clean:
                return 0.95
            
            # 计算最长公共子序列
            def lcs_length(s1, s2):
                m, n = len(s1), len(s2)
                dp = [[0] * (n + 1) for _ in range(m + 1)]
                
                for i in range(1, m + 1):
                    for j in range(1, n + 1):
                        if s1[i-1] == s2[j-1]:
                            dp[i][j] = dp[i-1][j-1] + 1
                        else:
                            dp[i][j] = max(dp[i-1][j], dp[i][j-1])
                
                return dp[m][n]
            
            lcs_len = lcs_length(text1_clean, text2_clean)
            max_len = max(len(text1_clean), len(text2_clean))
            
            if max_len == 0:
                return 0.6
            
            similarity = lcs_len / max_len
            
            # 确保相似度在合理范围内，避免过低导致学习停滞
            return max(0.4, min(similarity, 1.0))
            
        except Exception as e:
            logger.warning(f"计算文本相似度失败: {e}")
            return 0.6

    async def _calculate_style_stability(self, messages: List[Dict[str, Any]]) -> float:
        """计算风格稳定性"""
        if len(messages) < 2:
            return 1.0
            
        try:
            # 分析消息的风格特征
            style_features = []
            for msg in messages:
                features = {
                    'length': len(msg['message']),
                    'punctuation_ratio': self._get_punctuation_ratio(msg['message']),
                    'emoji_count': self._count_emoji(msg['message']),
                    'question_count': msg['message'].count('?') + msg['message'].count('？'),
                    'exclamation_count': msg['message'].count('!') + msg['message'].count('！')
                }
                style_features.append(features)
            
            # 计算特征方差（稳定性与方差成反比）
            variance_scores = []
            for feature in ['length', 'punctuation_ratio', 'emoji_count']:
                values = [f[feature] for f in style_features]
                if len(values) > 1:
                    mean_val = sum(values) / len(values)
                    variance = sum((x - mean_val) ** 2 for x in values) / len(values)
                    # 归一化方差得分（越小越稳定）
                    normalized_variance = min(variance / (mean_val + 1), 1.0)
                    variance_scores.append(1.0 - normalized_variance)
            
            return sum(variance_scores) / len(variance_scores) if variance_scores else 0.5
            
        except Exception as e:
            logger.warning(f"风格稳定性计算失败: {e}")
            return 0.5

    async def _calculate_vocabulary_diversity(self, messages: List[Dict[str, Any]]) -> float:
        """计算词汇多样性"""
        try:
            all_text = ' '.join([msg['message'] for msg in messages])
            words = all_text.split()
            
            if len(words) == 0:
                return 0.0
            
            unique_words = set(words)
            diversity_ratio = len(unique_words) / len(words)
            
            # 归一化到0-1范围
            return min(diversity_ratio * 2, 1.0)
            
        except Exception as e:
            logger.warning(f"词汇多样性计算失败: {e}")
            return 0.5

    async def _calculate_emotional_balance(self, messages: List[Dict[str, Any]]) -> float:
        """使用LLM计算情感平衡性"""
        if not self.llm_adapter or not self.llm_adapter.has_refine_provider():
            return self._simple_emotional_balance(messages)

        messages_text = "\n".join([msg['message'] for msg in messages])
        
        prompt = self.prompts.LEARNING_QUALITY_MONITOR_EMOTIONAL_BALANCE_PROMPT.format(
            batch_messages=messages_text
        )
        try:
            # 使用框架适配器
            if self.llm_adapter and self.llm_adapter.has_refine_provider():
                response = await self.llm_adapter.refine_chat_completion(prompt=prompt)
            else:
                logger.warning("没有可用的LLM服务")
                return self._simple_emotional_balance(messages)
            
            # 处理响应
            response_text = response if isinstance(response, str) else (response.text() if response and hasattr(response, 'text') else None)
            if response_text:
                # 使用安全的JSON解析
                default_scores = {
                    "积极": 0.5,
                    "消极": 0.5,
                    "中性": 0.5
                }
                
                emotional_scores = safe_parse_llm_json(response_text, fallback_result=default_scores)
                
                if emotional_scores and isinstance(emotional_scores, dict):
                    # 确保所有分数都在0-1之间
                    for key, value in emotional_scores.items():
                        emotional_scores[key] = max(0.0, min(float(value), 1.0))
                    
                    # 计算情感平衡性：积极情感减去消极情感，再调整到0-1范围
                    positive_score = emotional_scores.get("积极", 0.5)
                    negative_score = emotional_scores.get("消极", 0.5)
                    balance_score = (positive_score - negative_score + 1.0) / 2.0 # 转换到0-1范围
                    return max(0.0, min(balance_score, 1.0))
                else:
                    return self._simple_emotional_balance(messages)
            return self._simple_emotional_balance(messages)
        except Exception as e:
            logger.warning(f"LLM情感平衡性计算失败，使用简化算法: {e}")
            return self._simple_emotional_balance(messages)

    def _simple_emotional_balance(self, messages: List[Dict[str, Any]]) -> float:
        """简化的情感平衡性计算（备用）"""
        positive_words = ['好', '棒', '赞', '喜欢', '开心', '高兴', '哈哈']
        negative_words = ['不', '没', '坏', '烦', '讨厌', '生气', '难过']
        
        pos_count = 0
        neg_count = 0
        
        for msg in messages:
            text = msg['message']
            for word in positive_words:
                pos_count += text.count(word)
            for word in negative_words:
                neg_count += text.count(word)
        
        total_emotional = pos_count + neg_count
        if total_emotional == 0:
            return 0.8 # 中性情感
        
        # 计算平衡性（越接近0.5越平衡）
        pos_ratio = pos_count / total_emotional
        balance_score = 1.0 - abs(pos_ratio - 0.5) * 2
        
        return balance_score

    async def _calculate_coherence(self, persona: Dict[str, Any]) -> float:
        """计算逻辑连贯性"""
        try:
            prompt_text = persona.get('prompt', '')
            if not prompt_text:
                return 0.0
            
            # 简单的连贯性检查
            sentences = prompt_text.split('。')
            if len(sentences) < 2:
                return 0.8
            
            # 检查句子长度一致性和结构完整性
            sentence_lengths = [len(s.strip()) for s in sentences if s.strip()]
            if not sentence_lengths:
                return 0.0
            
            avg_length = sum(sentence_lengths) / len(sentence_lengths)
            length_variance = sum((l - avg_length) ** 2 for l in sentence_lengths) / len(sentence_lengths)
            
            # 归一化连贯性得分
            coherence = max(0.0, 1.0 - length_variance / (avg_length + 1))
            
            return min(coherence, 1.0)
            
        except Exception as e:
            logger.warning(f"连贯性计算失败: {e}")
            return 0.5

    async def _check_quality_alerts(self, metrics: PersonaMetrics):
        """检查质量警报"""
        alerts = []
        
        # 一致性检查
        if metrics.consistency_score < self.consistency_threshold:
            alerts.append(LearningAlert(
                alert_type="consistency",
                severity="high" if metrics.consistency_score < 0.5 else "medium",
                message=f"人格一致性得分过低: {metrics.consistency_score:.3f}",
                timestamp=datetime.now().isoformat(),
                metrics={'consistency_score': metrics.consistency_score},
                suggestions=["建议人工审核人格变化", "考虑回滚到之前的人格版本"]
            ))
        
        # 稳定性检查
        if metrics.style_stability < self.stability_threshold:
            alerts.append(LearningAlert(
                alert_type="stability",
                severity="medium",
                message=f"风格稳定性不足: {metrics.style_stability:.3f}",
                timestamp=datetime.now().isoformat(),
                metrics={'style_stability': metrics.style_stability},
                suggestions=["增加训练数据一致性", "调整学习率"]
            ))
        
        # 风格偏移检查
        if len(self.historical_metrics) >= 2:
            current_drift = self._calculate_style_drift(
                self.historical_metrics[-2], metrics
            )
            if current_drift > self.drift_threshold:
                alerts.append(LearningAlert(
                    alert_type="drift",
                    severity="critical" if current_drift > 0.5 else "high",
                    message=f"检测到显著风格偏移: {current_drift:.3f}",
                    timestamp=datetime.now().isoformat(),
                    metrics={'style_drift': current_drift},
                    suggestions=["立即暂停自动学习", "人工审核学习数据", "考虑重置人格"]
                ))
        
        # 存储警报
        self.alerts_history.extend(alerts)
        
        # 记录警报
        for alert in alerts:
            logger.warning(f"学习质量警报 [{alert.severity}]: {alert.message}")

    def _calculate_style_drift(self, prev_metrics: PersonaMetrics, curr_metrics: PersonaMetrics) -> float:
        """计算风格偏移程度"""
        # 计算关键指标的变化幅度
        consistency_drift = abs(curr_metrics.consistency_score - prev_metrics.consistency_score)
        stability_drift = abs(curr_metrics.style_stability - prev_metrics.style_stability)
        diversity_drift = abs(curr_metrics.vocabulary_diversity - prev_metrics.vocabulary_diversity)
        
        # 加权平均偏移
        weighted_drift = (
            consistency_drift * 0.4 +
            stability_drift * 0.3 +
            diversity_drift * 0.3
        )
        
        return weighted_drift

    def _get_punctuation_ratio(self, text: str) -> float:
        """获取标点符号比例"""
        punctuation = '，。！？；：、""''()（）【】'
        punct_count = sum(1 for char in text if char in punctuation)
        return punct_count / len(text) if text else 0.0

    def _count_emoji(self, text: str) -> int:
        """统计表情符号数量"""
        # 简单的表情符号检测
        emoji_patterns = ['', '', '', '', '', '', '']
        count = 0
        for emoji in emoji_patterns:
            count += text.count(emoji)
        return count

    async def get_quality_report(self) -> Dict[str, Any]:
        """获取质量报告"""
        if not self.historical_metrics:
            return {"error": "暂无历史数据"}
        
        latest_metrics = self.historical_metrics[-1]
        
        # 计算趋势
        trends = {}
        if len(self.historical_metrics) >= 2:
            prev_metrics = self.historical_metrics[-2]
            trends = {
                'consistency_trend': latest_metrics.consistency_score - prev_metrics.consistency_score,
                'stability_trend': latest_metrics.style_stability - prev_metrics.style_stability,
                'diversity_trend': latest_metrics.vocabulary_diversity - prev_metrics.vocabulary_diversity
            }
        
        # 获取最近的警报
        recent_alerts = [
            alert for alert in self.alerts_history
            if datetime.fromisoformat(alert.timestamp) > datetime.now() - timedelta(hours=24)
        ]
        
        return {
            'current_metrics': {
                'consistency_score': latest_metrics.consistency_score,
                'style_stability': latest_metrics.style_stability,
                'vocabulary_diversity': latest_metrics.vocabulary_diversity,
                'emotional_balance': latest_metrics.emotional_balance,
                'coherence_score': latest_metrics.coherence_score
            },
            'trends': trends,
            'recent_alerts': len(recent_alerts),
            'alert_summary': {
                'critical': len([a for a in recent_alerts if a.severity == 'critical']),
                'high': len([a for a in recent_alerts if a.severity == 'high']),
                'medium': len([a for a in recent_alerts if a.severity == 'medium'])
            },
            'recommendations': self._generate_recommendations(latest_metrics, recent_alerts)
        }

    def _generate_recommendations(self, metrics: PersonaMetrics, alerts: List[LearningAlert]) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        if metrics.consistency_score < 0.7:
            recommendations.append("建议增加人格一致性检查")
        
        if metrics.style_stability < 0.6:
            recommendations.append("建议调整学习数据筛选标准")
        
        if len(alerts) > 5:
            recommendations.append("警报频繁，建议人工介入审核")
        
        if not recommendations:
            recommendations.append("学习质量良好，可继续自动学习")
        
        return recommendations

    async def should_pause_learning(self) -> tuple[bool, str]:
        """判断是否应该暂停学习"""
        if not self.historical_metrics:
            return False, ""
        
        latest_metrics = self.historical_metrics[-1]
        
        # 检查关键指标
        if latest_metrics.consistency_score < 0.4:
            return True, "人格一致性严重下降"
        
        # 检查最近的严重警报
        recent_critical_alerts = [
            alert for alert in self.alerts_history
            if (alert.severity in ['critical', 'high'] and 
                datetime.fromisoformat(alert.timestamp) > datetime.now() - timedelta(hours=1))
        ]
        
        if len(recent_critical_alerts) >= 2:
            return True, "检测到多个严重质量问题"
        
        return False, ""

    async def adjust_thresholds_based_on_history(self):
        """基于历史指标动态调整阈值"""
        try:
            if len(self.historical_metrics) < 5:
                # 历史数据不足，使用默认阈值
                return
            
            # 获取最近的指标
            recent_metrics = self.historical_metrics[-5:]
            
            # 计算最近的平均表现
            avg_consistency = sum(m.consistency_score for m in recent_metrics) / len(recent_metrics)
            avg_stability = sum(m.style_stability for m in recent_metrics) / len(recent_metrics)
            
            # 动态调整阈值 - 如果系统表现持续良好，可以适当提高阈值
            if avg_consistency > 0.8:
                self.consistency_threshold = min(0.8, self.consistency_threshold + 0.05)
            elif avg_consistency < 0.5:
                self.consistency_threshold = max(0.6, self.consistency_threshold - 0.05)
            
            if avg_stability > 0.7:
                self.stability_threshold = min(0.7, self.stability_threshold + 0.05)
            elif avg_stability < 0.4:
                self.stability_threshold = max(0.5, self.stability_threshold - 0.05)
            
            # 根据变化幅度调整偏移阈值
            if len(recent_metrics) >= 2:
                recent_changes = []
                for i in range(1, len(recent_metrics)):
                    change = abs(recent_metrics[i].consistency_score - recent_metrics[i-1].consistency_score)
                    recent_changes.append(change)
                
                avg_change = sum(recent_changes) / len(recent_changes)
                if avg_change < 0.1:
                    # 变化很小，可以提高偏移阈值
                    self.drift_threshold = min(0.4, self.drift_threshold + 0.05)
                elif avg_change > 0.3:
                    # 变化很大，降低偏移阈值
                    self.drift_threshold = max(0.2, self.drift_threshold - 0.05)
            
            logger.debug(f"动态调整阈值 - 一致性: {self.consistency_threshold:.2f}, "
                        f"稳定性: {self.stability_threshold:.2f}, "
                        f"偏移: {self.drift_threshold:.2f}")
                        
        except Exception as e:
            logger.warning(f"动态调整阈值失败: {e}")

    async def stop(self):
        """停止服务"""
        try:
            logger.info("学习质量监控服务已停止")
            return True
        except Exception as e:
            logger.error(f"停止学习质量监控服务失败: {e}")
            return False
