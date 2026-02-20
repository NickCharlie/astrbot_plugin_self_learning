"""
渐进式学习服务 - 协调各个组件实现智能自适应学习
"""
import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.star import Context

from ...config import PluginConfig
from ...constants import UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING
from ...exceptions import LearningError

from ...utils.json_utils import safe_parse_llm_json, clean_llm_json_response

from ..database import DatabaseManager


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

    async def _execute_learning_batch(self, group_id: str, relearn_mode: bool = False):
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
                    limit=self.batch_size
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
            
            # 3. 获取当前人格设置 (针对特定群组)
            current_persona = await self._get_current_persona(group_id)
            
            # 4. 【新增】强化学习记忆重放 - 在force_learning中减少调用频率
            if self.config.enable_ml_analysis:
                try:
                    # 检查是否为force_learning调用，如果是则跳过记忆重放避免无限循环
                    import inspect
                    current_frame = inspect.currentframe()
                    call_stack = []
                    frame = current_frame
                    while frame:
                        call_stack.append(frame.f_code.co_name)
                        frame = frame.f_back
                    
                    if 'force_learning_command' in call_stack:
                        logger.debug("force_learning中跳过强化学习记忆重放，避免无限循环")
                    else:
                        reinforcement_result = await self.ml_analyzer.reinforcement_memory_replay(
                            group_id, filtered_messages, current_persona
                        )
                        
                        if reinforcement_result and reinforcement_result.get('optimization_strategy'):
                            # 根据强化学习结果调整学习参数
                            learning_weight = reinforcement_result.get('optimization_strategy', {}).get('learning_weight', 1.0)
                            confidence_threshold = reinforcement_result.get('optimization_strategy', {}).get('confidence_threshold', self.config.confidence_threshold)
                            
                            # 动态调整筛选阈值
                            if confidence_threshold != self.config.confidence_threshold:
                                logger.info(f"根据强化学习调整置信度阈值: {self.config.confidence_threshold} -> {confidence_threshold}")
                                # 重新筛选消息（如果阈值提高了）
                                if confidence_threshold > self.config.confidence_threshold:
                                    filtered_messages = [msg for msg in filtered_messages 
                                                       if msg.get('relevance_score', 0) >= confidence_threshold]
                                    
                except Exception as e:
                    logger.error(f"强化学习记忆重放失败: {e}")
            
            # 5. 使用风格分析器深度分析
            style_analysis = await self.style_analyzer.analyze_conversation_style(group_id, filtered_messages)
            
            # 6. 【增强】使用提炼模型生成更新后的人格
            updated_persona = await self._generate_updated_persona_with_refinement(group_id, current_persona, style_analysis)

            # 7. 【新增】强化学习增量微调
            ml_tuning_info = None # 用于记录强化学习调优信息
            if self.config.enable_ml_analysis and updated_persona:
                try:
                    tuning_result = await self.ml_analyzer.reinforcement_incremental_tuning(
                        group_id, current_persona, updated_persona
                    )

                    if tuning_result and tuning_result.get('updated_persona'):
                        # 使用强化学习优化后的人格
                        final_persona = tuning_result.get('updated_persona')

                        # 检查 updated_persona 类型，确保是字典才调用 update
                        if not isinstance(updated_persona, dict):
                            logger.error(f"updated_persona 类型不正确，预期为 dict 但得到 {type(updated_persona)}，跳过强化学习调优")
                        elif not isinstance(final_persona, dict):
                            logger.error(f"final_persona 类型不正确，预期为 dict 但得到 {type(final_persona)}，跳过强化学习调优")
                        else:
                            # 检测是否使用了保守融合策略
                            original_prompt_length = len(current_persona.get('prompt', ''))
                            new_prompt_length = len(final_persona.get('prompt', ''))
                            used_conservative_fusion = new_prompt_length < original_prompt_length * 0.8

                            updated_persona.update(final_persona)

                            # 保存强化学习调优信息，供审查记录使用
                            ml_tuning_info = {
                                'applied': True,
                                'expected_improvement': tuning_result.get('performance_prediction', {}).get('expected_improvement', 0),
                                'used_conservative_fusion': used_conservative_fusion,
                                'original_length': original_prompt_length,
                                'tuned_length': new_prompt_length
                            }

                            logger.info(f"应用强化学习优化后的人格，预期改进: {ml_tuning_info['expected_improvement']}" +
                                      (f"，使用保守融合策略" if used_conservative_fusion else ""))

                except Exception as e:
                    logger.error(f"强化学习增量微调失败: {e}")
            
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

            # 9. 应用学习更新（对话风格学习不判断质量直接应用，人格学习加入审查）
            # 注意：对话风格（表达模式）学习总是成功，人格学习在_apply_learning_updates中会加入审查
            # 传递 relearn_mode 和 ml_tuning_info 参数
            await self._apply_learning_updates(group_id, style_analysis, filtered_messages, current_persona, updated_persona, quality_metrics, relearn_mode=relearn_mode, ml_tuning_info=ml_tuning_info)
            logger.info(f"学习更新已应用（对话风格学习已完成，人格学习已加入审查），质量得分: {quality_metrics.consistency_score:.3f} for group {group_id}")
            success = True # 对话风格学习总是成功
            
            # 10. 【新增】保存学习性能记录
            # 正确处理 AnalysisResult 对象进行序列化
            style_analysis_for_db = style_analysis.data if hasattr(style_analysis, 'data') else style_analysis
            await self.db_manager.save_learning_performance_record(group_id, {
                'session_id': self._group_sessions[group_id].session_id if group_id in self._group_sessions else '',
                'timestamp': time.time(),
                'quality_score': quality_metrics.consistency_score,
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
                group_session.quality_score = quality_metrics.consistency_score
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

    async def _execute_learning_batch_background(self, group_id: str):
        """在后台执行学习批次 - 使用线程池避免阻塞主协程"""
        try:
            batch_start_time = datetime.now()
            
            # 1. 异步获取数据
            unprocessed_messages = await self.message_collector.get_unprocessed_messages(
                limit=self.batch_size
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
            
            # 3. 并行执行强化学习和风格分析
            reinforcement_result, style_analysis = await asyncio.gather(
                self._execute_reinforcement_learning_background(group_id, filtered_messages, current_persona),
                self._execute_style_analysis_background(group_id, filtered_messages),
                return_exceptions=True
            )
            
            # 处理异常结果
            if isinstance(reinforcement_result, Exception):
                logger.error(f"强化学习异常: {reinforcement_result}")
                reinforcement_result = {}
            
            if isinstance(style_analysis, Exception):
                logger.error(f"风格分析异常: {style_analysis}")
                style_analysis = {}
            
            # 4. 动态调整学习参数（基于强化学习结果）
            if reinforcement_result and reinforcement_result.get('optimization_strategy'):
                confidence_threshold = reinforcement_result.get('optimization_strategy', {}).get('confidence_threshold', self.config.confidence_threshold)
                if confidence_threshold > self.config.confidence_threshold:
                    filtered_messages = [msg for msg in filtered_messages 
                                       if msg.get('relevance_score', 0) >= confidence_threshold]
                    logger.info(f"根据强化学习调整置信度阈值: {self.config.confidence_threshold} -> {confidence_threshold}")
            
            # 5. 使用提炼模型生成更新后的人格
            updated_persona = await self._generate_updated_persona_with_refinement(
                group_id, current_persona, style_analysis
            )
            
            # 6. 强化学习增量微调
            if self.config.enable_ml_analysis and updated_persona:
                tuning_result = await self._execute_incremental_tuning_background(
                    group_id, current_persona, updated_persona
                )
                if tuning_result and tuning_result.get('updated_persona'):
                    # 检查 updated_persona 类型，确保是字典才调用 update
                    if isinstance(updated_persona, dict):
                        updated_persona.update(tuning_result.get('updated_persona'))
                        logger.info(f"应用强化学习优化，预期改进: {tuning_result.get('performance_prediction', {}).get('expected_improvement', 0)}")
                    else:
                        logger.warning(f"updated_persona 类型不正确，预期为 dict 但得到 {type(updated_persona)}，跳过强化学习调优")
            
            # 7. 质量评估和应用更新
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

            # 应用学习更新（对话风格学习不判断质量直接应用，人格学习加入审查）
            # 传递 style_analysis 用于保存对话风格学习记录
            # 如果 style_analysis 为 None，创建一个空的 AnalysisResult
            from ...core.interfaces import AnalysisResult
            if style_analysis is None:
                style_analysis = AnalysisResult(success=True, confidence=0.5, data={})
            await self._apply_learning_updates(group_id, style_analysis, filtered_messages, current_persona, updated_persona, quality_metrics, relearn_mode=False, ml_tuning_info=None)
            logger.info(f"学习更新已应用（对话风格学习已完成，人格学习已加入审查），质量得分: {quality_metrics.consistency_score:.3f} for group {group_id}")
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
                        quality_score=quality_metrics.consistency_score,
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
                'quality_score': quality_metrics.consistency_score,
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
                bg_session.quality_score = quality_metrics.consistency_score
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

    async def _generate_updated_persona_with_refinement(self, group_id: str, current_persona: Dict[str, Any], style_analysis: Any) -> Dict[str, Any]:
        """使用提炼模型生成更新后的人格"""
        try:
            # 正确处理AnalysisResult对象和字典类型
            from ...core.interfaces import AnalysisResult
            
            if isinstance(style_analysis, AnalysisResult):
                # 如果是AnalysisResult对象，提取data属性
                analysis_data = style_analysis.data if style_analysis.data else {}
                logger.debug(f"从AnalysisResult提取data: success={style_analysis.success}, confidence={style_analysis.confidence}")
            elif isinstance(style_analysis, dict):
                analysis_data = style_analysis
                logger.debug("使用字典形式的style_analysis")
            elif hasattr(style_analysis, 'data'):
                # 兼容其他具有data属性的对象
                analysis_data = style_analysis.data if style_analysis.data else {}
                logger.debug(f"从对象提取data属性: {type(style_analysis)}")
            else:
                analysis_data = {}
                logger.warning(f"style_analysis类型不正确: {type(style_analysis)}, 使用空字典")
            
            # 使用多维度分析器的框架适配器生成人格更新
            if hasattr(self.multidimensional_analyzer, 'llm_adapter') and self.multidimensional_analyzer.llm_adapter:
                llm_adapter = self.multidimensional_analyzer.llm_adapter
                
                if llm_adapter.has_refine_provider() and llm_adapter.providers_configured >= 2:
                    # 准备输入数据
                    current_persona_json = json.dumps(current_persona, ensure_ascii=False, indent=2, default=self._json_serializer)
                    style_analysis_json = json.dumps(analysis_data, ensure_ascii=False, indent=2, default=self._json_serializer)
                    
                    # 调用框架适配器
                    response = await llm_adapter.refine_chat_completion(
                        prompt=self.prompts.PROGRESSIVE_LEARNING_GENERATE_UPDATED_PERSONA_PROMPT.format(
                            current_persona_json=current_persona_json,
                            style_analysis_json=style_analysis_json
                        ),
                        temperature=0.6
                    )
                    
                    if response:
                        # 清理响应文本，移除markdown标识符（使用统一的json_utils工具）
                        clean_response = clean_llm_json_response(response)

                        try:
                            updated_persona = safe_parse_llm_json(clean_response)
                            logger.info("使用提炼模型成功生成更新后的人格")
                            return updated_persona
                        except json.JSONDecodeError as e:
                            logger.error(f"提炼模型返回的JSON格式不正确: {e}, 响应: {clean_response}")
                            return await self._generate_updated_persona(group_id, current_persona, style_analysis)
                else:
                    logger.warning("提炼模型Provider未配置，使用传统方法生成人格")
                    return await self._generate_updated_persona(group_id, current_persona, style_analysis)
            else:
                logger.warning("框架适配器未找到，使用传统方法生成人格")
                return await self._generate_updated_persona(group_id, current_persona, style_analysis)
            
        except Exception as e:
            logger.error(f"使用提炼模型生成人格失败: {e}")
            return await self._generate_updated_persona(group_id, current_persona, style_analysis)

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

    async def _filter_messages_with_context(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对话风格学习不需要筛选，直接返回所有消息"""

        # 对话风格学习不需要LLM筛选，直接学习所有原始消息
        logger.info(f"对话风格学习模式：直接学习 {len(messages)} 条原始消息（跳过LLM筛选）")

        # 为每条消息添加默认的相关性评分
        for message in messages:
            message['relevance_score'] = 1.0 # 默认完全相关
            message['filter_reason'] = 'style_learning_no_filter'

        return messages

    async def _get_current_persona(self, group_id: str) -> Dict[str, Any]:
        """获取当前人格设置 (针对特定群组)"""
        try:
            # 通过 PersonaManagerService 获取当前人格
            persona = await self.persona_manager.get_current_persona(group_id)
            if persona:
                return persona

            # 如果没有特定群组的人格，尝试从框架获取默认人格
            if hasattr(self.context, 'persona_manager') and self.context.persona_manager:
                try:
                    default_persona = await self.context.persona_manager.get_default_persona_v3(self._resolve_umo(group_id))
                    if default_persona:
                        return {
                            'prompt': default_persona.get('prompt', '默认人格'),
                            'name': default_persona.get('name', 'default'),
                            'style_parameters': {},
                            'last_updated': datetime.now().isoformat()
                        }
                except Exception as e:
                    logger.warning(f"从框架获取默认人格失败: {e}")

            # 如果都失败，返回默认结构
            return {
                'prompt': "默认人格",
                'name': 'default',
                'style_parameters': {},
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取当前人格失败 for group {group_id}: {e}")
            return {'prompt': '默认人格', 'name': 'default', 'style_parameters': {}}

    async def _generate_updated_persona(self, group_id: str, current_persona: Dict[str, Any], style_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成更新后的人格 - 直接在原有文本后面追加增量学习内容"""
        try:
            # 使用新版框架API获取当前人格
            if not hasattr(self.context, 'persona_manager') or not self.context.persona_manager:
                logger.warning(f"无法获取PersonaManager for group {group_id}")
                return current_persona

            default_persona = await self.context.persona_manager.get_default_persona_v3(self._resolve_umo(group_id))
            if not default_persona:
                logger.warning(f"无法获取当前人格 for group {group_id}")
                return current_persona

            # 获取原有人格文本
            original_prompt = default_persona.get('prompt', '')

            # 构建增量学习内容
            learning_content = []

            # 正确处理AnalysisResult对象和字典类型
            from ...core.interfaces import AnalysisResult

            if isinstance(style_analysis, AnalysisResult):
                # 如果是AnalysisResult对象，提取data属性
                analysis_data = style_analysis.data if style_analysis.data else {}
                logger.debug(f"从AnalysisResult提取data: success={style_analysis.success}, confidence={style_analysis.confidence}")
            elif isinstance(style_analysis, dict):
                analysis_data = style_analysis
                logger.debug("使用字典形式的style_analysis")
            elif hasattr(style_analysis, 'data'):
                # 兼容其他具有data属性的对象
                analysis_data = style_analysis.data if style_analysis.data else {}
                logger.debug(f"从对象提取data属性: {type(style_analysis)}")
            else:
                analysis_data = {}
                logger.warning(f"style_analysis类型不正确: {type(style_analysis)}, 使用空字典")

            # 修复：从实际的 style_analysis 结构中提取内容
            # 优先提取 enhanced_prompt 和 learning_insights（如果有）
            if 'enhanced_prompt' in analysis_data:
                learning_content.append(analysis_data['enhanced_prompt'])
                logger.debug("找到 enhanced_prompt 字段")

            if 'learning_insights' in analysis_data:
                insights = analysis_data['learning_insights']
                if insights:
                    learning_content.append(insights)
                    logger.debug("找到 learning_insights 字段")

            # 新增：从 style_analysis 字段提取内容（StyleAnalyzer返回的结构）
            if not learning_content and 'style_analysis' in analysis_data:
                style_report = analysis_data['style_analysis']
                if isinstance(style_report, dict):
                    # 提取关键的风格分析内容
                    extracted_parts = []

                    # 提取文本风格描述
                    if 'text_style' in style_report:
                        extracted_parts.append(f"文本风格: {style_report['text_style']}")

                    # 提取表达特点
                    if 'expression_features' in style_report:
                        features = style_report['expression_features']
                        if isinstance(features, list):
                            extracted_parts.append(f"表达特点: {', '.join(features)}")
                        elif isinstance(features, str):
                            extracted_parts.append(f"表达特点: {features}")

                    # 提取语气倾向
                    if 'tone' in style_report:
                        extracted_parts.append(f"语气倾向: {style_report['tone']}")

                    # 提取话题偏好
                    if 'topics' in style_report:
                        topics = style_report['topics']
                        if isinstance(topics, list):
                            extracted_parts.append(f"话题偏好: {', '.join(topics)}")
                        elif isinstance(topics, str):
                            extracted_parts.append(f"话题偏好: {topics}")

                    if extracted_parts:
                        learning_content.append("【对话风格学习结果】\n" + "\n".join(extracted_parts))
                        logger.debug(f"从 style_analysis 提取了 {len(extracted_parts)} 个风格特征")

            # 新增：如果还是没有内容，从 style_profile 提取
            if not learning_content and 'style_profile' in analysis_data:
                style_profile = analysis_data['style_profile']
                if isinstance(style_profile, dict):
                    profile_parts = []

                    # 提取语气强度
                    if 'tone_intensity' in style_profile:
                        profile_parts.append(f"语气强度: {style_profile['tone_intensity']:.2f}")

                    # 提取情感倾向
                    if 'sentiment' in style_profile:
                        profile_parts.append(f"情感倾向: {style_profile['sentiment']:.2f}")

                    # 提取词汇丰富度
                    if 'vocabulary_richness' in style_profile:
                        profile_parts.append(f"词汇丰富度: {style_profile['vocabulary_richness']:.2f}")

                    if profile_parts:
                        learning_content.append("【风格量化指标】\n" + "\n".join(profile_parts))
                        logger.debug(f"从 style_profile 提取了 {len(profile_parts)} 个量化指标")

            # 新增：如果还是没有内容，尝试提取任何有用的信息
            if not learning_content:
                # 尝试从顶层提取任何看起来有用的字段
                useful_fields = ['summary', 'description', 'analysis', 'insights', 'findings']
                for field in useful_fields:
                    if field in analysis_data and analysis_data[field]:
                        learning_content.append(f"【{field}】\n{analysis_data[field]}")
                        logger.debug(f"从顶层字段 {field} 提取了内容")
                        break

            # 直接在原有文本后面追加新内容
            if learning_content:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                new_content = f"\n\n【学习更新 - {timestamp}】\n" + "\n".join(learning_content)

                # 创建更新后的人格 (Personality是TypedDict)
                updated_persona = dict(default_persona)
                updated_persona['prompt'] = original_prompt + new_content
                updated_persona['last_updated'] = timestamp

                logger.info(f" 成功追加 {len(learning_content)} 项学习内容到人格 for group {group_id}")
                return updated_persona
            else:
                logger.warning(f" style_analysis中没有可提取的学习内容 for group {group_id}, 数据结构: {list(analysis_data.keys())}")
                # 即使没有学习内容，也返回一个副本以确保有updated_persona用于对比
                return dict(default_persona)

        except Exception as e:
            logger.error(f"生成更新人格失败 for group {group_id}: {e}", exc_info=True)
            return current_persona

    async def _apply_learning_updates(self, group_id: str, style_analysis: Dict[str, Any], messages: List[Dict[str, Any]],
                                     current_persona: Dict[str, Any] = None, updated_persona: Dict[str, Any] = None,
                                     quality_metrics = None, relearn_mode: bool = False, ml_tuning_info: Dict[str, Any] = None):
        """应用学习更新，并创建人格学习审查记录和风格学习记录

        Args:
            group_id: 群组ID
            style_analysis: 风格分析结果
            messages: 处理的消息列表
            current_persona: 当前人格
            updated_persona: 更新后的人格
            quality_metrics: 质量指标
            relearn_mode: 重新学习模式，为True时即使内容相同也创建审查记录
            ml_tuning_info: 强化学习调优信息（包含是否使用保守融合策略等）
        """
        try:
            # 处理可能的list类型参数
            if isinstance(current_persona, list):
                logger.warning(f"current_persona为list类型(长度{len(current_persona)})，转换为空字典")
                current_persona = {}

            if isinstance(updated_persona, list):
                logger.warning(f"updated_persona为list类型(长度{len(updated_persona)})，转换为空字典")
                updated_persona = {}

            # 1. 保存对话风格学习记录（不需要审查，直接保存）
            await self._save_style_learning_record(group_id, style_analysis, messages, quality_metrics)

            # 2. 更新人格prompt（通过 PersonaManagerService）
            logger.info(f"应用人格更新 for group {group_id}")

            # 正确处理 AnalysisResult 对象
            if hasattr(style_analysis, 'success'):
                # 这是一个 AnalysisResult 对象
                if not style_analysis.success:
                    logger.error(f"风格分析失败，跳过人格更新: {style_analysis.error}")
                    return

                # 使用 AnalysisResult 的 data 属性
                style_analysis_dict = style_analysis.data
                confidence = style_analysis.confidence
                logger.debug(f"使用 AnalysisResult 对象，置信度: {confidence:.3f}")
            elif isinstance(style_analysis, dict):
                # 向后兼容：如果传入的是字典
                style_analysis_dict = style_analysis
                confidence = style_analysis.get('confidence', 0.5)
                logger.debug("使用字典形式的 style_analysis（向后兼容）")
            else:
                logger.error(f"style_analysis 类型不正确: {type(style_analysis)}")
                return

            update_success = await self.persona_manager.update_persona(group_id, style_analysis_dict, messages)
            if not update_success:
                logger.error(f"通过 PersonaManagerService 更新人格失败 for group {group_id}")

            # 2. 创建人格学习审查记录（新增）
            # 重新学习模式：即使内容相同也创建审查记录（作为重新确认）
            # 正常模式：只在内容不同时创建审查记录
            should_create_review = False
            if relearn_mode:
                # 重新学习模式：总是创建审查记录
                should_create_review = bool(updated_persona and current_persona)
                if should_create_review:
                    # 检查是否有实质性变化
                    has_changes = updated_persona.get('prompt', '') != current_persona.get('prompt', '')
                    if has_changes:
                        logger.info(f" 重新学习模式：检测到人格变化，创建审查记录（group: {group_id}）")
                    else:
                        logger.info(f" 重新学习模式：未检测到人格变化，但仍创建审查记录供审核（group: {group_id}）")
                else:
                    logger.warning(f" 重新学习模式：无法创建审查记录 - updated_persona={bool(updated_persona)}, current_persona={bool(current_persona)}")
            elif updated_persona and current_persona and updated_persona.get('prompt') != current_persona.get('prompt'):
                # 正常模式：只在内容不同时创建
                should_create_review = True
                logger.info(f" 正常模式：检测到人格变化，创建审查记录（group: {group_id}）")
            else:
                logger.debug(f" 正常模式：人格未变化，跳过审查记录 - updated={bool(updated_persona)}, current={bool(current_persona)}, same_prompt={updated_persona.get('prompt') == current_persona.get('prompt') if updated_persona and current_persona else 'N/A'}")

            if should_create_review:
                try:
                    # 提取原人格和新人格的完整文本
                    original_prompt = current_persona.get('prompt', '')
                    new_prompt = updated_persona.get('prompt', '')

                    # 计算新增内容（用于单独标记）
                    if len(new_prompt) > len(original_prompt):
                        incremental_content = new_prompt[len(original_prompt):].strip()
                    else:
                        incremental_content = new_prompt

                    # 准备元数据（包含高亮信息）
                    metadata = {
                        "progressive_learning": True,
                        "message_count": len(messages),
                        "style_analysis_fields": list(style_analysis.data.keys()) if (hasattr(style_analysis, "data") and isinstance(style_analysis.data, dict)) else (list(style_analysis.keys()) if isinstance(style_analysis, dict) else []),
                        "original_prompt_length": len(original_prompt),
                        "new_prompt_length": len(new_prompt),
                        "incremental_content": incremental_content, # 单独记录增量内容，用于高亮
                        "incremental_start_pos": len(original_prompt), # 标记新增内容的起始位置
                        "relearn_mode": relearn_mode # 标记是否���重新学习模式
                    }

                    # 添加强化学习调优信息到元数据
                    if ml_tuning_info:
                        metadata['ml_tuning'] = ml_tuning_info

                    # 获取质量得分
                    confidence_score = quality_metrics.consistency_score if quality_metrics and hasattr(quality_metrics, 'consistency_score') else 0.5

                    # 构建 raw_analysis 说明（包含强化学习信息）
                    raw_analysis_parts = [f"基于{len(messages)}条消息的风格分析"]
                    if relearn_mode:
                        raw_analysis_parts.append("（重新学习）")
                    if ml_tuning_info and ml_tuning_info.get('applied'):
                        if ml_tuning_info.get('used_conservative_fusion'):
                            raw_analysis_parts.append(f"强化学习生成的prompt过短({ml_tuning_info['tuned_length']} vs {ml_tuning_info['original_length']})，采用保守融合策略")
                        else:
                            raw_analysis_parts.append(f"已应用强化学习优化，预期改进: {ml_tuning_info['expected_improvement']:.2%}")
                    raw_analysis = "；".join(raw_analysis_parts)

                    # 创建审查记录 - proposed_content 是完整的新人格（原人格 + 更新内容）
                    review_id = await self.db_manager.add_persona_learning_review(
                        group_id=group_id,
                        proposed_content=new_prompt, # 修改：proposed_content 是完整新人格
                        learning_source=UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING,
                        confidence_score=confidence_score,
                        raw_analysis=raw_analysis,
                        metadata=metadata,
                        original_content=original_prompt, # 原人格完整文本
                        new_content=new_prompt # 新人格完整文本（与proposed_content相同，保持一致性）
                    )

                    logger.info(f" 已创建人格学习审查记录 (ID: {review_id})，置信度: {confidence_score:.3f}")

                except Exception as review_error:
                    logger.error(f"创建人格学习审查记录失败: {review_error}", exc_info=True)
            else:
                logger.debug(f"人格未变化或缺少必要参数，跳过审查记录创建")

            # 3. 记录学习更新
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
        """
        保存对话风格学习记录（直接保存，不需要审查）

        Args:
            group_id: 群组ID
            style_analysis: 风格分析结果（可以为空，会基于消息创建简单记录）
            messages: 处理的消息列表
            quality_metrics: 质量指标
        """
        try:
            # 处理 AnalysisResult 对象，提取其 data 属性
            if style_analysis and hasattr(style_analysis, 'data'):
                style_analysis_dict = style_analysis.data
            elif isinstance(style_analysis, dict):
                style_analysis_dict = style_analysis
            else:
                style_analysis_dict = {}

            # 即使没有 style_analysis，也应该基于消息创建学习记录
            if not style_analysis_dict and not messages:
                logger.debug(f"群组 {group_id} 没有风格分析结果且没有消息，跳过风格学习记录保存")
                return

            # 1. 保存表达模式到 expression_patterns 表
            expression_patterns = style_analysis_dict.get('expression_patterns', [])
            if expression_patterns:
                await self._save_expression_patterns(group_id, expression_patterns)

            # 2. 构建 few_shots 内容
            few_shots_content = ''
            if style_analysis_dict:
                few_shots_content = style_analysis_dict.get('enhanced_prompt', '')
                if not few_shots_content and expression_patterns:
                    # 如果没有 enhanced_prompt，从 expression_patterns 构建
                    few_shots_content = self._build_few_shots_from_patterns(expression_patterns)

            # 如果没有 few_shots_content，从消息中构建简单的学习内容
            if not few_shots_content and messages:
                few_shots_content = f"基于 {len(messages)} 条对话消息的风格学习"

            # 3. 构建学习模式列表
            learned_patterns = []
            for pattern in expression_patterns[:10]: # 取前10个模式
                learned_patterns.append({
                    'situation': pattern.get('situation', ''),
                    'expression': pattern.get('expression', ''),
                    'weight': pattern.get('weight', 1.0),
                    'confidence': pattern.get('confidence', 0.8)
                })

            # 4. 获取质量得分
            confidence_score = quality_metrics.consistency_score if quality_metrics and hasattr(quality_metrics, 'consistency_score') else 0.75

            # 5. 构建描述
            pattern_count = len(learned_patterns) if learned_patterns else 0
            message_count = len(messages) if messages else 0
            description = f"群组 {group_id} 的对话风格学习结果（处理 {message_count} 条消息，提取 {pattern_count} 个表达模式）"

            # 6. 保存风格学习记录（使用 ORM）
            try:
                async with self.db_manager.get_session() as session:
                    from ...models.orm.learning import StyleLearningReview
                    from datetime import datetime

                    current_timestamp = time.time()

                    review = StyleLearningReview(
                        type='对话风格学习',
                        group_id=group_id,
                        timestamp=current_timestamp,
                        learned_patterns=json.dumps(learned_patterns, ensure_ascii=False),
                        few_shots_content=few_shots_content,
                        status='approved', # 直接批准，不需要审查
                        description=description,
                        reviewer_comment='自动批准',
                        review_time=current_timestamp,
                        created_at=datetime.fromtimestamp(current_timestamp), # 转换为datetime对象
                        updated_at=datetime.fromtimestamp(current_timestamp) # 转换为datetime对象
                    )

                    session.add(review)
                    await session.commit()
                    await session.refresh(review)

                    logger.info(f" 对话风格学习记录已保存 (ID: {review.id})，处理 {message_count} 条消息，提取 {pattern_count} 个模式")

            except Exception as e:
                logger.error(f"保存对话风格学习记录失败: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"保存风格学习记录失败: {e}", exc_info=True)

    def _build_few_shots_from_patterns(self, patterns: List[Dict[str, Any]]) -> str:
        """从表达模式构建 few-shots 内容"""
        few_shots = "*Here are few shots of dialogs, you need to imitate the tone of 'B' in the following dialogs to respond:\n"

        for i, pattern in enumerate(patterns[:5], 1): # 只取前5个
            situation = pattern.get('situation', '')
            expression = pattern.get('expression', '')
            if situation and expression:
                few_shots += f"A: {situation}\nB: {expression}\n\n"

        return few_shots.strip()

    async def _save_expression_patterns(self, group_id: str, patterns: List[Dict[str, Any]]):
        """
        保存表达模式到 expression_patterns 表

        Args:
            group_id: 群组ID
            patterns: 表达模式列表
        """
        try:
            if not patterns:
                return

            # 使用 ORM 保存表达模式
            async with self.db_manager.get_session() as session:
                from ...models.orm.expression import ExpressionPattern
                import time

                current_time = time.time()

                for pattern in patterns:
                    situation = pattern.get('situation', '').strip()
                    expression = pattern.get('expression', '').strip()

                    if not situation or not expression:
                        continue

                    # 创建表达模式记录（ExpressionPattern只有weight, last_active_time, create_time字段）
                    expr_pattern = ExpressionPattern(
                        group_id=group_id,
                        situation=situation,
                        expression=expression,
                        weight=float(pattern.get('weight', 1.0)),
                        last_active_time=current_time, # 使用last_active_time而不是confidence
                        create_time=current_time
                    )

                    session.add(expr_pattern)

                await session.commit()
                logger.info(f" 已保存 {len(patterns)} 个表达模式到数据库 (群组: {group_id})")

        except Exception as e:
            logger.error(f"保存表达模式失败: {e}", exc_info=True)
