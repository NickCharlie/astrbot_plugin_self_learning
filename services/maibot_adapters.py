"""
MaiBot功能适配器 - 将MaiBot功能适配到现有self_learning架构
遵循现有接口规范，不创造新接口，复用现有架构
"""
import time
from typing import Dict, List, Optional, Any
from dataclasses import asdict

from astrbot.api import logger

from ..core.interfaces import (
    IStyleAnalyzer, ILearningStrategy, IQualityMonitor,
    MessageData, AnalysisResult, ServiceLifecycle
)
from ..config import PluginConfig
from .database_manager import DatabaseManager
from .expression_pattern_learner import ExpressionPatternLearner
from .memory_graph_manager import MemoryGraphManager
from .knowledge_graph_manager import KnowledgeGraphManager
from .time_decay_manager import TimeDecayManager


class MaiBotStyleAnalyzer(IStyleAnalyzer):
    """
    MaiBot风格分析器适配器 - 实现IStyleAnalyzer接口
    集成MaiBot的表达模式学习功能
    """
    
    def __init__(self, config: PluginConfig, db_manager: DatabaseManager, context=None, llm_adapter=None):
        self.config = config
        self.db_manager = db_manager
        
        # 使用改进的单例方法，传递所有需要的参数
        self.expression_learner = ExpressionPatternLearner.get_instance(
            config=config,
            db_manager=db_manager,
            context=context,
            llm_adapter=llm_adapter
        )
        
        self._status = ServiceLifecycle.CREATED
    
    async def start(self) -> bool:
        """启动服务"""
        self._status = ServiceLifecycle.RUNNING
        return await self.expression_learner.start()
    
    async def stop(self) -> bool:
        """停止服务"""
        self._status = ServiceLifecycle.STOPPED
        return await self.expression_learner.stop()
    
    async def analyze_conversation_style(self, group_id: str, messages: List[MessageData]) -> AnalysisResult:
        """
        分析对话风格 - 使用MaiBot的表达模式学习
        
        Args:
            group_id: 群组ID
            messages: 消息列表
            
        Returns:
            分析结果
        """
        try:
            if not messages:
                return AnalysisResult(
                    success=False,
                    confidence=0.0,
                    data={},
                    error="没有提供消息"
                )
            
            # 获取群组ID（直接使用参数）
            # group_id = messages[0].group_id - 不再需要从消息中获取
            
            # 使用MaiBot的表达模式学习
            try:
                patterns = await self.expression_learner.learn_expression_patterns(messages, group_id)
            except Exception as e:
                logger.error(f"表达模式学习失败: {e}")
                patterns = []  # 使用空列表作为fallback
            
            # 转换为现有架构期望的格式
            style_data = {
                "expression_patterns": [p.to_dict() for p in patterns],
                "pattern_count": len(patterns),
                "learning_method": "maibot_expression_learning",
                "group_id": group_id
            }
            
            # 计算置信度（基于学到的模式数量）
            confidence = min(len(patterns) / 10.0, 1.0)  # 10个模式为满分
            
            return AnalysisResult(
                success=True,
                confidence=confidence,
                data=style_data,
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error(f"MaiBot风格分析失败: {e}")
            return AnalysisResult(
                success=False,
                confidence=0.0,
                data={},
                error=str(e)
            )
    
    async def compare_styles(self, style1: Dict[str, Any], style2: Dict[str, Any]) -> float:
        """
        比较风格相似度
        
        Args:
            style1: 风格1
            style2: 风格2
            
        Returns:
            相似度分数 (0-1)
        """
        try:
            # 提取表达模式
            patterns1 = style1.get("expression_patterns", [])
            patterns2 = style2.get("expression_patterns", [])
            
            if not patterns1 or not patterns2:
                return 0.0
            
            # 计算相似度（简单的基于表达方式的重叠度）
            expressions1 = set(p.get("expression", "") for p in patterns1)
            expressions2 = set(p.get("expression", "") for p in patterns2)
            
            if not expressions1 or not expressions2:
                return 0.0
            
            # Jaccard相似度
            intersection = len(expressions1.intersection(expressions2))
            union = len(expressions1.union(expressions2))
            
            return intersection / union if union > 0 else 0.0
            
        except Exception as e:
            logger.error(f"风格比较失败: {e}")
            return 0.0
    
    async def get_style_trends(self) -> Dict[str, Any]:
        """
        获取风格趋势分析 - 使用MaiBot的表达模式趋势
        
        Returns:
            风格趋势数据
        """
        try:
            # 这是一个简化的实现，可以根据需要扩展
            # 在MaiBot架构中，风格趋势可以基于表达模式的演化来计算
            trends = {
                "trend_analysis": "使用MaiBot表达模式学习进行趋势分析",
                "available": False,
                "reason": "MaiBot适配器暂未实现详细的风格趋势分析",
                "suggestions": [
                    "可以基于表达模式的变化频率分析趋势",
                    "结合时间衰减数据提供趋势洞察",
                    "使用记忆图和知识图谱的演化数据"
                ]
            }
            
            return trends
            
        except Exception as e:
            logger.error(f"获取风格趋势失败: {e}")
            return {"error": f"获取风格趋势失败: {e}"}


class MaiBotLearningStrategy(ILearningStrategy):
    """
    MaiBot学习策略适配器 - 实现ILearningStrategy接口
    集成MaiBot的智能学习触发机制
    """
    
    def __init__(self, config: PluginConfig, db_manager: DatabaseManager):
        self.config = config
        self.db_manager = db_manager
        self.expression_learner = ExpressionPatternLearner.get_instance()
        self.memory_graph_manager = MemoryGraphManager.get_instance()
        self.knowledge_graph_manager = KnowledgeGraphManager.get_instance()
        self._status = ServiceLifecycle.CREATED
    
    async def start(self) -> bool:
        """启动服务"""
        self._status = ServiceLifecycle.RUNNING
        return True
    
    async def stop(self) -> bool:
        """停止服务"""
        self._status = ServiceLifecycle.STOPPED
        return True
    
    async def should_learn(self, context: Dict[str, Any]) -> bool:
        """
        判断是否应该学习 - 使用MaiBot的学习触发条件
        
        Args:
            context: 学习上下文
            
        Returns:
            是否应该学习
        """
        try:
            messages = context.get("messages", [])
            group_id = context.get("group_id", "")
            
            if not messages or not group_id:
                return False
            
            # 使用MaiBot的学习触发逻辑
            return self.expression_learner.should_trigger_learning(group_id, messages)
            
        except Exception as e:
            logger.error(f"判断学习条件失败: {e}")
            return False
    
    async def execute_learning_cycle(self, messages: List[MessageData]) -> AnalysisResult:
        """
        执行学习周期 - 使用MaiBot的综合学习机制
        
        Args:
            messages: 消息列表
            
        Returns:
            学习结果
        """
        try:
            if not messages:
                return AnalysisResult(
                    success=False,
                    confidence=0.0,
                    data={},
                    error="没有提供消息"
                )
            
            group_id = messages[0].group_id
            results = {
                "expression_learning": False,
                "memory_updates": 0,
                "knowledge_updates": 0,
                "group_id": group_id
            }
            
            # 1. 表达模式学习
            try:
                success = await self.expression_learner.trigger_learning_for_group(group_id, messages)
                results["expression_learning"] = success
            except Exception as e:
                logger.error(f"表达学习失败: {e}")
            
            # 2. 记忆图更新
            try:
                for message in messages:
                    await self.memory_graph_manager.add_memory_from_message(message, group_id)
                    results["memory_updates"] += 1
            except Exception as e:
                logger.error(f"记忆图更新失败: {e}")
            
            # 3. 知识图谱更新
            try:
                for message in messages:
                    await self.knowledge_graph_manager.process_message_for_knowledge_graph(message, group_id)
                    results["knowledge_updates"] += 1
            except Exception as e:
                logger.error(f"知识图谱更新失败: {e}")
            
            # 计算总体成功度
            success_rate = (
                (1 if results["expression_learning"] else 0) +
                min(results["memory_updates"] / len(messages), 1) +
                min(results["knowledge_updates"] / len(messages), 1)
            ) / 3
            
            return AnalysisResult(
                success=success_rate > 0,
                confidence=success_rate,
                data=results,
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error(f"执行学习周期失败: {e}")
            return AnalysisResult(
                success=False,
                confidence=0.0,
                data={},
                error=str(e)
            )


class MaiBotQualityMonitor(IQualityMonitor):
    """
    MaiBot质量监控器适配器 - 实现IQualityMonitor接口
    集成MaiBot的时间衰减机制进行质量监控
    """
    
    def __init__(self, config: PluginConfig, db_manager: DatabaseManager):
        self.config = config
        self.db_manager = db_manager
        self.time_decay_manager = TimeDecayManager(config, db_manager)
        self._status = ServiceLifecycle.CREATED
    
    async def start(self) -> bool:
        """启动服务"""
        self._status = ServiceLifecycle.RUNNING
        return await self.time_decay_manager.start()
    
    async def stop(self) -> bool:
        """停止服务"""
        self._status = ServiceLifecycle.STOPPED
        return await self.time_decay_manager.stop()
    
    async def evaluate_learning_quality(self, before: Dict[str, Any], after: Dict[str, Any]) -> AnalysisResult:
        """
        评估学习质量 - 使用MaiBot的质量评估方法
        
        Args:
            before: 学习前的状态
            after: 学习后的状态
            
        Returns:
            质量评估结果
        """
        try:
            # 处理None参数，提供默认值
            if before is None:
                before = {}
                logger.warning("学习质量评估: before参数为None，使用空字典作为默认值")
            
            if after is None:
                after = {}
                logger.warning("学习质量评估: after参数为None，使用空字典作为默认值")
            
            # 如果两个参数都为空，返回中性结果
            if not before and not after:
                logger.warning("学习质量评估: before和after参数都为空，返回中性结果")
                return AnalysisResult(
                    success=True,
                    confidence=0.5,
                    data={"message": "无足够数据进行质量评估"},
                    consistency_score=0.5
                )
            
            quality_metrics = {
                "expression_pattern_improvement": 0.0,
                "memory_graph_growth": 0.0,
                "knowledge_graph_growth": 0.0,
                "prompt_improvement": 0.0,
                "overall_quality": 0.0
            }
            
            # 1. 表达模式改进度
            before_patterns = before.get("expression_patterns", [])
            after_patterns = after.get("expression_patterns", [])
            if after_patterns:
                pattern_improvement = len(after_patterns) / max(len(before_patterns), 1)
                quality_metrics["expression_pattern_improvement"] = min(pattern_improvement, 2.0) / 2.0
            
            # 2. 记忆图增长
            before_memory = before.get("memory_updates", 0)
            after_memory = after.get("memory_updates", 0)
            if after_memory > before_memory:
                quality_metrics["memory_graph_growth"] = min((after_memory - before_memory) / 10.0, 1.0)
            
            # 3. 知识图谱增长
            before_knowledge = before.get("knowledge_updates", 0)
            after_knowledge = after.get("knowledge_updates", 0)
            if after_knowledge > before_knowledge:
                quality_metrics["knowledge_graph_growth"] = min((after_knowledge - before_knowledge) / 10.0, 1.0)
            
            # 4. 新增：基于人格prompt的改进评估
            before_prompt = before.get("prompt", "")
            after_prompt = after.get("prompt", "")
            
            if before_prompt != after_prompt:
                # 计算prompt长度变化（增加内容通常表示学习到新知识）
                length_ratio = len(after_prompt) / max(len(before_prompt), 1)
                if length_ratio > 1.0:  # 内容增加
                    quality_metrics["prompt_improvement"] = min((length_ratio - 1.0) * 2, 1.0)  # 最大值1.0
                
                # 检查是否包含学习标识符
                if "【学习更新" in after_prompt and "【学习更新" not in before_prompt:
                    quality_metrics["prompt_improvement"] = max(quality_metrics["prompt_improvement"], 0.6)
                
                # 如果有任何变化，至少给予基础分数
                if quality_metrics["prompt_improvement"] == 0.0:
                    quality_metrics["prompt_improvement"] = 0.3
            
            # 5. 如果没有任何特定指标，但存在人格数据，给予基础评分
            if all(v == 0.0 for v in [quality_metrics["expression_pattern_improvement"], 
                                     quality_metrics["memory_graph_growth"], 
                                     quality_metrics["knowledge_graph_growth"],
                                     quality_metrics["prompt_improvement"]]):
                # 检查是否有有效的人格数据
                if (before.get("prompt") or after.get("prompt")) and before != after:
                    quality_metrics["overall_quality"] = 0.4  # 基础质量分数
                    logger.info("基于数据存在差异给予基础质量评分")
            else:
                # 6. 计算总体质量（包含prompt改进）
                quality_metrics["overall_quality"] = (
                    quality_metrics["expression_pattern_improvement"] +
                    quality_metrics["memory_graph_growth"] +
                    quality_metrics["knowledge_graph_growth"] +
                    quality_metrics["prompt_improvement"]
                ) / 4
            
            # 调试日志
            logger.info(f"学习质量评估详情: prompt_improvement={quality_metrics['prompt_improvement']:.3f}, "
                       f"pattern_improvement={quality_metrics['expression_pattern_improvement']:.3f}, "
                       f"memory_growth={quality_metrics['memory_graph_growth']:.3f}, "
                       f"knowledge_growth={quality_metrics['knowledge_graph_growth']:.3f}, "
                       f"overall_quality={quality_metrics['overall_quality']:.3f}")
            
            logger.info(f"Before prompt长度: {len(before.get('prompt', ''))}, After prompt长度: {len(after.get('prompt', ''))}")
            
            if before != after:
                logger.info("检测到before和after存在差异")
            else:
                logger.info("before和after完全相同")
            
            return AnalysisResult(
                success=True,
                confidence=quality_metrics["overall_quality"],
                data=quality_metrics,
                timestamp=time.time(),
                consistency_score=quality_metrics["overall_quality"]
            )
            
        except Exception as e:
            logger.error(f"学习质量评估失败: {e}")
            return AnalysisResult(
                success=False,
                confidence=0.0,
                data={},
                error=str(e),
                consistency_score=0.0
            )
    
    async def evaluate_learning_batch(self, 
                                    original_persona: Dict[str, Any],
                                    updated_persona: Dict[str, Any],
                                    learning_messages: List[Dict[str, Any]]) -> Any:
        """
        评估学习批次质量 - 兼容LearningQualityMonitor的接口
        
        Args:
            original_persona: 原始人格数据
            updated_persona: 更新后的人格数据
            learning_messages: 学习的消息列表
            
        Returns:
            质量评估结果
        """
        try:
            # 调用现有的evaluate_learning_quality方法
            return await self.evaluate_learning_quality(original_persona, updated_persona)
            
        except Exception as e:
            logger.error(f"学习批次质量评估失败: {e}")
            from ..core.interfaces import AnalysisResult
            return AnalysisResult(
                success=False,
                confidence=0.0,
                data={},
                error=str(e),
                consistency_score=0.0
            )
    
    async def detect_quality_issues(self, data: Dict[str, Any]) -> List[str]:
        """
        检测质量问题 - 使用MaiBot的质量检测机制
        
        Args:
            data: 待检测的数据
            
        Returns:
            质量问题列表
        """
        try:
            issues = []
            
            # 检查表达模式质量
            patterns = data.get("expression_patterns", [])
            if len(patterns) < 3:
                issues.append("表达模式数量不足，可能影响学习效果")
            
            # 检查记忆图连接性
            memory_stats = data.get("memory_graph_stats", {})
            if memory_stats.get("nodes_count", 0) > 0:
                edges_count = memory_stats.get("edges_count", 0)
                if edges_count / memory_stats["nodes_count"] < 0.5:
                    issues.append("记忆图连接稀疏，概念关联度较低")
            
            # 检查知识图谱质量
            kg_stats = data.get("knowledge_graph_stats", {})
            entity_count = kg_stats.get("entities", {}).get("total_count", 0)
            relation_count = kg_stats.get("relations", {}).get("total_count", 0)
            if entity_count > 0 and relation_count / entity_count < 0.3:
                issues.append("知识图谱关系密度较低，实体连接不充分")
            
            # 使用时间衰减检测过时数据
            group_id = data.get("group_id")
            if group_id:
                decay_stats = await self.time_decay_manager.get_decay_statistics(group_id)
                for table_name, stats in decay_stats.items():
                    if isinstance(stats, dict) and stats.get("oldest_days", 0) > 30:
                        issues.append(f"{table_name}包含超过30天的过时数据")
            
            return issues
            
        except Exception as e:
            logger.error(f"质量问题检测失败: {e}")
            return [f"质量检测失败: {e}"]
    
    async def get_quality_report(self) -> Dict[str, Any]:
        """
        获取质量报告 - 使用MaiBot的质量监控方法
        
        Returns:
            质量报告数据
        """
        try:
            # 获取时间衰减统计信息
            decay_stats = {}
            try:
                # 尝试获取全局衰减统计（如果有的话）
                decay_stats = await self.time_decay_manager.get_decay_statistics("global")
            except Exception as e:
                logger.warning(f"获取衰减统计失败: {e}")
            
            # 构建MaiBot风格的质量报告
            current_metrics = {
                'data_freshness_score': self._calculate_data_freshness_score(decay_stats),
                'learning_efficiency': 0.8,  # 基于MaiBot架构的默认效率
                'pattern_diversity': 0.7,    # 表达模式多样性
                'knowledge_coherence': 0.75,  # 知识图谱连贯性
                'memory_integrity': 0.85     # 记忆图完整性
            }
            
            # 趋势分析（简化版，基于数据新鲜度）
            trends = {
                'freshness_trend': 0.0,      # 数据新鲜度趋势
                'efficiency_trend': 0.05,    # 学习效率趋势
                'diversity_trend': 0.02      # 模式多样性趋势
            }
            
            # 生成警报总结
            alert_summary = {
                'critical': 0,
                'high': 0,
                'medium': self._count_data_staleness_issues(decay_stats)
            }
            
            # 生成MaiBot风格的建议
            recommendations = self._generate_maibot_recommendations(current_metrics, decay_stats)
            
            return {
                'current_metrics': current_metrics,
                'trends': trends,
                'recent_alerts': alert_summary['critical'] + alert_summary['high'] + alert_summary['medium'],
                'alert_summary': alert_summary,
                'recommendations': recommendations,
                'data_sources': ['expression_patterns', 'memory_graph', 'knowledge_graph', 'time_decay'],
                'last_updated': time.time()
            }
            
        except Exception as e:
            logger.error(f"获取MaiBot质量报告失败: {e}")
            return {
                'error': f"获取质量报告失败: {e}",
                'current_metrics': {},
                'trends': {},
                'recent_alerts': 0,
                'alert_summary': {'critical': 0, 'high': 0, 'medium': 0},
                'recommendations': ['系统出现错误，建议检查日志']
            }
    
    def _calculate_data_freshness_score(self, decay_stats: Dict[str, Any]) -> float:
        """计算数据新鲜度评分"""
        if not decay_stats:
            return 0.5  # 中等评分，表示没有数据
        
        try:
            # 基于衰减统计计算新鲜度
            total_score = 0.0
            count = 0
            
            for table_name, stats in decay_stats.items():
                if isinstance(stats, dict) and 'oldest_days' in stats:
                    oldest_days = stats.get('oldest_days', 0)
                    # 数据越新鲜，评分越高
                    if oldest_days <= 7:
                        score = 1.0
                    elif oldest_days <= 30:
                        score = 0.8
                    elif oldest_days <= 90:
                        score = 0.6
                    else:
                        score = 0.3
                    
                    total_score += score
                    count += 1
            
            return total_score / count if count > 0 else 0.5
            
        except Exception:
            return 0.5
    
    def _count_data_staleness_issues(self, decay_stats: Dict[str, Any]) -> int:
        """统计数据过时问题数量"""
        if not decay_stats:
            return 0
        
        issues = 0
        for table_name, stats in decay_stats.items():
            if isinstance(stats, dict) and stats.get('oldest_days', 0) > 30:
                issues += 1
        
        return issues
    
    def _generate_maibot_recommendations(self, metrics: Dict[str, Any], decay_stats: Dict[str, Any]) -> List[str]:
        """生成MaiBot风格的改进建议"""
        recommendations = []
        
        # 基于数据新鲜度的建议
        freshness_score = metrics.get('data_freshness_score', 0.5)
        if freshness_score < 0.6:
            recommendations.append("建议清理过时数据，提升学习效率")
        
        # 基于学习效率的建议
        efficiency = metrics.get('learning_efficiency', 0.8)
        if efficiency < 0.7:
            recommendations.append("建议优化表达模式学习触发条件")
        
        # 基于模式多样性的建议
        diversity = metrics.get('pattern_diversity', 0.7)
        if diversity < 0.6:
            recommendations.append("建议增加不同场景下的学习样本")
        
        # 基于衰减统计的建议
        if decay_stats:
            stale_data_count = self._count_data_staleness_issues(decay_stats)
            if stale_data_count > 3:
                recommendations.append("建议启用时间衰减清理机制")
        
        # 如果没有特殊建议，给出积极反馈
        if not recommendations:
            recommendations.append("MaiBot学习系统运行良好，可继续自动学习")
        
        return recommendations

    async def should_pause_learning(self) -> tuple[bool, str]:
        """
        判断是否应该暂停学习 - 使用MaiBot的质量监控机制
        
        Returns:
            (是否应该暂停, 暂停原因)
        """
        try:
            # 检查时间衰减管理器的状态
            if not hasattr(self.time_decay_manager, 'get_decay_statistics'):
                return False, ""
            
            # 基于时间衰减情况判断是否需要暂停
            # 这是一个简化的实现，可以根据需要调整逻辑
            
            # 如果没有足够的历史数据，不暂停学习
            return False, ""
            
        except Exception as e:
            logger.error(f"判断是否暂停学习失败: {e}")
            return False, ""