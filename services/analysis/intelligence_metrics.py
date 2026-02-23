"""
智能化指标计算服务
负责计算学习效率、置信度等智能化指标
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from astrbot.api import logger
from ...config import PluginConfig


@dataclass
class LearningEfficiencyMetrics:
    """学习效率指标"""
    overall_efficiency: float  # 总体学习效率 (0-100)
    message_filter_rate: float  # 消息筛选率
    content_refine_quality: float  # 内容提炼质量
    style_learning_progress: float  # 对话风格学习进度
    persona_update_quality: float  # 人格更新质量
    active_strategies_count: int  # 激活的学习策略数量
    jargon_learning_score: float = 0.0  # 黑话学习得分 (0-100)
    social_relation_score: float = 0.0  # 社交关系学习得分 (0-100)
    affection_score: float = 0.0  # 好感度系统得分 (0-100)

    # 各维度权重分配
    weights: Dict[str, float] = None

    def __post_init__(self):
        if self.weights is None:
            self.weights = {
                'message_filter': 0.15,
                'content_refine': 0.15,
                'style_learning': 0.20,
                'persona_update': 0.10,
                'active_strategies': 0.10,
                'jargon_learning': 0.10,
                'social_relation': 0.10,
                'affection': 0.10,
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

    def __init__(self, config: PluginConfig, db_manager=None, llm_adapter=None):
        self.config = config
        self.db_manager = db_manager
        self.llm_adapter = llm_adapter
        self._logger = logger  # 添加 logger 属性
        self.logger = logger

    async def calculate_learning_efficiency(
        self,
        total_messages: int,
        filtered_messages: int,
        refined_content_count: int = 0,
        style_patterns_learned: int = 0,
        persona_updates_count: int = 0,
        active_strategies: List[str] = None,
        jargon_count: int = 0,
        social_relation_count: int = 0,
        affection_users_count: int = 0
    ) -> LearningEfficiencyMetrics:
        """
        计算综合学习效率

        改进算法:不再仅基于 filtered_messages / total_messages
        而是综合考虑多个维度的学习成果
        """
        if active_strategies is None:
            active_strategies = []

        # 1. 消息筛选率 (基础维度)
        # 确保类型转换为整数，并处理非数字值
        try:
            total_messages = int(total_messages) if total_messages else 0
        except (ValueError, TypeError) as e:
            self._logger.warning(f"total_messages 类型转换失败，值为: {total_messages}, 错误: {e}")
            total_messages = 0

        try:
            filtered_messages = int(filtered_messages) if filtered_messages else 0
        except (ValueError, TypeError) as e:
            self._logger.warning(f"filtered_messages 类型转换失败，值为: {filtered_messages}, 错误: {e}")
            filtered_messages = 0

        message_filter_rate = (filtered_messages / total_messages * 100) if total_messages > 0 else 0

        # 确保其他参数也是整数类型
        try:
            refined_content_count = int(refined_content_count) if refined_content_count else 0
        except (ValueError, TypeError) as e:
            self._logger.warning(f"refined_content_count 类型转换失败，值为: {refined_content_count}, 错误: {e}")
            refined_content_count = 0

        try:
            style_patterns_learned = int(style_patterns_learned) if style_patterns_learned else 0
        except (ValueError, TypeError) as e:
            self._logger.warning(f"style_patterns_learned 类型转换失败，值为: {style_patterns_learned}, 错误: {e}")
            style_patterns_learned = 0

        try:
            persona_updates_count = int(persona_updates_count) if persona_updates_count else 0
        except (ValueError, TypeError) as e:
            self._logger.warning(f"persona_updates_count 类型转换失败，值为: {persona_updates_count}, 错误: {e}")
            persona_updates_count = 0

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

        # 6. 黑话学习得分
        jargon_learning_score = self._calculate_jargon_score(jargon_count, total_messages)

        # 7. 社交关系学习得分
        social_relation_score = self._calculate_social_relation_score(
            social_relation_count, total_messages
        )

        # 8. 好感度系统得分
        affection_score = self._calculate_affection_score(affection_users_count)

        # 计算加权总体效率
        metrics = LearningEfficiencyMetrics(
            overall_efficiency=0,  # 稍后计算
            message_filter_rate=message_filter_rate,
            content_refine_quality=content_refine_quality,
            style_learning_progress=style_learning_progress,
            persona_update_quality=persona_update_quality,
            active_strategies_count=len(active_strategies),
            jargon_learning_score=jargon_learning_score,
            social_relation_score=social_relation_score,
            affection_score=affection_score
        )

        # 使用权重计算总体效率
        metrics.overall_efficiency = (
            metrics.weights['message_filter'] * message_filter_rate +
            metrics.weights['content_refine'] * content_refine_quality +
            metrics.weights['style_learning'] * style_learning_progress +
            metrics.weights['persona_update'] * persona_update_quality +
            metrics.weights['active_strategies'] * active_strategies_score +
            metrics.weights['jargon_learning'] * jargon_learning_score +
            metrics.weights['social_relation'] * social_relation_score +
            metrics.weights['affection'] * affection_score
        )

        self.logger.debug(
            f"学习效率计算完成: 总体={metrics.overall_efficiency:.2f}%, "
            f"筛选率={message_filter_rate:.2f}%, "
            f"提炼质量={content_refine_quality:.2f}%, "
            f"风格进度={style_learning_progress:.2f}%, "
            f"人格质量={persona_update_quality:.2f}%, "
            f"黑话={jargon_learning_score:.2f}%, "
            f"社交={social_relation_score:.2f}%, "
            f"好感度={affection_score:.2f}%, "
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

    def _calculate_jargon_score(self, jargon_count: int, message_count: int) -> float:
        """计算黑话学习得分 (0-100)

        基于已学习的黑话数量与消息量的比例评估黑话挖掘效果
        """
        if message_count == 0:
            return 0.0

        # 每100条消息预期学到2-5个黑话
        expected = message_count / 50
        if expected == 0:
            return 0.0

        ratio = jargon_count / expected
        # 在0.5-2.0倍之间为合理区间
        if ratio < 0.1:
            return min(100, ratio * 200)  # 很少黑话,低分但不为0
        elif ratio > 3.0:
            return max(50, 100 - (ratio - 3.0) * 10)  # 过多可能噪声大
        else:
            return min(100, 50 + ratio * 25)

    def _calculate_social_relation_score(
        self, relation_count: int, message_count: int
    ) -> float:
        """计算社交关系学习得分 (0-100)

        基于已建立的社交关系数量评估社交图谱构建情况
        """
        if message_count == 0:
            return 0.0

        # 每200条消息预期建立1-3个社交关系
        expected = message_count / 100
        if expected == 0:
            return 0.0

        ratio = relation_count / expected
        if ratio < 0.1:
            return min(100, ratio * 200)
        elif ratio > 5.0:
            return max(60, 100 - (ratio - 5.0) * 5)
        else:
            return min(100, 40 + ratio * 12)

    def _calculate_affection_score(self, users_count: int) -> float:
        """计算好感度系统得分 (0-100)

        基于参与好感度追踪的用户数量评估好感度系统运行状况
        """
        if users_count == 0:
            return 0.0

        # 有追踪用户即有基础分，随用户数增长
        if users_count >= 10:
            return 100.0
        elif users_count >= 5:
            return 80.0
        else:
            return min(100, 30 + users_count * 10)

    async def calculate_persona_confidence(
        self,
        proposed_content: str,
        original_content: str,
        learning_source: str,
        message_count: int = 0,
        llm_adapter=None
    ) -> ConfidenceMetrics:
        """
        人格置信度评估（纯本地启发式计算，不调用 LLM）
        """
        return self._calculate_basic_confidence(
            proposed_content,
            original_content,
            learning_source,
            message_count
        )

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
