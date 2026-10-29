"""
MaiBot功能适配器 - 将MaiBot功能适配到现有self_learning架构
遵循现有接口规范，不创造新接口，复用现有架构
"""
import difflib
import inspect
import time
from typing import Dict, List, Optional, Any
from dataclasses import asdict

from astrbot.api import logger

from ...core.interfaces import (
    IStyleAnalyzer, ILearningStrategy, IQualityMonitor,
    MessageData, AnalysisResult, ServiceLifecycle
)
from ...config import PluginConfig
from ..database import DatabaseManager
from ..analysis import ExpressionPatternLearner
from ..state.enhanced_memory_graph_manager import MemoryGraphManager
from .knowledge_graph_manager import KnowledgeGraphManager
from ..state import TimeDecayManager


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
        self.memory_graph_manager = MemoryGraphManager.get_instance(
            config,
            db_manager,
        )
        self.knowledge_graph_manager = KnowledgeGraphManager.get_instance()
        self.knowledge_graph_manager.configure(config, db_manager, None)
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
    
    # 学习质量指标：真实学习产物，缺失数据源时用 None 表示“不可用”
    _GROWTH_METRIC_KEYS = (
        "expression_pattern_improvement",
        "memory_graph_growth",
        "knowledge_graph_growth",
        "prompt_improvement",
    )

    def __init__(
        self,
        config: PluginConfig,
        db_manager: DatabaseManager,
        context: Any = None,
    ):
        self.config = config
        self.db_manager = db_manager
        self.context = context
        self.time_decay_manager = TimeDecayManager(config, db_manager)
        self._status = ServiceLifecycle.CREATED
        # 批次开始时的真实状态快照，供学习产物落库后比较增长
        self._batch_snapshots: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _message_text(message) -> str:
        if isinstance(message, dict):
            return str(
                message.get("message")
                or message.get("content")
                or message.get("text")
                or ""
            )
        return str(
            getattr(message, "message", None)
            or getattr(message, "content", None)
            or getattr(message, "text", None)
            or ""
        )

    def _derive_message_batch_quality(self, learning_messages: List[Dict[str, Any]]) -> float:
        texts = [
            self._message_text(message).strip()
            for message in (learning_messages or [])
        ]
        texts = [text for text in texts if len(text) >= 2]
        if not texts:
            return 0.0

        try:
            batch_size = max(1, int(getattr(self.config, "max_messages_per_batch", 200) or 200))
        except (TypeError, ValueError):
            batch_size = 200

        volume_score = min(len(texts) / batch_size, 1.0)
        avg_len = sum(min(len(text), 120) for text in texts) / len(texts)
        length_score = min(avg_len / 40.0, 1.0)
        unique_score = len(set(texts)) / len(texts)
        quality_score = volume_score * 0.55 + length_score * 0.30 + unique_score * 0.15
        return max(0.25, min(0.95, quality_score))

    @staticmethod
    def _resolve_group_id(
        original_persona: Dict[str, Any],
        updated_persona: Dict[str, Any],
        learning_messages: List[Dict[str, Any]],
    ) -> str:
        """从学习消息或人格数据中解析群组 ID。"""
        for message in learning_messages or []:
            if isinstance(message, dict) and message.get("group_id"):
                return str(message["group_id"])
        for persona in (original_persona, updated_persona):
            if isinstance(persona, dict) and persona.get("group_id"):
                return str(persona["group_id"])
        return ""

    def _local_memory_node_count(self, group_id: str) -> Optional[int]:
        """本地记忆图的实时节点数（内存图比 memories 表更及时）。"""
        try:
            manager = MemoryGraphManager.get_instance()
            memory_graph = getattr(manager, "memory_graphs", {}).get(group_id)
            graph = getattr(memory_graph, "G", None)
            if graph is None or not hasattr(graph, "number_of_nodes"):
                return None
            return int(graph.number_of_nodes())
        except Exception as exc:
            logger.debug(f"读取本地记忆图节点数失败: {exc}")
            return None

    def _livingmemory_graph_store(self) -> Optional[Any]:
        """获取 LivingMemory 后端 graph_store（仅在记忆委托生效时）。"""
        return self._livingmemory_backend()[0]

    def _livingmemory_memory_engine(self) -> Optional[Any]:
        """获取 LivingMemory MemoryEngine（用于统计回退）。"""
        return self._livingmemory_backend()[1]

    def _livingmemory_backend(self) -> tuple[Optional[Any], Optional[Any]]:
        """探测 LivingMemory 的 graph_store 与 memory_engine。

        LivingMemory 2.8.x 的插件结构仍为
        ``star.star_cls.initializer.memory_engine``；旧版本字段保持兼容。
        """
        if not self.context:
            return None, None
        try:
            from ...core.feature_delegation import FeatureDelegation

            delegation = FeatureDelegation(self.config, self.context)
            if not delegation.should_delegate_memory():
                return None, None
            star = delegation.memory_plugin()
            plugin = getattr(star, "star_cls", None)
            initializer = getattr(plugin, "initializer", None)
            memory_engine = (
                getattr(initializer, "memory_engine", None)
                or getattr(plugin, "memory_engine", None)
            )
            return getattr(memory_engine, "graph_store", None), memory_engine
        except Exception as exc:
            logger.debug(f"读取 LivingMemory 后端失败: {exc}")
            return None, None

    async def _livingmemory_total_memories(self) -> Optional[int]:
        """回退读取 LivingMemory 全局记忆总数（2.7+ 的 get_statistics）。"""
        memory_engine = self._livingmemory_memory_engine()
        stats_getter = getattr(memory_engine, "get_statistics", None)
        if not callable(stats_getter):
            return None
        try:
            stats = stats_getter()
            if inspect.isawaitable(stats):
                stats = await stats
        except Exception as exc:
            logger.debug(f"读取 LivingMemory 统计失败: {exc}")
            return None
        if not isinstance(stats, dict):
            return None
        total = stats.get("total_memories")
        if isinstance(total, (int, float)):
            return int(total)
        return None

    async def _count_livingmemory_memories(self, group_id: str) -> Optional[int]:
        """从 LivingMemory 图谱快照统计记忆条数，无法读取时返回 None。"""
        graph_store = self._livingmemory_graph_store()
        snapshot_getter = getattr(graph_store, "get_graph_snapshot", None)
        if not callable(snapshot_getter):
            return await self._livingmemory_total_memories()

        for session_id in (group_id, None):
            try:
                snapshot = snapshot_getter(
                    session_id=session_id,
                    persona_id=None,
                    limit_memories=500,
                    limit_entries=100,
                    limit_nodes=100,
                    limit_edges=200,
                )
                if inspect.isawaitable(snapshot):
                    snapshot = await snapshot
            except TypeError:
                continue
            except Exception as exc:
                logger.debug(f"读取 LivingMemory 快照失败: {exc}")
                continue
            if isinstance(snapshot, dict):
                memories = snapshot.get("memories") or []
                if memories:
                    return len(memories)

        # 2.8.x 轻量快照有条数上限；无快照数据时回退全局统计
        return await self._livingmemory_total_memories()

    async def _count_local_memories(self, group_id: str) -> Optional[int]:
        """本地 memories 表记忆条数。"""
        if not self.db_manager or not hasattr(self.db_manager, "get_session"):
            return None
        try:
            from sqlalchemy import func, select

            from ...models.orm.memory import Memory

            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(func.count(Memory.id)).where(Memory.group_id == group_id)
                )
                count = result.scalar()
            return int(count or 0)
        except Exception as exc:
            logger.debug(f"读取本地记忆条数失败: {exc}")
            return None

    async def _collect_learning_snapshot(self, group_id: str) -> Optional[Dict[str, Any]]:
        """采集群组真实学习产物计数（表达模式 / 记忆 / 知识图谱）。

        人格字典本身不包含这些字段，必须从数据库或委托插件读取，
        否则质量指标会永远退化。无法读取的指标保留 None（N/A）。
        """
        if not group_id:
            return None

        snapshot: Dict[str, Any] = {
            "expression_patterns": None,
            "memory_updates": None,
            "knowledge_updates": None,
            "memory_source": None,
        }

        if self.db_manager and hasattr(self.db_manager, "get_session"):
            try:
                from sqlalchemy import func, select

                from ...models.orm.expression import ExpressionPattern
                from ...models.orm.knowledge_graph import KGEntity, KGRelation

                async with self.db_manager.get_session() as session:
                    pattern_result = await session.execute(
                        select(func.count(ExpressionPattern.id)).where(
                            ExpressionPattern.group_id == group_id
                        )
                    )
                    snapshot["expression_patterns"] = int(
                        pattern_result.scalar() or 0
                    )

                    entity_result = await session.execute(
                        select(func.count(KGEntity.id)).where(
                            KGEntity.group_id == group_id
                        )
                    )
                    relation_result = await session.execute(
                        select(func.count(KGRelation.id)).where(
                            KGRelation.group_id == group_id
                        )
                    )
                    snapshot["knowledge_updates"] = int(
                        entity_result.scalar() or 0
                    ) + int(relation_result.scalar() or 0)
            except Exception as exc:
                logger.debug(f"读取表达模式/知识图谱快照失败: {exc}")

        livingmemory_count = await self._count_livingmemory_memories(group_id)
        if livingmemory_count is not None:
            snapshot["memory_updates"] = livingmemory_count
            snapshot["memory_source"] = "livingmemory"
        else:
            local_graph_count = self._local_memory_node_count(group_id)
            if local_graph_count is not None:
                snapshot["memory_updates"] = local_graph_count
                snapshot["memory_source"] = "local_graph"
            else:
                local_db_count = await self._count_local_memories(group_id)
                if local_db_count is not None:
                    snapshot["memory_updates"] = local_db_count
                    snapshot["memory_source"] = "local_db"

        if all(snapshot[key] is None for key in (
            "expression_patterns",
            "memory_updates",
            "knowledge_updates",
        )):
            return None
        return snapshot

    @staticmethod
    def _growth_score(before_count: Any, after_count: Any) -> Optional[float]:
        """把计数增长归一化到 0-1（10 条增量视为满分）。"""
        if after_count is None:
            return None
        try:
            before_value = int(before_count or 0)
            after_value = int(after_count or 0)
        except (TypeError, ValueError):
            return None
        return min(max(after_value - before_value, 0) / 10.0, 1.0)

    @staticmethod
    def _score_prompt_change(before_prompt: str, after_prompt: str) -> float:
        """按真实文本差异评分，长度不变但内容变化时也能得分。"""
        if before_prompt == after_prompt:
            return 0.0
        if not before_prompt:
            return 1.0
        if not after_prompt:
            return 0.0

        added_chars = max(len(after_prompt) - len(before_prompt), 0)
        score = min(added_chars / max(len(before_prompt) * 0.2, 20.0), 1.0)

        similarity = difflib.SequenceMatcher(None, before_prompt, after_prompt).ratio()
        score = max(score, min(1.0 - similarity, 1.0))

        if "【学习更新" in after_prompt and "【学习更新" not in before_prompt:
            score = max(score, 0.6)
        return max(0.0, min(score, 1.0))

    @staticmethod
    def _format_metric(value: Any) -> str:
        return "n/a" if value is None else f"{float(value):.3f}"

    def _log_quality_metrics(
        self,
        metrics: Dict[str, Any],
        group_id: str,
        level: str = "info",
    ) -> None:
        log = logger.info if level == "info" else logger.debug
        log(
            "学习质量评估详情 (group=%s): prompt_improvement=%s, "
            "pattern_improvement=%s, memory_growth=%s, knowledge_growth=%s, "
            "overall_quality=%s, source=%s",
            group_id or "unknown",
            self._format_metric(metrics.get("prompt_improvement")),
            self._format_metric(metrics.get("expression_pattern_improvement")),
            self._format_metric(metrics.get("memory_graph_growth")),
            self._format_metric(metrics.get("knowledge_graph_growth")),
            self._format_metric(metrics.get("overall_quality")),
            metrics.get("memory_source") or metrics.get("quality_source") or "local",
        )

    def _build_quality_metrics(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        snapshot_before: Optional[Dict[str, Any]] = None,
        snapshot_after: Optional[Dict[str, Any]] = None,
        learning_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """按真实学习产物构建指标；无数据源的指标返回 None。"""
        metrics: Dict[str, Any] = {
            "expression_pattern_improvement": None,
            "memory_graph_growth": None,
            "knowledge_graph_growth": None,
            "prompt_improvement": None,
            "overall_quality": 0.0,
        }

        before_snapshot = snapshot_before or {}
        after_snapshot = snapshot_after or {}
        if after_snapshot.get("memory_source"):
            metrics["memory_source"] = after_snapshot["memory_source"]

        # 1. 表达模式改进度：优先使用真实快照，兼容旧的 state 字典字段
        if after_snapshot.get("expression_patterns") is not None:
            metrics["expression_pattern_improvement"] = self._growth_score(
                before_snapshot.get("expression_patterns"),
                after_snapshot.get("expression_patterns"),
            )
        else:
            before_patterns = before.get("expression_patterns") or []
            after_patterns = after.get("expression_patterns") or []
            if after_patterns:
                pattern_improvement = len(after_patterns) / max(len(before_patterns), 1)
                metrics["expression_pattern_improvement"] = min(pattern_improvement, 2.0) / 2.0

        # 2. 记忆图增长
        if after_snapshot.get("memory_updates") is not None:
            metrics["memory_graph_growth"] = self._growth_score(
                before_snapshot.get("memory_updates"),
                after_snapshot.get("memory_updates"),
            )
        else:
            before_memory = before.get("memory_updates")
            after_memory = after.get("memory_updates")
            if isinstance(after_memory, (int, float)):
                metrics["memory_graph_growth"] = self._growth_score(
                    before_memory, after_memory
                )

        # 3. 知识图谱增长
        if after_snapshot.get("knowledge_updates") is not None:
            metrics["knowledge_graph_growth"] = self._growth_score(
                before_snapshot.get("knowledge_updates"),
                after_snapshot.get("knowledge_updates"),
            )
        else:
            before_knowledge = before.get("knowledge_updates")
            after_knowledge = after.get("knowledge_updates")
            if isinstance(after_knowledge, (int, float)):
                metrics["knowledge_graph_growth"] = self._growth_score(
                    before_knowledge, after_knowledge
                )

        # 4. 人格 prompt 改进度
        before_prompt = str(before.get("prompt", "") or "")
        after_prompt = str(after.get("prompt", "") or "")
        if before_prompt or after_prompt:
            metrics["prompt_improvement"] = self._score_prompt_change(before_prompt, after_prompt)

        # 5. 总体质量：只对可用指标求均值，避免缺失数据被当成 0 拉低分数
        available = [
            metrics[key]
            for key in self._GROWTH_METRIC_KEYS
            if isinstance(metrics.get(key), (int, float))
        ]
        if available:
            metrics["overall_quality"] = sum(available) / len(available)
        elif learning_messages:
            metrics["overall_quality"] = self._derive_message_batch_quality(learning_messages)
            metrics["quality_source"] = "learning_messages"
        return metrics

    async def start(self) -> bool:
        """启动服务"""
        self._status = ServiceLifecycle.RUNNING
        return await self.time_decay_manager.start()
    
    async def stop(self) -> bool:
        """停止服务"""
        self._status = ServiceLifecycle.STOPPED
        return await self.time_decay_manager.stop()
    
    async def evaluate_learning_quality(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        snapshot_before: Optional[Dict[str, Any]] = None,
        snapshot_after: Optional[Dict[str, Any]] = None,
        learning_messages: Optional[List[Dict[str, Any]]] = None,
        log_details: bool = True,
    ) -> AnalysisResult:
        """
        评估学习质量 - 使用MaiBot的质量评估方法

        Args:
            before: 学习前的人格状态
            after: 学习后的人格状态
            snapshot_before: 学习前真实学习产物计数（表达模式/记忆/知识）
            snapshot_after: 学习后真实学习产物计数
            learning_messages: 本批次学习消息
            log_details: 是否输出评估详情日志

        Returns:
            质量评估结果
        """
        try:
            # 处理None参数,提供默认值
            if before is None:
                before = {}
                logger.warning("学习质量评估: before参数为None，使用空字典作为默认值")

            if after is None:
                after = {}
                logger.warning("学习质量评估: after参数为None，使用空字典作为默认值")

            # 处理list类型参数,转换为字典
            if isinstance(before, list):
                logger.warning(f"学习质量评估: before参数为list类型(长度{len(before)})，转换为空字典")
                before = {}

            if isinstance(after, list):
                logger.warning(f"学习质量评估: after参数为list类型(长度{len(after)})，转换为空字典")
                after = {}

            # 如果没有任何可评估数据,返回中性结果
            if (
                not before
                and not after
                and not snapshot_after
                and not learning_messages
            ):
                logger.warning("学习质量评估: before和after参数都为空，返回中性结果")
                return AnalysisResult(
                    success=True,
                    confidence=0.5,
                    data={"message": "无足够数据进行质量评估"},
                    consistency_score=0.5
                )

            quality_metrics = self._build_quality_metrics(
                before,
                after,
                snapshot_before=snapshot_before,
                snapshot_after=snapshot_after,
                learning_messages=learning_messages,
            )

            if log_details:
                self._log_quality_metrics(quality_metrics, "", level="info")
                logger.info(
                    "Before prompt长度: %s, After prompt长度: %s",
                    len(str(before.get("prompt", "") or "")),
                    len(str(after.get("prompt", "") or "")),
                )

            overall = float(quality_metrics.get("overall_quality") or 0.0)
            return AnalysisResult(
                success=True,
                confidence=overall,
                data=quality_metrics,
                timestamp=time.time(),
                consistency_score=overall
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

        人格字典不包含表达模式/记忆/知识字段，因此从数据库或委托插件
        采集真实学习产物快照，并在学习应用后由 refresh_learning_impact 刷新。

        Args:
            original_persona: 原始人格数据
            updated_persona: 更新后的人格数据
            learning_messages: 学习的消息列表
            
        Returns:
            质量评估结果
        """
        try:
            group_id = self._resolve_group_id(
                original_persona, updated_persona, learning_messages
            )
            snapshot = (
                await self._collect_learning_snapshot(group_id)
                if group_id
                else None
            )
            if group_id and snapshot is not None:
                self._batch_snapshots[group_id] = snapshot

            result = await self.evaluate_learning_quality(
                original_persona,
                updated_persona,
                snapshot_before=snapshot,
                snapshot_after=snapshot,
                learning_messages=learning_messages,
                log_details=False,
            )
            result.data = dict(result.data or {})
            if group_id:
                result.data["group_id"] = group_id

            score = result.consistency_score if result.consistency_score is not None else result.confidence
            if (score or 0.0) <= 0:
                message_quality = self._derive_message_batch_quality(learning_messages)
                if message_quality > 0:
                    result.consistency_score = message_quality
                    result.confidence = message_quality
                    result.data["message_signal_quality"] = message_quality
                    result.data["quality_source"] = "learning_messages"
            return result
            
        except Exception as e:
            logger.error(f"学习批次质量评估失败: {e}")
            return AnalysisResult(
                success=False,
                confidence=0.0,
                data={},
                error=str(e),
                consistency_score=0.0
            )

    async def refresh_learning_impact(
        self,
        group_id: str,
        quality_metrics: Any,
        learning_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[float]:
        """学习产物落库后刷新真实增长指标。

        表达模式在批次末尾才写入 expression_patterns 表，本地记忆图与
        LivingMemory 图存储也只在消息处理/维护时变化，因此需要在
        ``_apply_learning_updates`` 之后再采集一次快照。

        Returns:
            刷新后的 overall_quality；无可用快照时返回 None。
        """
        data = getattr(quality_metrics, "data", None)
        if not group_id or not isinstance(data, dict):
            return None

        snapshot_before = self._batch_snapshots.get(group_id)
        snapshot_after = await self._collect_learning_snapshot(group_id)
        if snapshot_before is None or snapshot_after is None:
            return None

        updated = dict(data)
        for metric_key, snapshot_key in (
            ("expression_pattern_improvement", "expression_patterns"),
            ("memory_graph_growth", "memory_updates"),
            ("knowledge_graph_growth", "knowledge_updates"),
        ):
            updated[metric_key] = self._growth_score(
                (snapshot_before or {}).get(snapshot_key),
                snapshot_after.get(snapshot_key),
            )

        if snapshot_after.get("memory_source"):
            updated["memory_source"] = snapshot_after["memory_source"]

        available = [
            updated[key]
            for key in self._GROWTH_METRIC_KEYS
            if isinstance(updated.get(key), (int, float))
        ]
        if available:
            updated["overall_quality"] = sum(available) / len(available)
            updated.pop("quality_source", None)
        elif learning_messages:
            updated["overall_quality"] = self._derive_message_batch_quality(learning_messages)
            updated["quality_source"] = "learning_messages"

        overall = float(updated.get("overall_quality") or 0.0)
        quality_metrics.data = updated
        quality_metrics.consistency_score = overall
        quality_metrics.confidence = overall
        self._batch_snapshots.pop(group_id, None)

        self._log_quality_metrics(updated, group_id, level="info")
        logger.info(
            "学习前后真实计数 (group=%s): 表达模式 %s→%s, 记忆 %s→%s, 知识 %s→%s",
            group_id,
            (snapshot_before or {}).get("expression_patterns"),
            snapshot_after.get("expression_patterns"),
            (snapshot_before or {}).get("memory_updates"),
            snapshot_after.get("memory_updates"),
            (snapshot_before or {}).get("knowledge_updates"),
            snapshot_after.get("knowledge_updates"),
        )
        return overall
    
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
