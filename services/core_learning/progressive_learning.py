"""
渐进式学习服务 - 协调各个组件实现智能自适应学习
"""
import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context

from ...config import PluginConfig
from ...exceptions import LearningError

from ..database import DatabaseManager
from ..learning.expression_learning import ExpressionLearningModule
from ..learning.persona_learning import PersonaLearningModule
from ..learning.sample_filter import filter_learning_messages
from ..monitoring.instrumentation import monitored


@dataclass
class LearningSession:
    """学习会话"""
    session_id: str
    start_time: str
    end_time: Optional[str] = None
    messages_processed: int = 0
    filtered_messages: int = 0
    style_updates: int = 0
    quality_score: float = 0.0
    success: bool = False


class ProgressiveLearningService:
    """渐进式学习服务"""
    
    def __init__(self, config: PluginConfig, context: Context,
                 db_manager: DatabaseManager,
                 message_collector,
                 multidimensional_analyzer,
                 style_analyzer,
                 quality_monitor,
                 persona_manager, # 添加 persona_manager 参数
                 ml_analyzer, # 添加 ml_analyzer 参数
                 prompts: Any): # 添加 prompts 参数
        self.config = config
        self.context = context
        self.db_manager = db_manager
        
        # 注入各个组件服务
        self.message_collector = message_collector
        self.multidimensional_analyzer = multidimensional_analyzer
        self.style_analyzer = style_analyzer
        self.quality_monitor = quality_monitor
        self.persona_manager = persona_manager # 注入 persona_manager
        self.ml_analyzer = ml_analyzer # 注入 ml_analyzer
        self.prompts = prompts # 保存 prompts 实例

        # MaiBot-style learning domains: expression learning and persona
        # learning are independent modules; this service only orchestrates
        # the batch lifecycle.
        self.expression_learning = ExpressionLearningModule(db_manager)
        self.persona_learning = PersonaLearningModule(
            config=config,
            context=context,
            db_manager=db_manager,
            persona_manager=persona_manager,
            multidimensional_analyzer=multidimensional_analyzer,
            prompts=prompts,
            resolve_umo=self._resolve_umo,
            json_serializer=self._json_serializer,
        )
        
        # 学习状态 - 使用字典管理每个群组的学习状态
        self.learning_active = {} # 改为字典，按群组ID管理
        
        # 增量更新回调函数，降低耦合性
        self.update_system_prompt_callback = None

        self._group_sessions: Dict[str, LearningSession] = {}
        self.learning_sessions: List[LearningSession] = [] # 历史学习会话，可以从数据库加载
        self.learning_lock = asyncio.Lock() # 添加异步锁防止竞态条件

        # 学习控制参数
        self.batch_size = config.max_messages_per_batch
        self.learning_interval = config.learning_interval_hours * 3600 # 转换为秒
        self.quality_threshold = config.style_update_threshold

        logger.info("渐进式学习服务初始化完成")

    def _resolve_umo(self, group_id: str) -> str:
        """将group_id解析为unified_msg_origin以支持多配置文件"""
        if hasattr(self, 'group_id_to_unified_origin'):
            return self.group_id_to_unified_origin.get(group_id, group_id)
        return group_id

    def _get_expression_learning_module(self) -> ExpressionLearningModule:
        """Return the expression-learning domain module, creating it lazily for tests."""
        module = getattr(self, "expression_learning", None)
        if module is None:
            module = ExpressionLearningModule(self.db_manager)
            self.expression_learning = module
        return module

    def _get_persona_learning_module(self) -> PersonaLearningModule:
        """Return the persona-learning domain module, creating it lazily for tests."""
        module = getattr(self, "persona_learning", None)
        if module is None:
            module = PersonaLearningModule(
                config=getattr(self, "config", None),
                context=getattr(self, "context", None),
                db_manager=getattr(self, "db_manager", None),
                persona_manager=getattr(self, "persona_manager", None),
                multidimensional_analyzer=getattr(
                    self, "multidimensional_analyzer", None
                ),
                prompts=getattr(self, "prompts", None),
                resolve_umo=self._resolve_umo,
                json_serializer=self._json_serializer,
            )
            self.persona_learning = module
        return module

    @staticmethod
    def _quality_value(value) -> Optional[float]:
        if value is None:
            return None
        try:
            score = float(value)
        except (TypeError, ValueError):
            return None
        if score <= 0:
            return None
        return max(0.0, min(1.0, score))

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

    @staticmethod
    def _message_score(message, key: str) -> Optional[float]:
        if isinstance(message, dict):
            value = message.get(key)
        else:
            value = getattr(message, key, None)
        try:
            score = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, score))

    def _derive_message_signal_quality(self, learning_messages: List[Dict[str, Any]]) -> float:
        texts = [
            self._message_text(message).strip()
            for message in (learning_messages or [])
        ]
        texts = [text for text in texts if len(text) >= 2]
        if not texts:
            return 0.0

        relevance_scores = []
        for message in learning_messages or []:
            for key in ("relevance_score", "confidence", "quality_score"):
                score = self._message_score(message, key)
                if score is not None:
                    relevance_scores.append(score)
                    break

        try:
            batch_size = max(1, int(getattr(self.config, "max_messages_per_batch", 200) or 200))
        except (TypeError, ValueError):
            batch_size = 200

        volume_score = min(len(texts) / batch_size, 1.0)
        avg_len = sum(min(len(text), 120) for text in texts) / len(texts)
        length_score = min(avg_len / 40.0, 1.0)
        unique_score = len(set(texts)) / len(texts)
        relevance_score = (
            sum(relevance_scores) / len(relevance_scores)
            if relevance_scores
            else 0.65
        )

        quality_score = (
            volume_score * 0.50
            + length_score * 0.25
            + unique_score * 0.15
            + relevance_score * 0.10
        )
        return max(0.25, min(0.95, quality_score))

    def _resolve_learning_quality_score(self, quality_metrics, learning_messages: List[Dict[str, Any]]) -> float:
        metric_values = []
        for field_name in (
            "consistency_score",
            "style_stability",
            "vocabulary_diversity",
            "emotional_balance",
            "coherence_score",
            "confidence",
        ):
            score = self._quality_value(getattr(quality_metrics, field_name, None))
            if score is not None:
                metric_values.append(score)

        data = getattr(quality_metrics, "data", None)
        if isinstance(data, dict):
            for field_name in (
                "overall_quality",
                "prompt_improvement",
                "expression_pattern_improvement",
                "memory_graph_growth",
                "knowledge_graph_growth",
            ):
                score = self._quality_value(data.get(field_name))
                if score is not None:
                    metric_values.append(score)

        if metric_values:
            return sum(metric_values) / len(metric_values)

        return self._derive_message_signal_quality(learning_messages)

    def _patch_zero_quality_metric(self, quality_metrics, quality_score: float) -> None:
        current = self._quality_value(getattr(quality_metrics, "consistency_score", None))
        if current is None and quality_score > 0 and hasattr(quality_metrics, "consistency_score"):
            try:
                quality_metrics.consistency_score = quality_score
            except Exception:
                pass

    def _build_fallback_style_analysis_data(
        self,
        filtered_messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build reviewable persona-learning content when refine analysis is unavailable."""
        texts = [
            self._message_text(message).strip()
            for message in (filtered_messages or [])
        ]
        texts = [text for text in texts if text]
        sample_texts = texts[:5]
        avg_len = sum(len(text) for text in texts) / max(len(texts), 1)

        expression_features = []
        if avg_len >= 40:
            expression_features.append("偏向较完整、信息量较高的表达")
        elif avg_len > 0:
            expression_features.append("偏向短句和即时回应")
        if any("?" in text or "？" in text for text in texts):
            expression_features.append("常使用提问式互动")
        if any("!" in text or "！" in text for text in texts):
            expression_features.append("语气中包含强调和情绪表达")
        if not expression_features:
            expression_features.append("保留群聊中的自然表达习惯")

        sample_lines = [
            f"- {text[:80]}"
            for text in sample_texts
        ]
        learning_insights = [
            f"基于 {len(texts)} 条通过筛选的群聊消息生成待审人格候选。",
            "请在人工审查后决定是否将这些表达习惯追加到当前人格。",
        ]
        if sample_lines:
            learning_insights.append("代表性表达：")
            learning_insights.extend(sample_lines)

        return {
            "message_count": len(texts),
            "analysis_timestamp": datetime.now().isoformat(),
            "learning_insights": "\n".join(learning_insights),
            "style_analysis": {
                "text_style": (
                    "长句详述型" if avg_len >= 40 else "短句互动型"
                ),
                "expression_features": expression_features,
                "tone": "强调型" if any("!" in text or "！" in text for text in texts) else "平和型",
                "topics": [],
            },
        }

    async def _save_filtered_messages_for_stats(
        self,
        group_id: str,
        filtered_messages: List[Dict[str, Any]],
    ) -> int:
        """Persist passed learning samples so WebUI filter-rate stats move."""
        saved_count = 0
        for msg in filtered_messages or []:
            try:
                await self.message_collector.add_filtered_message({
                    "raw_message_id": msg.get("id"),
                    "message": msg.get("message", ""),
                    "sender_id": msg.get("sender_id", ""),
                    "group_id": msg.get("group_id", group_id),
                    "timestamp": msg.get("timestamp", int(time.time())),
                    "confidence": msg.get("relevance_score", 1.0),
                    "filter_reason": msg.get("filter_reason", "batch_learning"),
                })
                saved_count += 1
            except Exception as exc:
                logger.debug(f"保存筛选消息统计失败: {exc}")

        if saved_count:
            logger.debug(
                f"已保存 {saved_count}/{len(filtered_messages or [])} 条筛选消息到 FilteredMessage 表"
            )
        return saved_count

    def set_update_system_prompt_callback(self, callback):
        """
        设置增量更新回调函数
        
        Args:
            callback: 异步回调函数，接受 group_id 参数
        """
        self.update_system_prompt_callback = callback
        logger.info("增量更新回调函数已设置")

    async def start(self):
        """服务启动时加载历史学习会话"""
        # 假设每个群组有独立的学习会话，这里需要一个 group_id
        # 为了简化，暂时假设加载一个默认的或全局的学习会话
        # 实际应用中，可能需要根据当前处理的群组ID来加载
        default_group_id = "global_learning" # 或者从配置中获取
        # 这里可以加载所有历史会话，或者只加载最近的N个
        # 为了简化，我们暂时不从数据库加载历史会话列表，只在每次会话结束时保存
        # 如果需要加载历史会话，需要 DatabaseManager 提供 load_all_learning_sessions 方法
        logger.info("渐进式学习服务启动，准备开始学习。")

    @monitored
    async def start_learning(self, group_id: str) -> bool:
        """启动学习流程 - 优化为后台任务执行"""
        async with self.learning_lock: # 使用锁防止竞态条件
            try:
                # 检查该群组是否已经在学习
                if self.learning_active.get(group_id, False):
                    logger.info(f"群组 {group_id} 学习已在进行中，跳过启动")
                    return True # 返回True表示学习状态正常
                
                # 设置该群组为学习状态
                self.learning_active[group_id] = True
                
                # 创建新的学习会话
                session_id = f"session_{group_id}_{int(time.time())}"
                self._group_sessions[group_id] = LearningSession(
                    session_id=session_id,
                    start_time=datetime.now().isoformat()
                )
                # 保存新的学习会话到数据库
                await self.db_manager.save_learning_session_record(group_id, self._group_sessions[group_id].__dict__)
                
                logger.info(f"开始学习会话: {session_id} for group {group_id}")
                
                # 创建后台任务，确保不阻塞主线程
                learning_task = asyncio.create_task(self._learning_loop_safe(group_id))
                
                # 设置任务完成回调
                def on_learning_complete(task):
                    if task.exception():
                        logger.error(f"群组 {group_id} 学习任务异常完成: {task.exception()}")
                    else:
                        logger.info(f"群组 {group_id} 学习任务正常完成")
                    # 清除该群组的学习状态
                    self.learning_active[group_id] = False
                    
                learning_task.add_done_callback(on_learning_complete)
                
                return True
                
            except Exception as e:
                logger.error(f"启动群组 {group_id} 学习失败: {e}")
                # 确保清除学习状态
                self.learning_active[group_id] = False
                return False

    async def stop_learning(self, group_id: str = None):
        """停止学习流程"""
        if group_id:
            # 停止特定群组的学习
            self.learning_active[group_id] = False
            logger.info(f"停止群组 {group_id} 的学习任务")
        else:
            # 停止所有群组的学习
            for gid in list(self.learning_active.keys()):
                self.learning_active[gid] = False
            logger.info("停止所有群组的学习任务")
        
        if group_id:
            session = self._group_sessions.pop(group_id, None)
            if session:
                session.end_time = datetime.now().isoformat()
                session.success = True
                await self.db_manager.save_learning_session_record(group_id, session.__dict__)
                self.learning_sessions.append(session)
                logger.info(f"学习会话结束: {session.session_id}")
        else:
            for gid, session in list(self._group_sessions.items()):
                session.end_time = datetime.now().isoformat()
                session.success = True
                await self.db_manager.save_learning_session_record(gid, session.__dict__)
                self.learning_sessions.append(session)
                logger.info(f"学习会话结束: {session.session_id}")
            self._group_sessions.clear()

    @monitored
    async def _learning_loop_safe(self, group_id: str):
        """安全的学习循环 - 在后台线程执行，包含完整错误处理"""
        try:
            while self.learning_active.get(group_id, False):
                try:
                    # 检查是否应该暂停学习
                    should_pause, reason = await self.quality_monitor.should_pause_learning()
                    if should_pause:
                        logger.warning(f"群组 {group_id} 学习被暂停: {reason}")
                        await self.stop_learning(group_id)
                        break
                    
                    # 执行一个学习批次 - 在后台执行
                    await self._execute_learning_batch_background(group_id)
                    
                    # 等待下一个学习周期
                    await asyncio.sleep(self.learning_interval)
                    
                except asyncio.CancelledError:
                    logger.info(f"群组 {group_id} 学习任务被取消")
                    break
                except Exception as e:
                    logger.error(f"群组 {group_id} 学习循环异常: {e}", exc_info=True)
                    await asyncio.sleep(60) # 异常时等待1分钟
        finally:
            # 确保清理资源
            session = self._group_sessions.pop(group_id, None)
            if session:
                session.end_time = datetime.now().isoformat()
                await self.db_manager.save_learning_session_record(group_id, session.__dict__)
            logger.info(f"学习循环结束 for group {group_id}")

    @monitored
    async def _execute_learning_batch(self, group_id: str, relearn_mode: bool = False, from_force_learning: bool = False):
        """执行一个学习批次 - 集成强化学习

        Args:
            group_id: 群组ID
            relearn_mode: 重新学习模式，如果为True则忽略"已处理"标记，获取所有历史消息
        """
        try:
            batch_start_time = datetime.now()

            # 1. 获取消息（根据模式决定是否忽略"已处理"标记）
            if relearn_mode:
                # 重新学习模式：获取所有历史消息，忽略已处理标记
                logger.info(f" 重新学习模式：获取群组 {group_id} 的所有历史消息（忽略已处理标记）")
                # 使用 get_recent_raw_messages 获取所有历史消息（不考虑已处理标记）
                unprocessed_messages = await self.db_manager.get_recent_raw_messages(
                    group_id=group_id,
                    limit=self.batch_size * 10 # 重新学习时获取更多消息
                )
                logger.info(f"获取到 {len(unprocessed_messages) if unprocessed_messages else 0} 条历史消息用于重新学习")
            else:
                # 正常模式：只获取未处理的消息
                unprocessed_messages = await self.message_collector.get_unprocessed_messages(
                    limit=self.batch_size,
                    group_id=group_id,
                )

            if not unprocessed_messages:
                if relearn_mode:
                    logger.warning(f"群组 {group_id} 没有找到历史消息")
                else:
                    logger.debug("没有未处理的消息，跳过此批次")
                return

            logger.info(f"开始处理 {len(unprocessed_messages)} 条消息（relearn_mode={relearn_mode}）")
            
            # 2. 使用多维度分析器筛选消息
            filtered_messages = await self._filter_messages_with_context(unprocessed_messages)
            
            if not filtered_messages:
                logger.debug("没有通过筛选的消息")
                await self._mark_messages_processed(unprocessed_messages)
                return

            # 2.5 将筛选后的消息写入 FilteredMessage 表（供 WebUI 统计）
            await self._save_filtered_messages_for_stats(group_id, filtered_messages)

            # 3. 获取当前人格设置 (针对特定群组)
            current_persona = await self._get_current_persona(group_id)
            
            # 4-7. 分析风格并生成候选人格更新；失败时保留统计和风格学习降级记录
            from ...core.interfaces import AnalysisResult

            style_analysis = await self._execute_style_analysis_background(group_id, filtered_messages)
            if not getattr(style_analysis, "success", False):
                logger.warning(
                    f"风格分析失败，使用统计摘要继续学习批次: {getattr(style_analysis, 'error', '')}"
                )
                style_analysis = AnalysisResult(
                    success=True,
                    confidence=0.7,
                    data=self._build_fallback_style_analysis_data(filtered_messages),
                    timestamp=time.time()
                )

            updated_persona = await self._generate_updated_persona_with_refinement(
                group_id,
                current_persona or {"prompt": "默认人格"},
                style_analysis,
            )
            ml_tuning_info = None
            
            # 8. 质量监控评估
            # 确保参数不为None，提供默认值
            if current_persona is None:
                current_persona = {"prompt": "默认人格"}
                logger.warning("current_persona为None，使用默认值")
            
            if updated_persona is None:
                updated_persona = current_persona.copy()
                logger.warning("updated_persona为None，使用current_persona的副本")
                
            quality_metrics = await self.quality_monitor.evaluate_learning_batch(
                current_persona,
                updated_persona,
                filtered_messages
            )
            quality_score = self._resolve_learning_quality_score(quality_metrics, filtered_messages)
            self._patch_zero_quality_metric(quality_metrics, quality_score)

            # 9. 应用学习更新（对话风格学习不判断质量直接应用，人格学习加入审查）
            # 注意：对话风格（表达模式）学习总是成功，人格学习在_apply_learning_updates中会加入审查
            # 传递 relearn_mode 和 ml_tuning_info 参数
            await self._apply_learning_updates(group_id, style_analysis, filtered_messages, current_persona, updated_persona, quality_metrics, relearn_mode=relearn_mode, ml_tuning_info=ml_tuning_info)
            logger.info(f"学习更新已应用（对话风格学习已完成，人格学习已加入审查），质量得分: {quality_score:.3f} for group {group_id}")
            success = True # 对话风格学习总是成功
            
            # 10. 【新增】保存学习性能记录
            # 正确处理 AnalysisResult 对象进行序列化
            style_analysis_for_db = style_analysis.data if hasattr(style_analysis, 'data') else style_analysis
            await self.db_manager.save_learning_performance_record(group_id, {
                'session_id': self._group_sessions[group_id].session_id if group_id in self._group_sessions else '',
                'timestamp': time.time(),
                'quality_score': quality_score,
                'learning_time': (datetime.now() - batch_start_time).total_seconds(),
                'success': success,
                'successful_pattern': json.dumps(style_analysis_for_db, default=self._json_serializer),
                'failed_pattern': '' # 对话风格学习总是成功，不记录失败
            })
            
            # 11. 标记消息为已处理
            await self._mark_messages_processed(unprocessed_messages)
            
            # 12. 更新学习会话统计并持久化
            group_session = self._group_sessions.get(group_id)
            if group_session:
                group_session.messages_processed += len(unprocessed_messages)
                group_session.filtered_messages += len(filtered_messages)
                group_session.quality_score = quality_score
                group_session.success = success
                await self.db_manager.save_learning_session_record(group_id, group_session.__dict__)
            
            # 13. 【新增】学习成功后更新增量内容到system_prompt
            if success:
                try:
                    # 使用回调函数进行增量更新，降低耦合性
                    if self.update_system_prompt_callback:
                        await self.update_system_prompt_callback(group_id)
                        logger.info(f"定时更新增量内容完成: {group_id}")
                    else:
                        logger.debug("未设置增量更新回调函数，跳过增量内容更新")
                except Exception as e:
                    logger.error(f"定时增量内容更新失败: {e}")
            
            # 14. 定期执行策略优化
            if success and group_session and group_session.messages_processed % 500 == 0:
                try:
                    await self.ml_analyzer.reinforcement_strategy_optimization(group_id)
                    logger.info("执行了策略优化检查")
                except Exception as e:
                    logger.error(f"策略优化失败: {e}")
            
            # 记录批次耗时
            batch_duration = (datetime.now() - batch_start_time).total_seconds()
            logger.info(f"学习批次完成，耗时: {batch_duration:.2f}秒")
            
        except Exception as e:
            logger.error(f"学习批次执行失败: {e}")
            raise LearningError(f"学习批次执行失败: {str(e)}")

    @monitored
    async def _execute_learning_batch_background(self, group_id: str):
        """在后台执行学习批次 - 使用线程池避免阻塞主协程"""
        try:
            batch_start_time = datetime.now()
            
            # 1. 异步获取数据
            unprocessed_messages = await self.message_collector.get_unprocessed_messages(
                limit=self.batch_size,
                group_id=group_id,
            )
            
            if not unprocessed_messages:
                logger.debug("没有未处理的消息，跳过此批次")
                return
            
            logger.info(f"开始后台处理 {len(unprocessed_messages)} 条消息")
            
            # 2. 并行执行筛选和获取人格
            filtered_messages, current_persona = await asyncio.gather(
                self._filter_messages_with_context(unprocessed_messages),
                self._get_current_persona(group_id),
                return_exceptions=True
            )
            
            # 处理异常结果
            if isinstance(filtered_messages, Exception):
                logger.error(f"消息筛选异常: {filtered_messages}")
                filtered_messages = []
            
            if isinstance(current_persona, Exception):
                logger.error(f"获取人格异常: {current_persona}")
                current_persona = {}
            
            if not filtered_messages:
                logger.debug("没有通过筛选的消息")
                await self._mark_messages_processed(unprocessed_messages)
                return

            await self._save_filtered_messages_for_stats(group_id, filtered_messages)

            # 3. 分析风格并生成候选人格更新；失败时保留统计和风格学习降级记录
            from ...core.interfaces import AnalysisResult

            style_analysis = await self._execute_style_analysis_background(group_id, filtered_messages)
            if not getattr(style_analysis, "success", False):
                logger.warning(
                    f"风格分析失败，使用统计摘要继续学习批次: {getattr(style_analysis, 'error', '')}"
                )
                style_analysis = AnalysisResult(
                    success=True,
                    confidence=0.7,
                    data=self._build_fallback_style_analysis_data(filtered_messages),
                    timestamp=time.time()
                )

            updated_persona = await self._generate_updated_persona_with_refinement(
                group_id,
                current_persona or {"prompt": "默认人格"},
                style_analysis,
            )

            # 4. 质量评估和应用更新
            await self._finalize_learning_batch(
                group_id, current_persona, updated_persona, filtered_messages,
                unprocessed_messages, batch_start_time, style_analysis # 传递 style_analysis
            )
            
        except Exception as e:
            logger.error(f"后台学习批次执行失败: {e}", exc_info=True)

    async def _execute_reinforcement_learning_background(self, group_id: str, filtered_messages, current_persona):
        """在后台执行强化学习"""
        if not self.config.enable_ml_analysis:
            return {}
        
        try:
            return await self.ml_analyzer.reinforcement_memory_replay(
                group_id, filtered_messages, current_persona
            )
        except Exception as e:
            logger.error(f"后台强化学习失败: {e}")
            return {}

    @monitored
    async def _execute_style_analysis_background(self, group_id: str, filtered_messages):
        """在后台执行风格分析"""
        from ...core.interfaces import AnalysisResult
        try:
            return await self.style_analyzer.analyze_conversation_style(group_id, filtered_messages)
        except Exception as e:
            logger.error(f"后台风格分析失败: {e}")
            return AnalysisResult(success=False, confidence=0.0, data={}, error=str(e))

    async def _execute_incremental_tuning_background(self, group_id: str, base_persona, incremental_updates):
        """在后台执行增量微调"""
        try:
            return await self.ml_analyzer.reinforcement_incremental_tuning(
                group_id, base_persona, incremental_updates
            )
        except Exception as e:
            logger.error(f"后台增量微调失败: {e}")
            return {}

    async def _finalize_learning_batch(self, group_id: str, current_persona, updated_persona,
                                     filtered_messages, unprocessed_messages, batch_start_time, style_analysis=None):
        """完成学习批次的最终处理

        Args:
            style_analysis: 风格分析结果，用于保存对话风格学习记录
        """
        try:
            # 质量监控评估
            # 确保参数不为None，提供默认值
            if current_persona is None:
                current_persona = {"prompt": "默认人格"}
                logger.warning("_finalize_learning_batch: current_persona为None，使用默认值")

            if updated_persona is None:
                updated_persona = current_persona.copy()
                logger.warning("_finalize_learning_batch: updated_persona为None，使用current_persona的副本")

            quality_metrics = await self.quality_monitor.evaluate_learning_batch(
                current_persona, updated_persona, filtered_messages
            )
            quality_score = self._resolve_learning_quality_score(quality_metrics, filtered_messages)
            self._patch_zero_quality_metric(quality_metrics, quality_score)

            # 应用学习更新（对话风格学习不判断质量直接应用，人格学习加入审查）
            # 传递 style_analysis 用于保存对话风格学习记录
            # 如果 style_analysis 为 None，创建一个空的 AnalysisResult
            from ...core.interfaces import AnalysisResult
            if style_analysis is None:
                style_analysis = AnalysisResult(success=True, confidence=0.5, data={})
            await self._apply_learning_updates(group_id, style_analysis, filtered_messages, current_persona, updated_persona, quality_metrics, relearn_mode=False, ml_tuning_info=None)
            logger.info(f"学习更新已应用（对话风格学习已完成，人格学习已加入审查），质量得分: {quality_score:.3f} for group {group_id}")
            success = True # 对话风格学习总是成功

            # 记录学习批次到数据库（使用 ORM）
            try:
                batch_name = f"batch_{group_id}_{int(time.time())}"
                start_time = batch_start_time.timestamp()
                end_time = time.time()

                async with self.db_manager.get_session() as session:
                    from ...models.orm.learning import LearningBatch
                    batch_record = LearningBatch(
                        batch_id=batch_name,
                        batch_name=batch_name,
                        group_id=group_id,
                        start_time=start_time,
                        end_time=end_time,
                        quality_score=quality_score,
                        processed_messages=len(unprocessed_messages),
                        message_count=len(unprocessed_messages),
                        filtered_count=len(filtered_messages),
                        success=success,
                    )
                    session.add(batch_record)
                    await session.commit()
                    logger.debug(f"学习批次记录已保存: {batch_name}")
            except Exception as e:
                logger.debug(f"无法记录学习批次（不影响学习功能）: {e}")

            # 保存学习性能记录
            await self.db_manager.save_learning_performance_record(group_id, {
                'session_id': self._group_sessions[group_id].session_id if group_id in self._group_sessions else '',
                'timestamp': time.time(),
                'quality_score': quality_score,
                'learning_time': end_time - start_time,
                'success': success,
                'successful_pattern': json.dumps({}),
                'failed_pattern': '' # 对话风格学习总是成功，不记录失败
            })
            
            # 标记消息为已处理
            await self._mark_messages_processed(unprocessed_messages)
            
            # 更新会话统计
            bg_session = self._group_sessions.get(group_id)
            if bg_session:
                bg_session.messages_processed += len(unprocessed_messages)
                bg_session.filtered_messages += len(filtered_messages)
                bg_session.quality_score = quality_score
                bg_session.success = success
                await self.db_manager.save_learning_session_record(group_id, bg_session.__dict__)

            # 定期执行策略优化 - 不阻塞主流程
            if success and bg_session and bg_session.messages_processed % 500 == 0:
                asyncio.create_task(self._execute_strategy_optimization_background(group_id))
            
            batch_duration = end_time - start_time
            logger.info(f"后台学习批次完成，耗时: {batch_duration:.2f}秒")
            
        except Exception as e:
            logger.error(f"完成学习批次失败: {e}")

    async def _execute_strategy_optimization_background(self, group_id: str):
        """在后台执行策略优化，不阻塞主流程"""
        try:
            await self.ml_analyzer.reinforcement_strategy_optimization(group_id)
            logger.info("后台策略优化完成")
        except Exception as e:
            logger.error(f"后台策略优化失败: {e}")

    @monitored
    async def _generate_updated_persona_with_refinement(self, group_id: str, current_persona: Dict[str, Any], style_analysis: Any) -> Dict[str, Any]:
        """使用提炼模型生成更新后的人格（兼容转发）"""
        return await self._get_persona_learning_module().generate_updated_persona_with_refinement(
            group_id,
            current_persona,
            style_analysis,
        )

    def _json_serializer(self, obj):
        """自定义JSON序列化器，处理不能直接序列化的对象"""
        try:
            # 检查对象的类型名称，避免循环导入
            class_name = obj.__class__.__name__
            
            if class_name == 'StyleProfile':
                # 将StyleProfile对象转换为字典
                if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
                    return obj.to_dict()
                elif hasattr(obj, '__dict__'):
                    return obj.__dict__
            elif hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
                # 对于有to_dict方法的对象
                return obj.to_dict()
            elif hasattr(obj, '__dict__'):
                # 对于其他dataclass或对象，尝试使用__dict__
                return obj.__dict__
            else:
                # 如果都不行，转换为字符串
                return str(obj)
        except Exception as e:
            logger.warning(f"JSON序列化对象时出现错误: {e}, 对象类型: {type(obj)}, 转换为字符串")
            return str(obj)

    @monitored
    async def _filter_messages_with_context(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对话风格学习不需要筛选，直接返回所有消息"""
        messages = filter_learning_messages(messages)

        # 对话风格学习不需要LLM筛选，直接学习所有原始消息
        logger.info(f"对话风格学习模式：直接学习 {len(messages)} 条原始消息（跳过LLM筛选）")

        # 为每条消息添加默认的相关性评分
        for message in messages:
            message['relevance_score'] = 1.0 # 默认完全相关
            message['filter_reason'] = 'style_learning_no_filter'

        return messages

    @monitored
    async def _get_current_persona(self, group_id: str) -> Dict[str, Any]:
        """获取当前人格设置 (针对特定群组，兼容转发)"""
        return await self._get_persona_learning_module().get_current_persona(group_id)

    async def _generate_updated_persona(self, group_id: str, current_persona: Dict[str, Any], style_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成更新后的人格 - 直接在原有文本后面追加增量学习内容（兼容转发）"""
        return await self._get_persona_learning_module().generate_updated_persona(
            group_id,
            current_persona,
            style_analysis,
        )

    @monitored
    async def _apply_learning_updates(self, group_id: str, style_analysis: Dict[str, Any], messages: List[Dict[str, Any]],
                                     current_persona: Dict[str, Any] = None, updated_persona: Dict[str, Any] = None,
                                     quality_metrics = None, relearn_mode: bool = False, ml_tuning_info: Dict[str, Any] = None):
        """应用学习更新，并创建人格学习审查记录和风格学习记录。"""
        try:
            await self._save_style_learning_record(group_id, style_analysis, messages, quality_metrics)

            await self._get_persona_learning_module().apply_persona_learning(
                group_id,
                style_analysis,
                messages,
                current_persona=current_persona,
                updated_persona=updated_persona,
                quality_metrics=quality_metrics,
                relearn_mode=relearn_mode,
                ml_tuning_info=ml_tuning_info,
            )

            if group_id in self._group_sessions:
                self._group_sessions[group_id].style_updates += 1

        except Exception as e:
            logger.error(f"应用学习更新失败 for group {group_id}: {e}")

    async def _mark_messages_processed(self, messages: List[Dict[str, Any]]):
        """标记消息为已处理"""
        message_ids = [msg['id'] for msg in messages if 'id' in msg]
        if message_ids:
            await self.message_collector.mark_messages_processed(message_ids)

    async def get_learning_status(self, group_id: str = None) -> Dict[str, Any]:
        """获取学习状态"""
        if group_id:
            # 获取特定群组的状态
            return {
                'learning_active': self.learning_active.get(group_id, False),
                'group_id': group_id,
                'current_session': self._group_sessions[group_id].__dict__ if group_id in self._group_sessions else None,
                'total_sessions': len(self.learning_sessions),
                'statistics': await self.message_collector.get_statistics(),
                'quality_report': await self.quality_monitor.get_quality_report(),
                'last_update': datetime.now().isoformat()
            }
        else:
            return {
                'learning_active_groups': {gid: active for gid, active in self.learning_active.items()},
                'active_groups_count': sum(1 for active in self.learning_active.values() if active),
                'group_sessions': {gid: s.__dict__ for gid, s in self._group_sessions.items()},
                'total_sessions': len(self.learning_sessions),
                'statistics': await self.message_collector.get_statistics(),
                'quality_report': await self.quality_monitor.get_quality_report(),
                'last_update': datetime.now().isoformat()
            }

    async def get_learning_insights(self) -> Dict[str, Any]:
        """获取学习洞察"""
        try:
            # 获取风格趋势
            style_trends = await self.style_analyzer.get_style_trends()
            
            # 获取用户分析（示例用户）
            user_insights = {}
            if self.multidimensional_analyzer.user_profiles:
                sample_user_id = list(self.multidimensional_analyzer.user_profiles.keys())
                user_insights = await self.multidimensional_analyzer.get_user_insights(sample_user_id)
            
            # 获取社交图谱
            social_graph = await self.multidimensional_analyzer.export_social_graph()
            
            return {
                'style_trends': style_trends,
                'user_insights_sample': user_insights,
                'social_graph_summary': {
                    'total_nodes': len(social_graph.get('nodes', [])),
                    'total_edges': len(social_graph.get('edges', [])),
                    'statistics': social_graph.get('statistics', {})
                },
                'learning_performance': {
                    'successful_sessions': len([s for s in self.learning_sessions if s.success]),
                    'average_quality_score': sum(s.quality_score for s in self.learning_sessions) / 
                                           max(len(self.learning_sessions), 1),
                    'total_messages_processed': sum(s.messages_processed for s in self.learning_sessions)
                }
            }
            
        except Exception as e:
            logger.error(f"获取学习洞察失败: {e}")
            return {"error": str(e)}

    async def stop(self):
        """停止服务"""
        try:
            await self.stop_learning() # 停止所有群组的学习
            logger.info("渐进式学习服务已停止")
            return True
        except Exception as e:
            logger.error(f"停止渐进式学习服务失败: {e}")
            return False

    async def _save_style_learning_record(self, group_id: str, style_analysis: Dict[str, Any],
                                         messages: List[Dict[str, Any]], quality_metrics=None):
        """保存对话风格学习记录（兼容转发）。"""
        await self._get_expression_learning_module().save_style_learning_record(
            group_id,
            style_analysis,
            messages,
            quality_metrics,
        )

    @staticmethod
    def _filter_expression_patterns(patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove command/system-derived pairs before saving style samples."""
        return ExpressionLearningModule.filter_expression_patterns(patterns)

    def _build_few_shots_from_patterns(self, patterns: List[Dict[str, Any]]) -> str:
        """从表达模式构建 few-shots 内容。"""
        return self._get_expression_learning_module().build_few_shots_from_patterns(
            patterns
        )

    async def _merge_bot_messages_for_pairs(
        self, group_id: str, user_messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge user messages with bot messages from DB to form a timeline."""
        return await self._get_expression_learning_module().merge_bot_messages_for_pairs(
            group_id,
            user_messages,
        )

    @staticmethod
    def _extract_fewshot_pairs_from_merged(
        merged: List[Dict[str, Any]], group_id: str
    ) -> List[Dict[str, Any]]:
        """Extract user->bot conversation pairs from a merged message timeline."""
        return ExpressionLearningModule.extract_fewshot_pairs_from_merged(
            merged,
            group_id,
        )

    async def _save_expression_patterns(self, group_id: str, patterns: List[Dict[str, Any]]):
        """保存表达模式到 expression_patterns 表。"""
        await self._get_expression_learning_module().save_expression_patterns(
            group_id,
            patterns,
        )
