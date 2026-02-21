"""
数据分析与可视化服务 - 提供学习过程数据分析和用户行为分析

NOTE: 图表渲染由前端 ECharts 完成，本模块只返回 JSON 数据。
"""
import json
import asyncio
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict

from astrbot.api import logger

from ...config import PluginConfig

from ...core.patterns import AsyncServiceBase

from ...core.interfaces import IDataStorage


def _mean(values: list) -> float:
    """Simple arithmetic mean without numpy."""
    if not values:
        return 0.0
    return sum(values) / len(values)


class DataAnalyticsService(AsyncServiceBase):
    """数据分析与可视化服务"""

    def __init__(self, config: PluginConfig, database_manager: IDataStorage):
        super().__init__("data_analytics")
        self.config = config
        self.db_manager = database_manager
        self.analytics_cache = {}
        self.cache_timeout = 300  # 5分钟缓存

    async def _do_start(self) -> bool:
        """启动分析服务"""
        try:
            self._logger.info("数据分析服务启动成功")
            return True
        except Exception as e:
            self._logger.error(f"数据分析服务启动失败: {e}")
            return False

    async def _do_stop(self) -> bool:
        """停止分析服务"""
        self.analytics_cache.clear()
        return True

    async def generate_learning_trajectory_chart(self, group_id: str, days: int = 30) -> Dict[str, Any]:
        """生成学习过程轨迹数据（返回纯 JSON，由前端 ECharts 渲染）"""
        cache_key = f"learning_trajectory_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]

        try:
            persona_updates = await self.db_manager.get_persona_update_history(group_id, days)

            if not persona_updates:
                return {"chart": None, "message": "暂无人格更新数据"}

            dates = []
            creativity_scores = []
            formality_scores = []
            emotional_scores = []
            vocabulary_richness = []

            for update in persona_updates:
                dates.append(update.get('timestamp', time.time()))
                style_data = update.get('style_profile', {})
                creativity_scores.append(style_data.get('creativity', 0.5))
                formality_scores.append(style_data.get('formality', 0.5))
                emotional_scores.append(style_data.get('emotional_intensity', 0.5))
                vocabulary_richness.append(style_data.get('vocabulary_richness', 0.5))

            formatted_dates = [datetime.fromtimestamp(ts).strftime('%m-%d') for ts in dates]

            result = {
                "chart": {
                    "dates": formatted_dates,
                    "series": {
                        "creativity": creativity_scores,
                        "formality": formality_scores,
                        "emotional": emotional_scores,
                        "vocabulary": vocabulary_richness,
                    },
                },
                "summary": {
                    "total_updates": len(persona_updates),
                    "avg_creativity": _mean(creativity_scores),
                    "avg_formality": _mean(formality_scores),
                    "avg_emotional": _mean(emotional_scores),
                    "avg_vocabulary": _mean(vocabulary_richness),
                },
            }

            self.analytics_cache[cache_key] = result
            return result

        except Exception as e:
            self._logger.error(f"生成学习轨迹数据失败: {e}")
            return {"chart": None, "error": str(e)}

    async def generate_learning_quality_curve(self, group_id: str, days: int = 30) -> Dict[str, Any]:
        """生成学习质量曲线数据"""
        cache_key = f"quality_curve_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]

        try:
            learning_batches = await self.db_manager.get_learning_batch_history(group_id, days)

            if not learning_batches:
                return {"chart": None, "message": "暂无学习批次数据"}

            dates = []
            quality_scores = []
            message_counts = []
            processing_times = []

            for batch in learning_batches:
                dates.append(batch.get('start_time', time.time()))
                quality_scores.append(batch.get('quality_score', 0.5))
                message_counts.append(batch.get('processed_messages', 0))
                processing_times.append(batch.get('processing_time', 0))

            formatted_dates = [datetime.fromtimestamp(ts).strftime('%m-%d %H:%M') for ts in dates]

            result = {
                "chart": {
                    "dates": formatted_dates,
                    "quality_scores": quality_scores,
                    "message_counts": message_counts,
                },
                "summary": {
                    "total_batches": len(learning_batches),
                    "avg_quality": _mean(quality_scores),
                    "total_messages": sum(message_counts),
                    "avg_processing_time": _mean(processing_times),
                },
            }

            self.analytics_cache[cache_key] = result
            return result

        except Exception as e:
            self._logger.error(f"生成学习质量曲线失败: {e}")
            return {"chart": None, "error": str(e)}

    async def generate_user_activity_heatmap(self, group_id: str, days: int = 7) -> Dict[str, Any]:
        """生成用户活跃度热力图数据"""
        cache_key = f"activity_heatmap_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]

        try:
            messages = await self.db_manager.get_messages_by_timerange(
                group_id,
                datetime.now() - timedelta(days=days),
                datetime.now()
            )

            if not messages:
                return {"chart": None, "message": "暂无消息数据"}

            # 7天 x 24小时 活跃度矩阵
            activity_matrix = [[0] * 24 for _ in range(7)]

            for msg in messages:
                timestamp = msg.timestamp
                dt = datetime.fromtimestamp(timestamp)
                weekday = dt.weekday()
                hour = dt.hour
                activity_matrix[weekday][hour] += 1

            # 计算峰值活跃时间
            max_val = 0
            max_day_idx = 0
            max_hour = 0
            for d in range(7):
                for h in range(24):
                    if activity_matrix[d][h] > max_val:
                        max_val = activity_matrix[d][h]
                        max_day_idx = d
                        max_hour = h

            day_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

            result = {
                "chart": {
                    "matrix": activity_matrix,
                    "hours": [f"{i:02d}:00" for i in range(24)],
                    "days": day_names,
                },
                "summary": {
                    "total_messages": len(messages),
                    "peak_activity_day": day_names[max_day_idx],
                    "peak_activity_hour": f"{max_hour:02d}:00",
                    "avg_messages_per_hour": len(messages) / (days * 24),
                },
            }

            self.analytics_cache[cache_key] = result
            return result

        except Exception as e:
            self._logger.error(f"生成活跃度热力图失败: {e}")
            return {"chart": None, "error": str(e)}

    async def generate_topic_trend_analysis(self, group_id: str, days: int = 30) -> Dict[str, Any]:
        """生成话题趋势分析数据"""
        cache_key = f"topic_trends_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]

        try:
            messages = await self.db_manager.get_messages_by_timerange(
                group_id,
                datetime.now() - timedelta(days=days),
                datetime.now()
            )

            if not messages:
                return {"chart": None, "message": "暂无消息数据"}

            import jieba

            topic_counts = defaultdict(int)
            daily_topics = defaultdict(lambda: defaultdict(int))

            stopwords = {'的', '了', '是', '在', '我', '你', '他', '她', '它', '这', '那', '和', '与', '及'}

            for msg in messages:
                content = msg.message or ''
                timestamp = msg.timestamp
                date_key = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

                words = jieba.lcut(content)
                for word in words:
                    if len(word) > 1 and word not in stopwords:
                        topic_counts[word] += 1
                        daily_topics[date_key][word] += 1

            top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]

            dates = sorted(daily_topics.keys())
            series = {}
            for topic, _ in top_topics[:5]:
                series[topic] = [daily_topics[date].get(topic, 0) for date in dates]

            result = {
                "chart": {
                    "dates": dates,
                    "series": series,
                },
                "top_topics": top_topics[:10],
                "summary": {
                    "total_topics": len(topic_counts),
                    "analysis_days": days,
                    "most_discussed": top_topics[0][0] if top_topics else "无",
                },
            }

            self.analytics_cache[cache_key] = result
            return result

        except Exception as e:
            self._logger.error(f"生成话题趋势分析失败: {e}")
            return {"chart": None, "error": str(e)}

    async def generate_social_network_graph(self, group_id: str, days: int = 30) -> Dict[str, Any]:
        """生成社交关系网络图数据"""
        cache_key = f"social_network_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]

        try:
            relationships = await self.db_manager.get_social_relationships(group_id, days)

            if not relationships:
                return {"chart": None, "message": "暂无社交关系数据"}

            nodes = []
            edges = []
            user_interactions = defaultdict(int)

            for rel in relationships:
                user1 = rel.get('user1_id')
                user2 = rel.get('user2_id')
                interaction_count = rel.get('interaction_count', 0)

                user_interactions[user1] += interaction_count
                user_interactions[user2] += interaction_count

                edges.append({
                    'from': user1,
                    'to': user2,
                    'weight': interaction_count,
                })

            for user_id, interaction_count in user_interactions.items():
                nodes.append({
                    'id': user_id,
                    'label': f"用户{user_id[-4:]}",
                    'value': interaction_count,
                    'title': f"交互次数: {interaction_count}",
                })

            result = {
                "network_data": {
                    "nodes": nodes,
                    "edges": edges,
                },
                "summary": {
                    "total_users": len(nodes),
                    "total_relationships": len(edges),
                    "most_active_user": max(user_interactions.items(), key=lambda x: x[1])[0] if user_interactions else "无",
                    "avg_interactions": _mean(list(user_interactions.values())),
                },
            }

            self.analytics_cache[cache_key] = result
            return result

        except Exception as e:
            self._logger.error(f"生成社交网络图失败: {e}")
            return {"network_data": None, "error": str(e)}

    async def get_comprehensive_analytics(self, group_id: str) -> Dict[str, Any]:
        """获取综合分析报告"""
        try:
            tasks = [
                self.generate_learning_trajectory_chart(group_id, 30),
                self.generate_learning_quality_curve(group_id, 30),
                self.generate_user_activity_heatmap(group_id, 7),
                self.generate_topic_trend_analysis(group_id, 30),
                self.generate_social_network_graph(group_id, 30),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            return {
                "learning_trajectory": results[0] if not isinstance(results[0], Exception) else None,
                "quality_curve": results[1] if not isinstance(results[1], Exception) else None,
                "activity_heatmap": results[2] if not isinstance(results[2], Exception) else None,
                "topic_trends": results[3] if not isinstance(results[3], Exception) else None,
                "social_network": results[4] if not isinstance(results[4], Exception) else None,
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            self._logger.error(f"生成综合分析报告失败: {e}")
            return {"error": str(e)}

    async def analyze_user_behavior_patterns(self, group_id: str, days: int = 30) -> Dict[str, Any]:
        """分析用户行为模式"""
        cache_key = f"user_behavior_patterns_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]

        try:
            messages = await self.db_manager.get_messages_by_timerange(
                group_id,
                datetime.now() - timedelta(days=days),
                datetime.now()
            )

            if not messages:
                return {
                    "user_patterns": {},
                    "common_topics": [],
                    "dominant_emotion": "中性",
                    "recommendations": "暂无足够数据进行分析",
                }

            import jieba

            user_patterns = {}
            topic_counts = defaultdict(int)
            emotion_indicators = {
                "positive": 0, "negative": 0, "neutral": 0,
                "excited": 0, "calm": 0, "active": 0,
            }

            user_message_counts = defaultdict(int)
            user_message_lengths = defaultdict(list)

            stopwords = {'的', '了', '是', '在', '我', '你', '他', '她', '它', '这', '那', '和', '与', '及'}

            for msg in messages:
                sender_id = msg.sender_id or ''
                content = msg.message or ''

                user_message_counts[sender_id] += 1
                user_message_lengths[sender_id].append(len(content))

                words = jieba.lcut(content)
                for word in words:
                    if len(word) > 1 and word not in stopwords:
                        topic_counts[word] += 1

                positive_words = ['好', '棒', '赞', '喜欢', '开心', '高兴', '哈哈', '笑', '爱']
                negative_words = ['不好', '差', '糟', '讨厌', '难过', '生气', '烦', '恨']
                excited_words = ['太', '超', '非常', '特别', '极', '！', '!']

                for word in positive_words:
                    if word in content:
                        emotion_indicators["positive"] += 1
                        break

                for word in negative_words:
                    if word in content:
                        emotion_indicators["negative"] += 1
                        break

                for word in excited_words:
                    if word in content:
                        emotion_indicators["excited"] += 1
                        break

                if len(content) > 20:
                    emotion_indicators["active"] += 1
                elif len(content) < 5:
                    emotion_indicators["calm"] += 1
                else:
                    emotion_indicators["neutral"] += 1

            for user_id, msg_count in user_message_counts.items():
                avg_length = _mean(user_message_lengths[user_id])
                user_patterns[user_id] = {
                    "message_count": msg_count,
                    "avg_message_length": round(avg_length, 2),
                    "activity_level": "高" if msg_count > len(messages) * 0.3 else "中" if msg_count > len(messages) * 0.1 else "低",
                    "communication_style": "详细" if avg_length > 50 else "简洁" if avg_length < 15 else "适中",
                }

            common_topics = [topic for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]]

            dominant_emotion = max(emotion_indicators.items(), key=lambda x: x[1])[0]
            emotion_map = {
                "positive": "积极",
                "negative": "消极",
                "neutral": "中性",
                "excited": "兴奋",
                "calm": "平静",
                "active": "活跃",
            }
            dominant_emotion_zh = emotion_map.get(dominant_emotion, "中性")

            recommendations = self._generate_behavior_recommendations(user_patterns, emotion_indicators, len(messages))

            result = {
                "user_patterns": user_patterns,
                "common_topics": common_topics,
                "dominant_emotion": dominant_emotion_zh,
                "recommendations": recommendations,
                "total_messages": len(messages),
                "active_users": len(user_patterns),
                "emotion_distribution": emotion_indicators,
            }

            self.analytics_cache[cache_key] = result
            return result

        except Exception as e:
            self._logger.error(f"分析用户行为模式失败: {e}")
            return {
                "user_patterns": {},
                "common_topics": [],
                "dominant_emotion": "中性",
                "recommendations": "分析过程中出现错误",
                "total_messages": 0,
                "active_users": 0,
            }

    def _generate_behavior_recommendations(self, user_patterns: Dict, emotion_indicators: Dict, total_messages: int) -> str:
        """基于行为模式生成建议"""
        try:
            recommendations = []

            active_users = sum(1 for pattern in user_patterns.values() if pattern["activity_level"] == "高")
            if active_users > len(user_patterns) * 0.5:
                recommendations.append("群聊活跃度很高，可以考虑更频繁的学习更新")
            elif active_users < len(user_patterns) * 0.2:
                recommendations.append("群聊活跃度较低，建议优化互动策略")

            positive_ratio = emotion_indicators.get("positive", 0) / max(total_messages, 1)
            if positive_ratio > 0.6:
                recommendations.append("群聊氛围积极，可以保持当前的交流风格")
            elif positive_ratio < 0.3:
                recommendations.append("群聊氛围需要改善，建议增加正面互动")

            detailed_users = sum(1 for pattern in user_patterns.values() if pattern["communication_style"] == "详细")
            if detailed_users > len(user_patterns) * 0.5:
                recommendations.append("用户偏好详细交流，可以提供更丰富的回复内容")
            else:
                recommendations.append("用户偏好简洁交流，建议保持回复简明扼要")

            return "；".join(recommendations) if recommendations else "继续保持当前学习模式"

        except Exception as e:
            self._logger.error(f"生成行为建议失败: {e}")
            return "继续保持当前学习模式"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self.analytics_cache:
            return False

        cache_time = getattr(self.analytics_cache[cache_key], '_cache_time', 0)
        return time.time() - cache_time < self.cache_timeout

    def _set_cache_time(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """设置缓存时间"""
        data['_cache_time'] = time.time()
        return data