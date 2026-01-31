"""
黑话与表达系统相关的 Repository
提供黑话使用频率、表达生成结果、自适应响应模板的数据访问方法
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func, or_
from typing import List, Optional, Dict, Any
from astrbot.api import logger
import time

from .base_repository import BaseRepository
from ..models.orm import (
    Jargon,
    JargonUsageFrequency,
    ExpressionPattern,
    ExpressionGenerationResult,
    AdaptiveResponseTemplate
)


class JargonUsageFrequencyRepository(BaseRepository[JargonUsageFrequency]):
    """黑话使用频率 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, JargonUsageFrequency)

    async def save_usage_frequency(
        self,
        jargon_id: int,
        group_id: str,
        usage_count: int = 0,
        last_used_at: Optional[float] = None,
        success_rate: Optional[float] = None,
        context_types: Optional[str] = None
    ) -> Optional[JargonUsageFrequency]:
        """
        保存黑话使用频率

        Args:
            jargon_id: 黑话 ID
            group_id: 群组 ID
            usage_count: 使用次数
            last_used_at: 最后使用时间戳
            success_rate: 理解成功率
            context_types: 使用场景类型（JSON字符串）

        Returns:
            Optional[JargonUsageFrequency]: 创建的记录
        """
        try:
            if last_used_at is None:
                last_used_at = time.time()

            return await self.create(
                jargon_id=jargon_id,
                group_id=group_id,
                usage_count=usage_count,
                last_used_at=last_used_at,
                success_rate=success_rate,
                context_types=context_types
            )
        except Exception as e:
            logger.error(f"[JargonUsageFrequencyRepository] 保存使用频率失败: {e}")
            return None

    async def get_by_jargon(
        self,
        jargon_id: int,
        group_id: str
    ) -> Optional[JargonUsageFrequency]:
        """
        根据黑话ID和群组ID获取使用频率记录

        Args:
            jargon_id: 黑话 ID
            group_id: 群组 ID

        Returns:
            Optional[JargonUsageFrequency]: 使用频率记录
        """
        try:
            stmt = select(JargonUsageFrequency).where(
                and_(
                    JargonUsageFrequency.jargon_id == jargon_id,
                    JargonUsageFrequency.group_id == group_id
                )
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[JargonUsageFrequencyRepository] 获取使用频率失败: {e}")
            return None

    async def get_top_used_jargons(
        self,
        group_id: str,
        limit: int = 20
    ) -> List[JargonUsageFrequency]:
        """
        获取使用最频繁的黑话

        Args:
            group_id: 群组 ID
            limit: 最大返回数量

        Returns:
            List[JargonUsageFrequency]: 使用频率列表
        """
        try:
            stmt = select(JargonUsageFrequency).where(
                JargonUsageFrequency.group_id == group_id
            ).order_by(desc(JargonUsageFrequency.usage_count)).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[JargonUsageFrequencyRepository] 获取高频黑话失败: {e}")
            return []

    async def increment_usage_count(
        self,
        jargon_id: int,
        group_id: str,
        increment: int = 1,
        success: Optional[bool] = None
    ) -> bool:
        """
        增加黑话使用次数并更新成功率

        Args:
            jargon_id: 黑话 ID
            group_id: 群组 ID
            increment: 增量
            success: 本次使用是否成功（用于更新成功率）

        Returns:
            bool: 是否成功
        """
        try:
            usage_freq = await self.get_by_jargon(jargon_id, group_id)
            if not usage_freq:
                return False

            new_count = usage_freq.usage_count + increment
            update_data = {
                "usage_count": new_count,
                "last_used_at": time.time()
            }

            # 如果提供了成功标志，更新成功率
            if success is not None and usage_freq.success_rate is not None:
                # 简单的移动平均更新
                old_success = usage_freq.success_rate
                new_success_rate = (old_success * (new_count - increment) + (1.0 if success else 0.0)) / new_count
                update_data["success_rate"] = round(new_success_rate, 3)

            return await self.update(usage_freq.id, **update_data)

        except Exception as e:
            logger.error(f"[JargonUsageFrequencyRepository] 增加使用次数失败: {e}")
            return False

    async def get_usage_statistics(
        self,
        group_id: str
    ) -> Dict[str, Any]:
        """
        获取黑话使用统计

        Args:
            group_id: 群组 ID

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            # 总记录数
            total_stmt = select(func.count()).select_from(JargonUsageFrequency).where(
                JargonUsageFrequency.group_id == group_id
            )
            total_result = await self.session.execute(total_stmt)
            total_jargons = total_result.scalar() or 0

            # 总使用次数
            total_usage_stmt = select(func.sum(JargonUsageFrequency.usage_count)).where(
                JargonUsageFrequency.group_id == group_id
            )
            total_usage_result = await self.session.execute(total_usage_stmt)
            total_usage = total_usage_result.scalar() or 0

            # 平均成功率
            avg_success_stmt = select(func.avg(JargonUsageFrequency.success_rate)).where(
                and_(
                    JargonUsageFrequency.group_id == group_id,
                    JargonUsageFrequency.success_rate.isnot(None)
                )
            )
            avg_success_result = await self.session.execute(avg_success_stmt)
            avg_success_rate = avg_success_result.scalar() or 0

            return {
                "total_jargons": total_jargons,
                "total_usage_count": int(total_usage),
                "avg_success_rate": round(float(avg_success_rate), 3),
                "avg_usage_per_jargon": round(float(total_usage) / total_jargons, 2) if total_jargons > 0 else 0.0
            }

        except Exception as e:
            logger.error(f"[JargonUsageFrequencyRepository] 获取统计信息失败: {e}")
            return {
                "total_jargons": 0,
                "total_usage_count": 0,
                "avg_success_rate": 0.0,
                "avg_usage_per_jargon": 0.0
            }


class ExpressionGenerationResultRepository(BaseRepository[ExpressionGenerationResult]):
    """表达生成结果 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ExpressionGenerationResult)

    async def save_generation_result(
        self,
        group_id: str,
        pattern_id: int,
        generated_text: str,
        context: Optional[str] = None,
        quality_score: Optional[float] = None,
        user_feedback: Optional[str] = None,
        generated_at: Optional[float] = None
    ) -> Optional[ExpressionGenerationResult]:
        """
        保存表达生成结果

        Args:
            group_id: 群组 ID
            pattern_id: 表达模式 ID
            generated_text: 生成的文本
            context: 上下文（JSON字符串）
            quality_score: 质量评分
            user_feedback: 用户反馈
            generated_at: 生成时间戳

        Returns:
            Optional[ExpressionGenerationResult]: 创建的记录
        """
        try:
            if generated_at is None:
                generated_at = time.time()

            return await self.create(
                group_id=group_id,
                pattern_id=pattern_id,
                generated_text=generated_text,
                context=context,
                quality_score=quality_score,
                user_feedback=user_feedback,
                generated_at=generated_at
            )
        except Exception as e:
            logger.error(f"[ExpressionGenerationResultRepository] 保存生成结果失败: {e}")
            return None

    async def get_by_pattern(
        self,
        pattern_id: int,
        limit: int = 50
    ) -> List[ExpressionGenerationResult]:
        """
        根据模式ID获取生成结果

        Args:
            pattern_id: 表达模式 ID
            limit: 最大返回数量

        Returns:
            List[ExpressionGenerationResult]: 生成结果列表
        """
        try:
            stmt = select(ExpressionGenerationResult).where(
                ExpressionGenerationResult.pattern_id == pattern_id
            ).order_by(desc(ExpressionGenerationResult.generated_at)).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[ExpressionGenerationResultRepository] 获取生成结果失败: {e}")
            return []

    async def get_by_feedback(
        self,
        group_id: str,
        feedback: str,
        limit: int = 50
    ) -> List[ExpressionGenerationResult]:
        """
        根据用户反馈类型获取生成结果

        Args:
            group_id: 群组 ID
            feedback: 反馈类型（positive/negative/neutral）
            limit: 最大返回数量

        Returns:
            List[ExpressionGenerationResult]: 生成结果列表
        """
        try:
            stmt = select(ExpressionGenerationResult).where(
                and_(
                    ExpressionGenerationResult.group_id == group_id,
                    ExpressionGenerationResult.user_feedback == feedback
                )
            ).order_by(desc(ExpressionGenerationResult.generated_at)).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[ExpressionGenerationResultRepository] 根据反馈获取结果失败: {e}")
            return []

    async def update_feedback(
        self,
        result_id: int,
        user_feedback: str,
        quality_score: Optional[float] = None
    ) -> bool:
        """
        更新用户反馈

        Args:
            result_id: 结果 ID
            user_feedback: 用户反馈
            quality_score: 质量评分（可选）

        Returns:
            bool: 是否成功
        """
        try:
            update_data = {"user_feedback": user_feedback}
            if quality_score is not None:
                update_data["quality_score"] = quality_score

            return await self.update(result_id, **update_data)

        except Exception as e:
            logger.error(f"[ExpressionGenerationResultRepository] 更新反馈失败: {e}")
            return False

    async def get_quality_statistics(
        self,
        group_id: str,
        pattern_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        获取质量统计

        Args:
            group_id: 群组 ID
            pattern_id: 表达模式 ID（可选）

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            base_conditions = [ExpressionGenerationResult.group_id == group_id]
            if pattern_id is not None:
                base_conditions.append(ExpressionGenerationResult.pattern_id == pattern_id)

            # 总生成数
            total_stmt = select(func.count()).select_from(ExpressionGenerationResult).where(
                and_(*base_conditions)
            )
            total_result = await self.session.execute(total_stmt)
            total_count = total_result.scalar() or 0

            # 平均质量分数
            avg_quality_stmt = select(func.avg(ExpressionGenerationResult.quality_score)).where(
                and_(*base_conditions, ExpressionGenerationResult.quality_score.isnot(None))
            )
            avg_quality_result = await self.session.execute(avg_quality_stmt)
            avg_quality = avg_quality_result.scalar() or 0

            # 反馈统计
            feedback_stmt = select(
                ExpressionGenerationResult.user_feedback,
                func.count().label('count')
            ).where(
                and_(*base_conditions, ExpressionGenerationResult.user_feedback.isnot(None))
            ).group_by(ExpressionGenerationResult.user_feedback)

            feedback_result = await self.session.execute(feedback_stmt)
            feedback_stats = {row[0]: row[1] for row in feedback_result.fetchall()}

            return {
                "total_generations": total_count,
                "avg_quality_score": round(float(avg_quality), 3),
                "feedback_stats": feedback_stats,
                "positive_count": feedback_stats.get("positive", 0),
                "negative_count": feedback_stats.get("negative", 0),
                "neutral_count": feedback_stats.get("neutral", 0)
            }

        except Exception as e:
            logger.error(f"[ExpressionGenerationResultRepository] 获取质量统计失败: {e}")
            return {
                "total_generations": 0,
                "avg_quality_score": 0.0,
                "feedback_stats": {},
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0
            }


class AdaptiveResponseTemplateRepository(BaseRepository[AdaptiveResponseTemplate]):
    """自适应响应模板 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, AdaptiveResponseTemplate)

    async def save_template(
        self,
        group_id: str,
        template_text: str,
        trigger_patterns: str,
        usage_count: int = 0,
        success_rate: Optional[float] = None,
        last_adapted_at: Optional[float] = None
    ) -> Optional[AdaptiveResponseTemplate]:
        """
        保存自适应响应模板

        Args:
            group_id: 群组 ID
            template_text: 模板文本
            trigger_patterns: 触发模式（JSON字符串）
            usage_count: 使用次数
            success_rate: 成功率
            last_adapted_at: 最后调整时间戳

        Returns:
            Optional[AdaptiveResponseTemplate]: 创建的记录
        """
        try:
            if last_adapted_at is None:
                last_adapted_at = time.time()

            return await self.create(
                group_id=group_id,
                template_text=template_text,
                trigger_patterns=trigger_patterns,
                usage_count=usage_count,
                success_rate=success_rate,
                last_adapted_at=last_adapted_at
            )
        except Exception as e:
            logger.error(f"[AdaptiveResponseTemplateRepository] 保存模板失败: {e}")
            return None

    async def get_all_templates(
        self,
        group_id: str,
        order_by_usage: bool = True,
        limit: int = 100
    ) -> List[AdaptiveResponseTemplate]:
        """
        获取所有模板

        Args:
            group_id: 群组 ID
            order_by_usage: 是否按使用次数排序
            limit: 最大返回数量

        Returns:
            List[AdaptiveResponseTemplate]: 模板列表
        """
        try:
            stmt = select(AdaptiveResponseTemplate).where(
                AdaptiveResponseTemplate.group_id == group_id
            )

            if order_by_usage:
                stmt = stmt.order_by(desc(AdaptiveResponseTemplate.usage_count))
            else:
                stmt = stmt.order_by(desc(AdaptiveResponseTemplate.last_adapted_at))

            stmt = stmt.limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[AdaptiveResponseTemplateRepository] 获取模板列表失败: {e}")
            return []

    async def increment_usage(
        self,
        template_id: int,
        success: Optional[bool] = None
    ) -> bool:
        """
        增加模板使用次数并更新成功率

        Args:
            template_id: 模板 ID
            success: 本次使用是否成功

        Returns:
            bool: 是否成功
        """
        try:
            template = await self.get_by_id(template_id)
            if not template:
                return False

            new_count = template.usage_count + 1
            update_data = {
                "usage_count": new_count,
                "last_adapted_at": time.time()
            }

            # 更新成功率
            if success is not None:
                if template.success_rate is not None:
                    old_success = template.success_rate
                    new_success_rate = (old_success * template.usage_count + (1.0 if success else 0.0)) / new_count
                    update_data["success_rate"] = round(new_success_rate, 3)
                else:
                    update_data["success_rate"] = 1.0 if success else 0.0

            return await self.update(template_id, **update_data)

        except Exception as e:
            logger.error(f"[AdaptiveResponseTemplateRepository] 增加使用次数失败: {e}")
            return False

    async def get_top_performing_templates(
        self,
        group_id: str,
        min_usage: int = 5,
        limit: int = 20
    ) -> List[AdaptiveResponseTemplate]:
        """
        获取表现最好的模板

        Args:
            group_id: 群组 ID
            min_usage: 最小使用次数阈值
            limit: 最大返回数量

        Returns:
            List[AdaptiveResponseTemplate]: 模板列表
        """
        try:
            stmt = select(AdaptiveResponseTemplate).where(
                and_(
                    AdaptiveResponseTemplate.group_id == group_id,
                    AdaptiveResponseTemplate.usage_count >= min_usage,
                    AdaptiveResponseTemplate.success_rate.isnot(None)
                )
            ).order_by(
                desc(AdaptiveResponseTemplate.success_rate),
                desc(AdaptiveResponseTemplate.usage_count)
            ).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[AdaptiveResponseTemplateRepository] 获取高性能模板失败: {e}")
            return []

    async def update_template(
        self,
        template_id: int,
        template_text: Optional[str] = None,
        trigger_patterns: Optional[str] = None
    ) -> bool:
        """
        更新模板内容

        Args:
            template_id: 模板 ID
            template_text: 新的模板文本
            trigger_patterns: 新的触发模式

        Returns:
            bool: 是否成功
        """
        try:
            update_data = {"last_adapted_at": time.time()}
            if template_text is not None:
                update_data["template_text"] = template_text
            if trigger_patterns is not None:
                update_data["trigger_patterns"] = trigger_patterns

            return await self.update(template_id, **update_data)

        except Exception as e:
            logger.error(f"[AdaptiveResponseTemplateRepository] 更新模板失败: {e}")
            return False

    async def get_template_statistics(
        self,
        group_id: str
    ) -> Dict[str, Any]:
        """
        获取模板统计

        Args:
            group_id: 群组 ID

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            # 总模板数
            total_stmt = select(func.count()).select_from(AdaptiveResponseTemplate).where(
                AdaptiveResponseTemplate.group_id == group_id
            )
            total_result = await self.session.execute(total_stmt)
            total_templates = total_result.scalar() or 0

            # 总使用次数
            total_usage_stmt = select(func.sum(AdaptiveResponseTemplate.usage_count)).where(
                AdaptiveResponseTemplate.group_id == group_id
            )
            total_usage_result = await self.session.execute(total_usage_stmt)
            total_usage = total_usage_result.scalar() or 0

            # 平均成功率
            avg_success_stmt = select(func.avg(AdaptiveResponseTemplate.success_rate)).where(
                and_(
                    AdaptiveResponseTemplate.group_id == group_id,
                    AdaptiveResponseTemplate.success_rate.isnot(None)
                )
            )
            avg_success_result = await self.session.execute(avg_success_stmt)
            avg_success_rate = avg_success_result.scalar() or 0

            return {
                "total_templates": total_templates,
                "total_usage_count": int(total_usage),
                "avg_success_rate": round(float(avg_success_rate), 3),
                "avg_usage_per_template": round(float(total_usage) / total_templates, 2) if total_templates > 0 else 0.0
            }

        except Exception as e:
            logger.error(f"[AdaptiveResponseTemplateRepository] 获取统计信息失败: {e}")
            return {
                "total_templates": 0,
                "total_usage_count": 0,
                "avg_success_rate": 0.0,
                "avg_usage_per_template": 0.0
            }
