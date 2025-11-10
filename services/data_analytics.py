"""
数据分析与可视化服务 - 提供学习过程可视化和用户行为分析
"""
import os
import json
import asyncio
import time
import jieba
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

import plotly.graph_objects as go
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder
import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud

from astrbot.api import logger

from ..config import PluginConfig

from ..core.patterns import AsyncServiceBase

from ..core.interfaces import IDataStorage

from ..core.compatibility_extensions import create_compatibility_extensions


class DataAnalyticsService(AsyncServiceBase):
    """数据分析与可视化服务"""
    
    def __init__(self, config: PluginConfig, database_manager: IDataStorage):
        super().__init__("data_analytics")
        self.config = config
        self.db_manager = database_manager
        self.analytics_cache = {}
        self.cache_timeout = 300  # 5分钟缓存
        
        # 创建兼容性扩展
        extensions = create_compatibility_extensions(config, None, database_manager, None)
        self.db_ext = extensions['db_manager']
        
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
        """生成学习过程轨迹图表 - 人格演变轨迹"""
        cache_key = f"learning_trajectory_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]
        
        try:
            # 获取人格更新历史数据
            persona_updates = await self.db_ext.get_persona_update_history(group_id, days)
            
            if not persona_updates:
                return {"chart": None, "message": "暂无人格更新数据"}
            
            # 处理数据
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
            
            # 转换时间戳为日期
            formatted_dates = [datetime.fromtimestamp(ts).strftime('%m-%d') for ts in dates]
            
            # 创建多线图表
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=formatted_dates,
                y=creativity_scores,
                mode='lines+markers',
                name='创造性',
                line=dict(color='#FF6B6B', width=2)
            ))
            
            fig.add_trace(go.Scatter(
                x=formatted_dates,
                y=formality_scores,
                mode='lines+markers',
                name='正式程度',
                line=dict(color='#4ECDC4', width=2)
            ))
            
            fig.add_trace(go.Scatter(
                x=formatted_dates,
                y=emotional_scores,
                mode='lines+markers',
                name='情感强度',
                line=dict(color='#45B7D1', width=2)
            ))
            
            fig.add_trace(go.Scatter(
                x=formatted_dates,
                y=vocabulary_richness,
                mode='lines+markers',
                name='词汇丰富度',
                line=dict(color='#FFA07A', width=2)
            ))
            
            fig.update_layout(
                title=f'人格演变轨迹 - 群组 {group_id}',
                xaxis_title='日期',
                yaxis_title='指标值 (0-1)',
                hovermode='x unified',
                template='plotly_white',
                height=400
            )
            
            chart_json = json.dumps(fig, cls=PlotlyJSONEncoder)
            
            result = {
                "chart": chart_json,
                "summary": {
                    "total_updates": len(persona_updates),
                    "avg_creativity": np.mean(creativity_scores),
                    "avg_formality": np.mean(formality_scores),
                    "avg_emotional": np.mean(emotional_scores),
                    "avg_vocabulary": np.mean(vocabulary_richness)
                }
            }
            
            self.analytics_cache[cache_key] = result
            return result
            
        except Exception as e:
            self._logger.error(f"生成学习轨迹图表失败: {e}")
            return {"chart": None, "error": str(e)}
    
    async def generate_learning_quality_curve(self, group_id: str, days: int = 30) -> Dict[str, Any]:
        """生成学习质量曲线图"""
        cache_key = f"quality_curve_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]
        
        try:
            # 获取学习批次数据
            learning_batches = await self.db_ext.get_learning_batch_history(group_id, days)
            
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
            
            # 创建双轴图表
            fig = go.Figure()
            
            # 质量得分线
            fig.add_trace(go.Scatter(
                x=formatted_dates,
                y=quality_scores,
                mode='lines+markers',
                name='学习质量',
                line=dict(color='#FF6B6B', width=3),
                yaxis='y'
            ))
            
            # 消息数量柱状图
            fig.add_trace(go.Bar(
                x=formatted_dates,
                y=message_counts,
                name='处理消息数',
                opacity=0.6,
                marker_color='#4ECDC4',
                yaxis='y2'
            ))
            
            fig.update_layout(
                title=f'学习质量曲线 - 群组 {group_id}',
                xaxis_title='时间',
                yaxis=dict(
                    title='学习质量 (0-1)',
                    side='left',
                    range=[0, 1]
                ),
                yaxis2=dict(
                    title='消息数量',
                    side='right',
                    overlaying='y'
                ),
                template='plotly_white',
                height=400
            )
            
            chart_json = json.dumps(fig, cls=PlotlyJSONEncoder)
            
            result = {
                "chart": chart_json,
                "summary": {
                    "total_batches": len(learning_batches),
                    "avg_quality": np.mean(quality_scores),
                    "total_messages": sum(message_counts),
                    "avg_processing_time": np.mean(processing_times)
                }
            }
            
            self.analytics_cache[cache_key] = result
            return result
            
        except Exception as e:
            self._logger.error(f"生成学习质量曲线失败: {e}")
            return {"chart": None, "error": str(e)}
    
    async def generate_user_activity_heatmap(self, group_id: str, days: int = 7) -> Dict[str, Any]:
        """生成用户活跃度热力图"""
        cache_key = f"activity_heatmap_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]
        
        try:
            # 获取用户消息数据
            messages = await self.db_ext.get_messages_by_timerange(
                group_id, 
                datetime.now() - timedelta(days=days),
                datetime.now()
            )
            
            if not messages:
                return {"chart": None, "message": "暂无消息数据"}
            
            # 创建时间网格
            activity_matrix = np.zeros((7, 24))  # 7天 x 24小时
            
            for msg in messages:
                timestamp = msg.timestamp
                dt = datetime.fromtimestamp(timestamp)
                weekday = dt.weekday()  # 0=Monday, 6=Sunday
                hour = dt.hour
                activity_matrix[weekday, hour] += 1
            
            # 创建热力图
            fig = go.Figure(data=go.Heatmap(
                z=activity_matrix,
                x=[f"{i:02d}:00" for i in range(24)],
                y=['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
                colorscale='Viridis',
                showscale=True
            ))
            
            fig.update_layout(
                title=f'用户活跃度热力图 - 群组 {group_id}',
                xaxis_title='时间',
                yaxis_title='星期',
                template='plotly_white',
                height=300
            )
            
            chart_json = json.dumps(fig, cls=PlotlyJSONEncoder)
            
            # 计算峰值活跃时间
            max_activity = np.unravel_index(np.argmax(activity_matrix), activity_matrix.shape)
            peak_day = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][max_activity[0]]
            peak_hour = f"{max_activity[1]:02d}:00"
            
            result = {
                "chart": chart_json,
                "summary": {
                    "total_messages": len(messages),
                    "peak_activity_day": peak_day,
                    "peak_activity_hour": peak_hour,
                    "avg_messages_per_hour": len(messages) / (days * 24)
                }
            }
            
            self.analytics_cache[cache_key] = result
            return result
            
        except Exception as e:
            self._logger.error(f"生成活跃度热力图失败: {e}")
            return {"chart": None, "error": str(e)}
    
    async def generate_topic_trend_analysis(self, group_id: str, days: int = 30) -> Dict[str, Any]:
        """生成话题趋势分析"""
        cache_key = f"topic_trends_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]
        
        try:
            # 获取消息数据
            messages = await self.db_ext.get_messages_by_timerange(
                group_id,
                datetime.now() - timedelta(days=days),
                datetime.now()
            )
            
            if not messages:
                return {"chart": None, "message": "暂无消息数据"}
            
            # 简单的关键词提取（这里可以后续升级为更复杂的NLP分析）
            topic_counts = defaultdict(int)
            daily_topics = defaultdict(lambda: defaultdict(int))
            
        
            stopwords = {'的', '了', '是', '在', '我', '你', '他', '她', '它', '这', '那', '和', '与', '及'}
            
            for msg in messages:
                content = msg.message or ''
                timestamp = msg.timestamp
                date_key = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                
                # 分词和关键词提取
                words = jieba.lcut(content)
                for word in words:
                    if len(word) > 1 and word not in stopwords:
                        topic_counts[word] += 1
                        daily_topics[date_key][word] += 1
            
            # 获取top话题
            top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            
            # 创建话题趋势图
            fig = go.Figure()
            
            dates = sorted(daily_topics.keys())
            colors = px.colors.qualitative.Set3
            
            for i, (topic, _) in enumerate(top_topics[:5]):  # 只显示前5个话题
                topic_data = [daily_topics[date].get(topic, 0) for date in dates]
                fig.add_trace(go.Scatter(
                    x=dates,
                    y=topic_data,
                    mode='lines+markers',
                    name=topic,
                    line=dict(color=colors[i % len(colors)])
                ))
            
            fig.update_layout(
                title=f'话题趋势分析 - 群组 {group_id}',
                xaxis_title='日期',
                yaxis_title='提及次数',
                template='plotly_white',
                height=400
            )
            
            chart_json = json.dumps(fig, cls=PlotlyJSONEncoder)
            
            # 生成词云
            if topic_counts:
                wordcloud = WordCloud(
                    font_path='simhei.ttf',  # 需要中文字体，可以配置
                    width=800,
                    height=400,
                    background_color='white'
                ).generate_from_frequencies(dict(top_topics[:50]))
                
                # 保存词云图
                wordcloud_path = os.path.join(self.config.data_dir, f"wordcloud_{group_id}.png")
                wordcloud.to_file(wordcloud_path)
            else:
                wordcloud_path = None
            
            result = {
                "chart": chart_json,
                "wordcloud_path": wordcloud_path,
                "top_topics": top_topics[:10],
                "summary": {
                    "total_topics": len(topic_counts),
                    "analysis_days": days,
                    "most_discussed": top_topics[0][0] if top_topics else "无"
                }
            }
            
            self.analytics_cache[cache_key] = result
            return result
            
        except Exception as e:
            self._logger.error(f"生成话题趋势分析失败: {e}")
            return {"chart": None, "error": str(e)}
    
    async def generate_social_network_graph(self, group_id: str, days: int = 30) -> Dict[str, Any]:
        """生成社交关系网络图"""
        cache_key = f"social_network_{group_id}_{days}"
        if self._is_cache_valid(cache_key):
            return self.analytics_cache[cache_key]
        
        try:
            # 获取社交关系数据
            relationships = await self.db_ext.get_social_relationships(group_id, days)
            
            if not relationships:
                return {"chart": None, "message": "暂无社交关系数据"}
            
            # 构建网络图数据
            nodes = []
            edges = []
            user_interactions = defaultdict(int)
            
            # 统计用户交互
            for rel in relationships:
                user1 = rel.get('user1_id')
                user2 = rel.get('user2_id')
                interaction_count = rel.get('interaction_count', 0)
                
                user_interactions[user1] += interaction_count
                user_interactions[user2] += interaction_count
                
                edges.append({
                    'from': user1,
                    'to': user2,
                    'weight': interaction_count
                })
            
            # 创建节点
            for user_id, interaction_count in user_interactions.items():
                nodes.append({
                    'id': user_id,
                    'label': f"用户{user_id[-4:]}",  # 显示ID后4位
                    'value': interaction_count,
                    'title': f"交互次数: {interaction_count}"
                })
            
            # 使用vis.js格式的网络图数据
            network_data = {
                "nodes": nodes,
                "edges": edges,
                "options": {
                    "physics": {
                        "enabled": True,
                        "stabilization": True
                    },
                    "interaction": {
                        "hover": True
                    }
                }
            }
            
            result = {
                "network_data": network_data,
                "summary": {
                    "total_users": len(nodes),
                    "total_relationships": len(edges),
                    "most_active_user": max(user_interactions.items(), key=lambda x: x[1])[0] if user_interactions else "无",
                    "avg_interactions": np.mean(list(user_interactions.values())) if user_interactions else 0
                }
            }
            
            self.analytics_cache[cache_key] = result
            return result
            
        except Exception as e:
            self._logger.error(f"生成社交网络图失败: {e}")
            return {"network_data": None, "error": str(e)}
    
    async def get_comprehensive_analytics(self, group_id: str) -> Dict[str, Any]:
        """获取综合分析报告"""
        try:
            # 并行获取各种分析结果
            tasks = [
                self.generate_learning_trajectory_chart(group_id, 30),
                self.generate_learning_quality_curve(group_id, 30),
                self.generate_user_activity_heatmap(group_id, 7),
                self.generate_topic_trend_analysis(group_id, 30),
                self.generate_social_network_graph(group_id, 30)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            return {
                "learning_trajectory": results[0] if not isinstance(results[0], Exception) else None,
                "quality_curve": results[1] if not isinstance(results[1], Exception) else None,
                "activity_heatmap": results[2] if not isinstance(results[2], Exception) else None,
                "topic_trends": results[3] if not isinstance(results[3], Exception) else None,
                "social_network": results[4] if not isinstance(results[4], Exception) else None,
                "generated_at": datetime.now().isoformat()
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
            # 获取用户消息数据
            messages = await self.db_ext.get_messages_by_timerange(
                group_id, 
                datetime.now() - timedelta(days=days),
                datetime.now()
            )
            
            if not messages:
                return {
                    "user_patterns": {},
                    "common_topics": [],
                    "dominant_emotion": "中性",
                    "recommendations": "暂无足够数据进行分析"
                }
            
            # 分析用户活跃模式
            user_patterns = {}
            topic_counts = defaultdict(int)
            emotion_indicators = {
                "positive": 0, "negative": 0, "neutral": 0,
                "excited": 0, "calm": 0, "active": 0
            }
            
            # 统计用户消息模式
            user_message_counts = defaultdict(int)
            user_message_lengths = defaultdict(list)
            
            stopwords = {'的', '了', '是', '在', '我', '你', '他', '她', '它', '这', '那', '和', '与', '及'}
            
            for msg in messages:
                sender_id = msg.sender_id or ''
                content = msg.message or ''
                timestamp = msg.timestamp
                
                # 统计用户消息数量和长度
                user_message_counts[sender_id] += 1
                user_message_lengths[sender_id].append(len(content))
                
                # 分词提取话题
                words = jieba.lcut(content)
                for word in words:
                    if len(word) > 1 and word not in stopwords:
                        topic_counts[word] += 1
                
                # 简单的情感分析
                positive_words = ['好', '棒', '赞', '喜欢', '开心', '高兴', '哈哈', '笑', '爱']
                negative_words = ['不好', '差', '糟', '讨厌', '难过', '生气', '烦', '恨']
                excited_words = ['太', '超', '非常', '特别', '极', '！', '!']
                
                content_lower = content.lower()
                
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
            
            # 构建用户行为模式
            for user_id, msg_count in user_message_counts.items():
                avg_length = np.mean(user_message_lengths[user_id]) if user_message_lengths[user_id] else 0
                user_patterns[user_id] = {
                    "message_count": msg_count,
                    "avg_message_length": round(avg_length, 2),
                    "activity_level": "高" if msg_count > len(messages) * 0.3 else "中" if msg_count > len(messages) * 0.1 else "低",
                    "communication_style": "详细" if avg_length > 50 else "简洁" if avg_length < 15 else "适中"
                }
            
            # 获取最常见话题
            common_topics = [topic for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]]
            
            # 确定主导情绪
            dominant_emotion = max(emotion_indicators.items(), key=lambda x: x[1])[0]
            emotion_map = {
                "positive": "积极",
                "negative": "消极", 
                "neutral": "中性",
                "excited": "兴奋",
                "calm": "平静",
                "active": "活跃"
            }
            dominant_emotion_zh = emotion_map.get(dominant_emotion, "中性")
            
            # 生成建议
            recommendations = self._generate_behavior_recommendations(user_patterns, emotion_indicators, len(messages))
            
            result = {
                "user_patterns": user_patterns,
                "common_topics": common_topics,
                "dominant_emotion": dominant_emotion_zh,
                "recommendations": recommendations,
                "total_messages": len(messages),
                "active_users": len(user_patterns),
                "emotion_distribution": emotion_indicators
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
                "active_users": 0
            }
    
    def _generate_behavior_recommendations(self, user_patterns: Dict, emotion_indicators: Dict, total_messages: int) -> str:
        """基于行为模式生成建议"""
        try:
            recommendations = []
            
            # 基于用户活跃度的建议
            active_users = sum(1 for pattern in user_patterns.values() if pattern["activity_level"] == "高")
            if active_users > len(user_patterns) * 0.5:
                recommendations.append("群聊活跃度很高，可以考虑更频繁的学习更新")
            elif active_users < len(user_patterns) * 0.2:
                recommendations.append("群聊活跃度较低，建议优化互动策略")
            
            # 基于情绪分布的建议
            positive_ratio = emotion_indicators.get("positive", 0) / max(total_messages, 1)
            if positive_ratio > 0.6:
                recommendations.append("群聊氛围积极，可以保持当前的交流风格")
            elif positive_ratio < 0.3:
                recommendations.append("群聊氛围需要改善，建议增加正面互动")
            
            # 基于消息长度的建议
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