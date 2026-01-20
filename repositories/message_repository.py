"""
消息与对话相关的 Repository
提供对话上下文、主题聚类、质量指标、相似度缓存的数据访问方法
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from typing import List, Optional, Dict, Any, Tuple
from astrbot.api import logger
import time

from .base_repository import BaseRepository
from ..models.orm import (
    ConversationContext,
    ConversationTopicClustering,
    ConversationQualityMetrics,
    ContextSimilarityCache
)


class ConversationContextRepository(BaseRepository[ConversationContext]):
    """对话上下文 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ConversationContext)

    async def save_context(
        self,
        group_id: str,
        user_id: str,
        context_window: str,
        topic: Optional[str] = None,
        sentiment: Optional[str] = None,
        context_embedding: Optional[bytes] = None,
        last_updated: Optional[float] = None
    ) -> Optional[ConversationContext]:
        """
        保存对话上下文

        Args:
            group_id: 群组 ID
            user_id: 用户 ID
            context_window: 上下文窗口（JSON字符串）
            topic: 当前话题
            sentiment: 情感倾向
            context_embedding: 上下文向量嵌入
            last_updated: 最后更新时间戳

        Returns:
            Optional[ConversationContext]: 创建的上下文记录
        """
        try:
            if last_updated is None:
                last_updated = time.time()

            return await self.create(
                group_id=group_id,
                user_id=user_id,
                context_window=context_window,
                topic=topic,
                sentiment=sentiment,
                context_embedding=context_embedding,
                last_updated=last_updated
            )
        except Exception as e:
            logger.error(f"[ConversationContextRepository] 保存对话上下文失败: {e}")
            return None

    async def get_latest_context(
        self,
        group_id: str,
        user_id: str
    ) -> Optional[ConversationContext]:
        """
        获取最新的对话上下文

        Args:
            group_id: 群组 ID
            user_id: 用户 ID

        Returns:
            Optional[ConversationContext]: 最新上下文记录
        """
        try:
            stmt = select(ConversationContext).where(
                and_(
                    ConversationContext.group_id == group_id,
                    ConversationContext.user_id == user_id
                )
            ).order_by(desc(ConversationContext.last_updated)).limit(1)

            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[ConversationContextRepository] 获取最新上下文失败: {e}")
            return None

    async def get_contexts_by_topic(
        self,
        group_id: str,
        topic: str,
        limit: int = 50
    ) -> List[ConversationContext]:
        """
        根据话题获取上下文列表

        Args:
            group_id: 群组 ID
            topic: 话题
            limit: 最大返回数量

        Returns:
            List[ConversationContext]: 上下文列表
        """
        try:
            stmt = select(ConversationContext).where(
                and_(
                    ConversationContext.group_id == group_id,
                    ConversationContext.topic == topic
                )
            ).order_by(desc(ConversationContext.last_updated)).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[ConversationContextRepository] 根据话题获取上下文失败: {e}")
            return []

    async def update_context(
        self,
        context_id: int,
        context_window: Optional[str] = None,
        topic: Optional[str] = None,
        sentiment: Optional[str] = None,
        context_embedding: Optional[bytes] = None
    ) -> bool:
        """
        更新对话上下文

        Args:
            context_id: 上下文 ID
            context_window: 新的上下文窗口
            topic: 新的话题
            sentiment: 新的情感倾向
            context_embedding: 新的向量嵌入

        Returns:
            bool: 是否成功
        """
        try:
            context = await self.get_by_id(context_id)
            if not context:
                return False

            update_data = {"last_updated": time.time()}
            if context_window is not None:
                update_data["context_window"] = context_window
            if topic is not None:
                update_data["topic"] = topic
            if sentiment is not None:
                update_data["sentiment"] = sentiment
            if context_embedding is not None:
                update_data["context_embedding"] = context_embedding

            return await self.update(context_id, **update_data)

        except Exception as e:
            logger.error(f"[ConversationContextRepository] 更新上下文失败: {e}")
            return False

    async def delete_old_contexts(
        self,
        group_id: str,
        before_timestamp: float
    ) -> int:
        """
        删除指定时间之前的旧上下文

        Args:
            group_id: 群组 ID
            before_timestamp: 时间戳阈值

        Returns:
            int: 删除的记录数
        """
        try:
            stmt = select(ConversationContext).where(
                and_(
                    ConversationContext.group_id == group_id,
                    ConversationContext.last_updated < before_timestamp
                )
            )
            result = await self.session.execute(stmt)
            contexts = result.scalars().all()

            count = 0
            for context in contexts:
                if await self.delete(context.id):
                    count += 1

            return count

        except Exception as e:
            logger.error(f"[ConversationContextRepository] 删除旧上下文失败: {e}")
            return 0


class ConversationTopicClusteringRepository(BaseRepository[ConversationTopicClustering]):
    """对话主题聚类 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ConversationTopicClustering)

    async def save_cluster(
        self,
        group_id: str,
        cluster_id: str,
        topic_keywords: str,
        message_count: int = 0,
        representative_messages: Optional[str] = None,
        cluster_center: Optional[bytes] = None
    ) -> Optional[ConversationTopicClustering]:
        """
        保存主题聚类

        Args:
            group_id: 群组 ID
            cluster_id: 聚类 ID
            topic_keywords: 主题关键词（JSON字符串）
            message_count: 消息数量
            representative_messages: 代表性消息（JSON字符串）
            cluster_center: 聚类中心向量

        Returns:
            Optional[ConversationTopicClustering]: 创建的聚类记录
        """
        try:
            return await self.create(
                group_id=group_id,
                cluster_id=cluster_id,
                topic_keywords=topic_keywords,
                message_count=message_count,
                representative_messages=representative_messages,
                cluster_center=cluster_center
            )
        except Exception as e:
            logger.error(f"[ConversationTopicClusteringRepository] 保存主题聚类失败: {e}")
            return None

    async def get_cluster_by_id(
        self,
        group_id: str,
        cluster_id: str
    ) -> Optional[ConversationTopicClustering]:
        """
        根据聚类 ID 获取聚类

        Args:
            group_id: 群组 ID
            cluster_id: 聚类 ID

        Returns:
            Optional[ConversationTopicClustering]: 聚类记录
        """
        try:
            stmt = select(ConversationTopicClustering).where(
                and_(
                    ConversationTopicClustering.group_id == group_id,
                    ConversationTopicClustering.cluster_id == cluster_id
                )
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[ConversationTopicClusteringRepository] 获取聚类失败: {e}")
            return None

    async def get_all_clusters(
        self,
        group_id: str,
        order_by_message_count: bool = True,
        limit: int = 100
    ) -> List[ConversationTopicClustering]:
        """
        获取所有主题聚类

        Args:
            group_id: 群组 ID
            order_by_message_count: 是否按消息数量排序
            limit: 最大返回数量

        Returns:
            List[ConversationTopicClustering]: 聚类列表
        """
        try:
            stmt = select(ConversationTopicClustering).where(
                ConversationTopicClustering.group_id == group_id
            )

            if order_by_message_count:
                stmt = stmt.order_by(desc(ConversationTopicClustering.message_count))

            stmt = stmt.limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[ConversationTopicClusteringRepository] 获取聚类列表失败: {e}")
            return []

    async def update_cluster(
        self,
        group_id: str,
        cluster_id: str,
        topic_keywords: Optional[str] = None,
        message_count: Optional[int] = None,
        representative_messages: Optional[str] = None,
        cluster_center: Optional[bytes] = None
    ) -> bool:
        """
        更新主题聚类

        Args:
            group_id: 群组 ID
            cluster_id: 聚类 ID
            topic_keywords: 新的主题关键词
            message_count: 新的消息数量
            representative_messages: 新的代表性消息
            cluster_center: 新的聚类中心向量

        Returns:
            bool: 是否成功
        """
        try:
            cluster = await self.get_cluster_by_id(group_id, cluster_id)
            if not cluster:
                return False

            update_data = {}
            if topic_keywords is not None:
                update_data["topic_keywords"] = topic_keywords
            if message_count is not None:
                update_data["message_count"] = message_count
            if representative_messages is not None:
                update_data["representative_messages"] = representative_messages
            if cluster_center is not None:
                update_data["cluster_center"] = cluster_center

            if update_data:
                return await self.update(cluster.id, **update_data)
            return True

        except Exception as e:
            logger.error(f"[ConversationTopicClusteringRepository] 更新聚类失败: {e}")
            return False

    async def increment_message_count(
        self,
        group_id: str,
        cluster_id: str,
        increment: int = 1
    ) -> bool:
        """
        增加聚类的消息计数

        Args:
            group_id: 群组 ID
            cluster_id: 聚类 ID
            increment: 增量

        Returns:
            bool: 是否成功
        """
        try:
            cluster = await self.get_cluster_by_id(group_id, cluster_id)
            if not cluster:
                return False

            new_count = cluster.message_count + increment
            return await self.update(cluster.id, message_count=new_count)

        except Exception as e:
            logger.error(f"[ConversationTopicClusteringRepository] 增加消息计数失败: {e}")
            return False

    async def get_cluster_statistics(
        self,
        group_id: str
    ) -> Dict[str, Any]:
        """
        获取聚类统计信息

        Args:
            group_id: 群组 ID

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            # 总聚类数
            total_stmt = select(func.count()).select_from(ConversationTopicClustering).where(
                ConversationTopicClustering.group_id == group_id
            )
            total_result = await self.session.execute(total_stmt)
            total_clusters = total_result.scalar() or 0

            # 总消息数
            total_msg_stmt = select(func.sum(ConversationTopicClustering.message_count)).where(
                ConversationTopicClustering.group_id == group_id
            )
            total_msg_result = await self.session.execute(total_msg_stmt)
            total_messages = total_msg_result.scalar() or 0

            # 平均每个聚类的消息数
            avg_msg_stmt = select(func.avg(ConversationTopicClustering.message_count)).where(
                ConversationTopicClustering.group_id == group_id
            )
            avg_msg_result = await self.session.execute(avg_msg_stmt)
            avg_messages = avg_msg_result.scalar() or 0

            return {
                "total_clusters": total_clusters,
                "total_messages": int(total_messages),
                "avg_messages_per_cluster": round(float(avg_messages), 2)
            }

        except Exception as e:
            logger.error(f"[ConversationTopicClusteringRepository] 获取统计信息失败: {e}")
            return {
                "total_clusters": 0,
                "total_messages": 0,
                "avg_messages_per_cluster": 0.0
            }


class ConversationQualityMetricsRepository(BaseRepository[ConversationQualityMetrics]):
    """对话质量指标 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ConversationQualityMetrics)

    async def save_quality_metrics(
        self,
        group_id: str,
        message_id: int,
        coherence_score: Optional[float] = None,
        relevance_score: Optional[float] = None,
        engagement_score: Optional[float] = None,
        sentiment_alignment: Optional[float] = None,
        calculated_at: Optional[float] = None
    ) -> Optional[ConversationQualityMetrics]:
        """
        保存对话质量指标

        Args:
            group_id: 群组 ID
            message_id: 消息 ID（外键到 bot_messages）
            coherence_score: 连贯性分数
            relevance_score: 相关性分数
            engagement_score: 互动度分数
            sentiment_alignment: 情感一致性分数
            calculated_at: 计算时间戳

        Returns:
            Optional[ConversationQualityMetrics]: 创建的质量指标记录
        """
        try:
            if calculated_at is None:
                calculated_at = time.time()

            return await self.create(
                group_id=group_id,
                message_id=message_id,
                coherence_score=coherence_score,
                relevance_score=relevance_score,
                engagement_score=engagement_score,
                sentiment_alignment=sentiment_alignment,
                calculated_at=calculated_at
            )
        except Exception as e:
            logger.error(f"[ConversationQualityMetricsRepository] 保存质量指标失败: {e}")
            return None

    async def get_metrics_by_message(
        self,
        message_id: int
    ) -> Optional[ConversationQualityMetrics]:
        """
        根据消息 ID 获取质量指标

        Args:
            message_id: 消息 ID

        Returns:
            Optional[ConversationQualityMetrics]: 质量指标记录
        """
        try:
            stmt = select(ConversationQualityMetrics).where(
                ConversationQualityMetrics.message_id == message_id
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[ConversationQualityMetricsRepository] 获取质量指标失败: {e}")
            return None

    async def get_recent_metrics(
        self,
        group_id: str,
        limit: int = 50
    ) -> List[ConversationQualityMetrics]:
        """
        获取最近的质量指标

        Args:
            group_id: 群组 ID
            limit: 最大返回数量

        Returns:
            List[ConversationQualityMetrics]: 质量指标列表
        """
        try:
            stmt = select(ConversationQualityMetrics).where(
                ConversationQualityMetrics.group_id == group_id
            ).order_by(desc(ConversationQualityMetrics.calculated_at)).limit(limit)

            result = await self.session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"[ConversationQualityMetricsRepository] 获取最近质量指标失败: {e}")
            return []

    async def get_average_scores(
        self,
        group_id: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> Dict[str, float]:
        """
        获取平均质量分数

        Args:
            group_id: 群组 ID
            start_time: 开始时间戳（可选）
            end_time: 结束时间戳（可选）

        Returns:
            Dict[str, float]: 各指标的平均分数
        """
        try:
            stmt = select(
                func.avg(ConversationQualityMetrics.coherence_score).label('avg_coherence'),
                func.avg(ConversationQualityMetrics.relevance_score).label('avg_relevance'),
                func.avg(ConversationQualityMetrics.engagement_score).label('avg_engagement'),
                func.avg(ConversationQualityMetrics.sentiment_alignment).label('avg_sentiment')
            ).where(ConversationQualityMetrics.group_id == group_id)

            if start_time is not None:
                stmt = stmt.where(ConversationQualityMetrics.calculated_at >= start_time)
            if end_time is not None:
                stmt = stmt.where(ConversationQualityMetrics.calculated_at <= end_time)

            result = await self.session.execute(stmt)
            row = result.fetchone()

            if row:
                return {
                    "avg_coherence_score": round(float(row.avg_coherence or 0), 3),
                    "avg_relevance_score": round(float(row.avg_relevance or 0), 3),
                    "avg_engagement_score": round(float(row.avg_engagement or 0), 3),
                    "avg_sentiment_alignment": round(float(row.avg_sentiment or 0), 3)
                }
            return {
                "avg_coherence_score": 0.0,
                "avg_relevance_score": 0.0,
                "avg_engagement_score": 0.0,
                "avg_sentiment_alignment": 0.0
            }

        except Exception as e:
            logger.error(f"[ConversationQualityMetricsRepository] 获取平均分数失败: {e}")
            return {
                "avg_coherence_score": 0.0,
                "avg_relevance_score": 0.0,
                "avg_engagement_score": 0.0,
                "avg_sentiment_alignment": 0.0
            }

    async def get_quality_trend(
        self,
        group_id: str,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        获取质量趋势（按天统计）

        Args:
            group_id: 群组 ID
            days: 统计天数

        Returns:
            List[Dict[str, Any]]: 每天的平均质量分数列表
        """
        try:
            cutoff_time = time.time() - (days * 24 * 3600)

            stmt = select(ConversationQualityMetrics).where(
                and_(
                    ConversationQualityMetrics.group_id == group_id,
                    ConversationQualityMetrics.calculated_at >= cutoff_time
                )
            ).order_by(ConversationQualityMetrics.calculated_at)

            result = await self.session.execute(stmt)
            metrics = result.scalars().all()

            # 按天分组统计
            daily_metrics: Dict[str, List[ConversationQualityMetrics]] = {}
            for metric in metrics:
                day_key = time.strftime('%Y-%m-%d', time.localtime(metric.calculated_at))
                if day_key not in daily_metrics:
                    daily_metrics[day_key] = []
                daily_metrics[day_key].append(metric)

            # 计算每天的平均分数
            trend = []
            for day, day_metrics in sorted(daily_metrics.items()):
                avg_coherence = sum(m.coherence_score or 0 for m in day_metrics) / len(day_metrics)
                avg_relevance = sum(m.relevance_score or 0 for m in day_metrics) / len(day_metrics)
                avg_engagement = sum(m.engagement_score or 0 for m in day_metrics) / len(day_metrics)
                avg_sentiment = sum(m.sentiment_alignment or 0 for m in day_metrics) / len(day_metrics)

                trend.append({
                    "date": day,
                    "count": len(day_metrics),
                    "avg_coherence_score": round(avg_coherence, 3),
                    "avg_relevance_score": round(avg_relevance, 3),
                    "avg_engagement_score": round(avg_engagement, 3),
                    "avg_sentiment_alignment": round(avg_sentiment, 3)
                })

            return trend

        except Exception as e:
            logger.error(f"[ConversationQualityMetricsRepository] 获取质量趋势失败: {e}")
            return []


class ContextSimilarityCacheRepository(BaseRepository[ContextSimilarityCache]):
    """上下文相似度缓存 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ContextSimilarityCache)

    async def save_similarity(
        self,
        context_hash_1: str,
        context_hash_2: str,
        similarity_score: float,
        calculation_method: Optional[str] = None,
        cached_at: Optional[float] = None
    ) -> Optional[ContextSimilarityCache]:
        """
        保存相似度缓存

        Args:
            context_hash_1: 上下文1的哈希值
            context_hash_2: 上下文2的哈希值
            similarity_score: 相似度分数
            calculation_method: 计算方法
            cached_at: 缓存时间戳

        Returns:
            Optional[ContextSimilarityCache]: 创建的缓存记录
        """
        try:
            if cached_at is None:
                cached_at = time.time()

            return await self.create(
                context_hash_1=context_hash_1,
                context_hash_2=context_hash_2,
                similarity_score=similarity_score,
                calculation_method=calculation_method,
                cached_at=cached_at
            )
        except Exception as e:
            logger.error(f"[ContextSimilarityCacheRepository] 保存相似度缓存失败: {e}")
            return None

    async def get_similarity(
        self,
        context_hash_1: str,
        context_hash_2: str
    ) -> Optional[ContextSimilarityCache]:
        """
        获取相似度缓存（双向查找）

        Args:
            context_hash_1: 上下文1的哈希值
            context_hash_2: 上下文2的哈希值

        Returns:
            Optional[ContextSimilarityCache]: 缓存记录
        """
        try:
            # 尝试正向查找
            stmt = select(ContextSimilarityCache).where(
                and_(
                    ContextSimilarityCache.context_hash_1 == context_hash_1,
                    ContextSimilarityCache.context_hash_2 == context_hash_2
                )
            )
            result = await self.session.execute(stmt)
            cache = result.scalar_one_or_none()

            if cache:
                return cache

            # 尝试反向查找（相似度是对称的）
            stmt = select(ContextSimilarityCache).where(
                and_(
                    ContextSimilarityCache.context_hash_1 == context_hash_2,
                    ContextSimilarityCache.context_hash_2 == context_hash_1
                )
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"[ContextSimilarityCacheRepository] 获取相似度缓存失败: {e}")
            return None

    async def delete_old_cache(
        self,
        before_timestamp: float
    ) -> int:
        """
        删除指定时间之前的旧缓存

        Args:
            before_timestamp: 时间戳阈值

        Returns:
            int: 删除的记录数
        """
        try:
            stmt = select(ContextSimilarityCache).where(
                ContextSimilarityCache.cached_at < before_timestamp
            )
            result = await self.session.execute(stmt)
            caches = result.scalars().all()

            count = 0
            for cache in caches:
                if await self.delete(cache.id):
                    count += 1

            return count

        except Exception as e:
            logger.error(f"[ContextSimilarityCacheRepository] 删除旧缓存失败: {e}")
            return 0

    async def get_cache_statistics(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            Dict[str, Any]: 统计数据
        """
        try:
            # 总缓存数
            total_stmt = select(func.count()).select_from(ContextSimilarityCache)
            total_result = await self.session.execute(total_stmt)
            total_cache = total_result.scalar() or 0

            # 平均相似度
            avg_score_stmt = select(func.avg(ContextSimilarityCache.similarity_score))
            avg_score_result = await self.session.execute(avg_score_stmt)
            avg_score = avg_score_result.scalar() or 0

            # 最早和最晚缓存时间
            time_range_stmt = select(
                func.min(ContextSimilarityCache.cached_at).label('earliest'),
                func.max(ContextSimilarityCache.cached_at).label('latest')
            )
            time_range_result = await self.session.execute(time_range_stmt)
            time_range = time_range_result.fetchone()

            return {
                "total_cache_entries": total_cache,
                "avg_similarity_score": round(float(avg_score), 3),
                "earliest_cache_time": time_range[0] if time_range else None,
                "latest_cache_time": time_range[1] if time_range else None
            }

        except Exception as e:
            logger.error(f"[ContextSimilarityCacheRepository] 获取缓存统计失败: {e}")
            return {
                "total_cache_entries": 0,
                "avg_similarity_score": 0.0,
                "earliest_cache_time": None,
                "latest_cache_time": None
            }

    async def get_similar_contexts(
        self,
        context_hash: str,
        min_similarity: float = 0.7,
        limit: int = 10
    ) -> List[Tuple[str, float]]:
        """
        获取与指定上下文相似的上下文列表

        Args:
            context_hash: 上下文哈希值
            min_similarity: 最小相似度阈值
            limit: 最大返回数量

        Returns:
            List[Tuple[str, float]]: (上下文哈希, 相似度分数)列表
        """
        try:
            # 查找 context_hash 作为 hash_1 的记录
            stmt1 = select(
                ContextSimilarityCache.context_hash_2,
                ContextSimilarityCache.similarity_score
            ).where(
                and_(
                    ContextSimilarityCache.context_hash_1 == context_hash,
                    ContextSimilarityCache.similarity_score >= min_similarity
                )
            ).order_by(desc(ContextSimilarityCache.similarity_score)).limit(limit)

            result1 = await self.session.execute(stmt1)
            matches1 = [(row[0], row[1]) for row in result1.fetchall()]

            # 查找 context_hash 作为 hash_2 的记录
            stmt2 = select(
                ContextSimilarityCache.context_hash_1,
                ContextSimilarityCache.similarity_score
            ).where(
                and_(
                    ContextSimilarityCache.context_hash_2 == context_hash,
                    ContextSimilarityCache.similarity_score >= min_similarity
                )
            ).order_by(desc(ContextSimilarityCache.similarity_score)).limit(limit)

            result2 = await self.session.execute(stmt2)
            matches2 = [(row[0], row[1]) for row in result2.fetchall()]

            # 合并并按相似度排序
            all_matches = matches1 + matches2
            all_matches.sort(key=lambda x: x[1], reverse=True)

            return all_matches[:limit]

        except Exception as e:
            logger.error(f"[ContextSimilarityCacheRepository] 获取相似上下文失败: {e}")
            return []
