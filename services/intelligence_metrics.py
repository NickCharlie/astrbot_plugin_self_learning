"""
智能化指标计算服务
负责计算学习效率、置信度等智能化指标
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from astrbot.api import logger
from ..config import PluginConfig
from ..utils.json_utils import safe_parse_llm_json


@dataclass
class LearningEfficiencyMetrics:
    """学习效率指标"""
    overall_efficiency: float  # 总体学习效率 (0-100)
    message_filter_rate: float  # 消息筛选率
    content_refine_quality: float  # 内容提炼质量
    style_learning_progress: float  # 对话风格学习进度
    persona_update_quality: float  # 人格更新质量
    active_strategies_count: int  # 激活的学习策略数量

    # 各维度权重分配
    weights: Dict[str, float] = None

    def __post_init__(self):
        if self.weights is None:
            # 默认权重分配
            self.weights = {
                'message_filter': 0.20,  # 消息筛选 20%
                'content_refine': 0.25,  # 内容提炼 25%
                'style_learning': 0.30,  # 风格学习 30%
                'persona_update': 0.15,  # 人格更新 15%
                'active_strategies': 0.10  # 学习策略 10%
            }


@dataclass
class ConfidenceMetrics:
    """置信度评估指标"""
    overall_confidence: float  # 总体置信度 (0-1)
    content_relevance: float  # 内容相关性
    consistency_score: float  # 一致性得分
    quality_score: float  # 质量得分
    diversity_score: float  # 多样性得分
    source_reliability: float  # 来源可靠性

    # 评判依据
    evaluation_basis: Dict[str, Any] = None


class IntelligenceMetricsService:
    """智能化指标计算服务"""

    def __init__(self, config: PluginConfig, db_manager=None):
        self.config = config
        self.db_manager = db_manager
        self.logger = logger

    async def calculate_learning_efficiency(
        self,
        total_messages: int,
        filtered_messages: int,
        refined_content_count: int = 0,
        style_patterns_learned: int = 0,
        persona_updates_count: int = 0,
        active_strategies: List[str] = None
    ) -> LearningEfficiencyMetrics:
        """
        计算综合学习效率

        改进算法:不再仅基于 filtered_messages / total_messages
        而是综合考虑多个维度的学习成果
        """
        if active_strategies is None:
            active_strategies = []

        # 1. 消息筛选率 (基础维度)
        message_filter_rate = (filtered_messages / total_messages * 100) if total_messages > 0 else 0

        # 2. 内容提炼质量 (考虑提炼后有效内容的数量和质量)
        content_refine_quality = self._calculate_refine_quality(
            filtered_messages,
            refined_content_count
        )

        # 3. 对话风格学习进度 (基于学到的风格模式数量)
        style_learning_progress = self._calculate_style_progress(
            style_patterns_learned,
            filtered_messages
        )

        # 4. 人格更新质量 (基于推送到审查页面的新内容质量和数量)
        persona_update_quality = self._calculate_persona_update_quality(
            persona_updates_count,
            filtered_messages
        )

        # 5. 激活的学习策略数量得分
        active_strategies_score = self._calculate_strategies_score(active_strategies)

        # 计算加权总体效率
        metrics = LearningEfficiencyMetrics(
            overall_efficiency=0,  # 稍后计算
            message_filter_rate=message_filter_rate,
            content_refine_quality=content_refine_quality,
            style_learning_progress=style_learning_progress,
            persona_update_quality=persona_update_quality,
            active_strategies_count=len(active_strategies)
        )

        # 使用权重计算总体效率
        metrics.overall_efficiency = (
            metrics.weights['message_filter'] * message_filter_rate +
            metrics.weights['content_refine'] * content_refine_quality +
            metrics.weights['style_learning'] * style_learning_progress +
            metrics.weights['persona_update'] * persona_update_quality +
            metrics.weights['active_strategies'] * active_strategies_score
        )

        self.logger.debug(
            f"学习效率计算完成: 总体={metrics.overall_efficiency:.2f}%, "
            f"筛选率={message_filter_rate:.2f}%, "
            f"提炼质量={content_refine_quality:.2f}%, "
            f"风格进度={style_learning_progress:.2f}%, "
            f"人格质量={persona_update_quality:.2f}%, "
            f"策略数={len(active_strategies)}"
        )

        return metrics

    def _calculate_refine_quality(self, filtered_count: int, refined_count: int) -> float:
        """计算内容提炼质量得分 (0-100)"""
        if filtered_count == 0:
            return 0

        # 提炼率
        refine_rate = (refined_count / filtered_count) * 100 if filtered_count > 0 else 0

        # 质量惩罚: 如果提炼率过低(说明筛选质量差)或过高(可能没有有效提炼)
        if refine_rate < 10:
            quality = refine_rate * 0.5  # 提炼率太低,质量打折
        elif refine_rate > 90:
            quality = 90 - (refine_rate - 90) * 2  # 提炼率过高,可能没有有效筛选
        else:
            quality = refine_rate

        return min(100, max(0, quality))

    def _calculate_style_progress(self, patterns_learned: int, message_count: int) -> float:
        """计算对话风格学习进度得分 (0-100)"""
        if message_count == 0:
            return 0

        # 每N条消息学到1个模式算合理
        expected_patterns = message_count / 20  # 每20条消息预期学到1个模式

        if expected_patterns == 0:
            return 0

        # 计算学习进度
        progress = (patterns_learned / expected_patterns) * 100

        # 限制在合理范围内
        return min(100, max(0, progress))

    def _calculate_persona_update_quality(self, updates_count: int, message_count: int) -> float:
        """计算人格更新质量得分 (0-100)"""
        if message_count == 0:
            return 0

        # 每N条消息产生1个待审查的更新算合理
        expected_updates = message_count / 50  # 每50条消息预期产生1个更新

        if expected_updates == 0:
            return 0

        # 计算更新质量
        quality = (updates_count / expected_updates) * 100

        # 如果更新过多,可能质量不高
        if quality > 120:
            quality = 120 - (quality - 120) * 0.5

        return min(100, max(0, quality))

    def _calculate_strategies_score(self, active_strategies: List[str]) -> float:
        """计算激活学习策略的得分 (0-100)"""
        # 预期的学习策略列表
        expected_strategies = [
            "message_filtering",      # 消息筛选
            "content_refinement",     # 内容提炼
            "style_learning",         # 风格学习
            "persona_evolution",      # 人格演化
            "context_awareness",      # 上下文感知
            "emotion_learning",       # 情感学习
            "social_analysis"         # 社交分析
        ]

        if not expected_strategies:
            return 100  # 如果没有预期策略,返回满分

        # 计算激活率
        active_count = len([s for s in active_strategies if s in expected_strategies])
        activation_rate = (active_count / len(expected_strategies)) * 100

        return activation_rate

    async def calculate_persona_confidence(
        self,
        proposed_content: str,
        original_content: str,
        learning_source: str,
        message_count: int = 0,
        llm_adapter=None
    ) -> ConfidenceMetrics:
        """
        智能化人格置信度评估

        使用LLM模型进行多维度评判
        """
        # 基础置信度评估 (不依赖LLM)
        basic_metrics = self._calculate_basic_confidence(
            proposed_content,
            original_content,
            learning_source,
            message_count
        )

        # 如果有LLM适配器,使用智能评估
        if llm_adapter:
            try:
                llm_metrics = await self._calculate_llm_confidence(
                    proposed_content,
                    original_content,
                    learning_source,
                    llm_adapter
                )

                # 融合基础评估和LLM评估
                return self._merge_confidence_metrics(basic_metrics, llm_metrics)
            except Exception as e:
                self.logger.warning(f"LLM置信度评估失败,使用基础评估: {e}")
                return basic_metrics
        else:
            return basic_metrics

    def _calculate_basic_confidence(
        self,
        proposed_content: str,
        original_content: str,
        learning_source: str,
        message_count: int
    ) -> ConfidenceMetrics:
        """计算基础置信度 (不依赖LLM)"""

        # 1. 内容相关性: 基于内容长度和变化程度
        content_relevance = self._calculate_content_relevance(
            proposed_content,
            original_content
        )

        # 2. 一致性得分: 基于内容结构的一致性
        consistency_score = self._calculate_consistency(
            proposed_content,
            original_content
        )

        # 3. 质量得分: 基于内容长度、复杂度
        quality_score = self._calculate_quality(proposed_content)

        # 4. 多样性得分: 基于新内容的多样性
        diversity_score = self._calculate_diversity(
            proposed_content,
            original_content
        )

        # 5. 来源可靠性: 基于学习来源和消息数量
        source_reliability = self._calculate_source_reliability(
            learning_source,
            message_count
        )

        # 计算总体置信度 (加权平均)
        overall_confidence = (
            content_relevance * 0.25 +
            consistency_score * 0.20 +
            quality_score * 0.25 +
            diversity_score * 0.15 +
            source_reliability * 0.15
        )

        return ConfidenceMetrics(
            overall_confidence=overall_confidence,
            content_relevance=content_relevance,
            consistency_score=consistency_score,
            quality_score=quality_score,
            diversity_score=diversity_score,
            source_reliability=source_reliability,
            evaluation_basis={
                'method': 'basic_calculation',
                'message_count': message_count,
                'learning_source': learning_source
            }
        )

    def _calculate_content_relevance(self, proposed: str, original: str) -> float:
        """计算内容相关性"""
        if not proposed or not original:
            return 0.0

        # 计算文本相似度的简单方法
        proposed_words = set(proposed.split())
        original_words = set(original.split())

        if not original_words:
            return 0.0

        # Jaccard相似度
        intersection = proposed_words & original_words
        union = proposed_words | original_words

        if not union:
            return 0.0

        similarity = len(intersection) / len(union)

        # 如果完全相同,相关性较低(因为没有新内容)
        if similarity > 0.95:
            return 0.5
        # 如果完全不同,相关性也较低
        elif similarity < 0.1:
            return 0.3
        else:
            # 中等相似度最好,说明既保留了原有内容,又有新内容
            return min(1.0, 0.5 + (0.5 - abs(similarity - 0.5)))

    def _calculate_consistency(self, proposed: str, original: str) -> float:
        """计算一致性得分"""
        if not proposed:
            return 0.0

        # 检查基本结构一致性
        proposed_lines = proposed.strip().split('\n')
        original_lines = original.strip().split('\n') if original else []

        # 行数变化合理性
        if len(proposed_lines) < len(original_lines) * 0.5:
            return 0.4  # 内容减少太多
        elif len(proposed_lines) > len(original_lines) * 3:
            return 0.5  # 内容增加太多
        else:
            return 0.9  # 合理的变化

    def _calculate_quality(self, proposed: str) -> float:
        """计算质量得分"""
        if not proposed:
            return 0.0

        quality = 0.5  # 基础分数

        # 长度合理性
        length = len(proposed)
        if 50 < length < 2000:
            quality += 0.2
        elif length >= 2000:
            quality += 0.1

        # 包含换行符(结构化内容)
        if '\n' in proposed:
            quality += 0.1

        # 包含标点符号(完整句子)
        if any(p in proposed for p in ['。', '!', '?', '！', '?', '.', '...', '~']):
            quality += 0.1

        # 不全是重复内容
        unique_chars = len(set(proposed))
        total_chars = len(proposed)
        if total_chars > 0 and unique_chars / total_chars > 0.3:
            quality += 0.1

        return min(1.0, quality)

    def _calculate_diversity(self, proposed: str, original: str) -> float:
        """计算多样性得分"""
        if not proposed:
            return 0.0

        proposed_words = set(proposed.split())
        original_words = set(original.split()) if original else set()

        # 新词汇数量
        new_words = proposed_words - original_words

        if not proposed_words:
            return 0.0

        # 新词汇比例
        new_ratio = len(new_words) / len(proposed_words)

        # 10-50% 的新词汇算合理
        if 0.1 <= new_ratio <= 0.5:
            return 0.9
        elif new_ratio > 0.5:
            return 0.7  # 太多新词可能偏离原意
        else:
            return 0.5  # 太少新词缺乏创新

    def _calculate_source_reliability(self, source: str, message_count: int) -> float:
        """计算来源可靠性"""
        reliability = 0.5  # 基础可靠性

        # 基于学习来源
        if '风格学习' in source or 'style' in source.lower():
            reliability += 0.2
        if '人格' in source or 'persona' in source.lower():
            reliability += 0.1
        if '重新学习' in source or 'relearn' in source.lower():
            reliability += 0.1

        # 基于消息数量
        if message_count > 100:
            reliability += 0.1
        elif message_count > 50:
            reliability += 0.05

        return min(1.0, reliability)

    async def _calculate_llm_confidence(
        self,
        proposed_content: str,
        original_content: str,
        learning_source: str,
        llm_adapter
    ) -> ConfidenceMetrics:
        """使用LLM进行智能置信度评估"""

        prompt = self._build_confidence_evaluation_prompt(
            proposed_content,
            original_content,
            learning_source
        )

        # 调用LLM进行评估
        response = await llm_adapter.call_llm(
            prompt=prompt,
            context_id="confidence_evaluation",
            max_tokens=500
        )

        # 解析LLM响应
        metrics = self._parse_llm_confidence_response(response)

        return metrics

    def _build_confidence_evaluation_prompt(
        self,
        proposed_content: str,
        original_content: str,
        learning_source: str
    ) -> str:
        """构建置信度评估prompt"""

        prompt = f"""你是一个专业的人格内容质量评估专家。请对以下人格更新内容进行多维度评估。

【原始人格内容】
{original_content[:500]}{'...' if len(original_content) > 500 else ''}

【建议更新内容】
{proposed_content[:500]}{'...' if len(proposed_content) > 500 else ''}

【学习来源】{learning_source}

请从以下5个维度对建议更新内容进行评分(0.0-1.0):

1. **内容相关性** (Content Relevance): 新内容与原人格的相关性和连贯性
2. **一致性** (Consistency): 新内容与原人格风格、语气的一致程度
3. **质量** (Quality): 新内容的语言质量、表达清晰度、逻辑性
4. **多样性** (Diversity): 新内容带来的创新性和多样化程度
5. **实用性** (Practicality): 新内容对改善人格表现的实际帮助

请以JSON格式返回评分:
{{
    "content_relevance": 0.85,
    "consistency": 0.90,
    "quality": 0.88,
    "diversity": 0.75,
    "practicality": 0.80,
    "overall": 0.84,
    "reasoning": "简要说明评分理由(100字以内)"
}}

只返回JSON,不要其他内容。"""

        return prompt

    def _parse_llm_confidence_response(self, response: str) -> ConfidenceMetrics:
        """解析LLM的置信度评估响应"""
        try:
            # 使用统一的json_utils工具解析LLM响应
            data = safe_parse_llm_json(response)

            if data:
                return ConfidenceMetrics(
                    overall_confidence=data.get('overall', 0.7),
                    content_relevance=data.get('content_relevance', 0.7),
                    consistency_score=data.get('consistency', 0.7),
                    quality_score=data.get('quality', 0.7),
                    diversity_score=data.get('diversity', 0.7),
                    source_reliability=data.get('practicality', 0.7),
                    evaluation_basis={
                        'method': 'llm_evaluation',
                        'reasoning': data.get('reasoning', ''),
                        'raw_response': response
                    }
                )
        except Exception as e:
            self.logger.warning(f"解析LLM置信度响应失败: {e}")

        # 失败时返回中等置信度
        return ConfidenceMetrics(
            overall_confidence=0.6,
            content_relevance=0.6,
            consistency_score=0.6,
            quality_score=0.6,
            diversity_score=0.6,
            source_reliability=0.6,
            evaluation_basis={'method': 'fallback', 'error': str(e)}
        )

    def _merge_confidence_metrics(
        self,
        basic: ConfidenceMetrics,
        llm: ConfidenceMetrics
    ) -> ConfidenceMetrics:
        """融合基础评估和LLM评估结果"""

        # 使用加权平均 (基础30%, LLM 70%)
        return ConfidenceMetrics(
            overall_confidence=basic.overall_confidence * 0.3 + llm.overall_confidence * 0.7,
            content_relevance=basic.content_relevance * 0.3 + llm.content_relevance * 0.7,
            consistency_score=basic.consistency_score * 0.3 + llm.consistency_score * 0.7,
            quality_score=basic.quality_score * 0.3 + llm.quality_score * 0.7,
            diversity_score=basic.diversity_score * 0.3 + llm.diversity_score * 0.7,
            source_reliability=basic.source_reliability * 0.3 + llm.source_reliability * 0.7,
            evaluation_basis={
                'method': 'merged',
                'basic': basic.evaluation_basis,
                'llm': llm.evaluation_basis
            }
        )
