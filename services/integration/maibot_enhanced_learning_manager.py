"""
MaiBot增强学习管理器 - 集成所有MaiBot功能的统一学习管理器
采用MaiBot的学习触发条件和协调机制
"""
import time
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from astrbot.api import logger

from ...core.interfaces import MessageData, ServiceLifecycle
from ...core.framework_llm_adapter import FrameworkLLMAdapter
from ...config import PluginConfig
from ...exceptions import SelfLearningError
from ..database import DatabaseManager
from ..analysis import ExpressionPatternLearner
from ..state.enhanced_memory_graph_manager import MemoryGraphManager
from .knowledge_graph_manager import KnowledgeGraphManager
from ..state import TimeDecayManager


class MaiBotEnhancedLearningManager:
    """
    MaiBot增强学习管理器
    统一协调表达模式学习、记忆图管理、知识图谱构建等功能
    采用单例模式并实现MaiBot的学习触发逻辑
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: PluginConfig = None, db_manager: DatabaseManager = None, context=None):
        # Allow re-init when first created without config (e.g. via get_instance())
        if self._initialized and self.config is not None:
            return
            
        self.config = config
        self.db_manager = db_manager
        self.context = context
        
        if config and context:
            self.llm_adapter = FrameworkLLMAdapter(context)
            self.llm_adapter.initialize_providers(config)
        else:
            self.llm_adapter = None
            
        self._status = ServiceLifecycle.CREATED
        
        # 初始化各个管理器，传递正确的参数
        self.expression_learner = ExpressionPatternLearner.get_instance(
            config=config,
            db_manager=db_manager,
            context=context,
            llm_adapter=self.llm_adapter
        )
        self.memory_graph_manager = MemoryGraphManager.get_instance()
        self.knowledge_graph_manager = KnowledgeGraphManager.get_instance()
        self.time_decay_manager = TimeDecayManager(config, db_manager) if config and db_manager else None
        
        # 学习状态跟踪
        self.group_learning_states: Dict[str, Dict[str, Any]] = {}
        
        # 消息缓冲区 - 用于批量学习
        self.message_buffers: Dict[str, List[MessageData]] = {}
        
        # MaiBot的学习参数
        self.MIN_MESSAGES_FOR_LEARNING = 25  # 触发学习的最小消息数
        self.LEARNING_COOLDOWN = 300  # 学习冷却时间（秒）
        self.BATCH_LEARNING_SIZE = 50  # 批量学习大小

        # V2 integration (conditional on engine config)
        self.v2_integration = None
        if config and (config.knowledge_engine != "legacy" or config.memory_engine != "legacy"):
            try:
                from ..core_learning import V2LearningIntegration
                self.v2_integration = V2LearningIntegration(
                    config=config,
                    llm_adapter=self.llm_adapter,
                    db_manager=db_manager,
                    context=context,
                )
            except Exception as exc:
                logger.warning(f"V2LearningIntegration init failed, using legacy only: {exc}")

        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'MaiBotEnhancedLearningManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def start(self) -> bool:
        """启动所有学习服务"""
        try:
            self._status = ServiceLifecycle.RUNNING
            
            # 启动各个子服务
            if self.expression_learner:
                await self.expression_learner.start()
            
            if self.memory_graph_manager:
                await self.memory_graph_manager.start()
            
            if self.knowledge_graph_manager:
                await self.knowledge_graph_manager.start()
            
            if self.time_decay_manager:
                await self.time_decay_manager.start()

            # V2 integration
            if self.v2_integration:
                await self.v2_integration.start()

            # 启动定期维护任务
            asyncio.create_task(self._periodic_maintenance())
            
            logger.info("MaiBotEnhancedLearningManager及所有子服务已启动")
            return True
            
        except Exception as e:
            logger.error(f"启动MaiBotEnhancedLearningManager失败: {e}")
            return False
    
    async def stop(self) -> bool:
        """停止所有学习服务"""
        try:
            self._status = ServiceLifecycle.STOPPED
            
            # 停止各个子服务
            if self.expression_learner:
                await self.expression_learner.stop()
            
            if self.memory_graph_manager:
                await self.memory_graph_manager.stop()
            
            if self.knowledge_graph_manager:
                await self.knowledge_graph_manager.stop()
            
            if self.time_decay_manager:
                await self.time_decay_manager.stop()

            # V2 integration
            if self.v2_integration:
                await self.v2_integration.stop()

            logger.info("MaiBotEnhancedLearningManager及所有子服务已停止")
            return True
            
        except Exception as e:
            logger.error(f"停止MaiBotEnhancedLearningManager失败: {e}")
            return False
    
    def _get_group_learning_state(self, group_id: str) -> Dict[str, Any]:
        """获取群组学习状态"""
        if group_id not in self.group_learning_states:
            self.group_learning_states[group_id] = {
                'last_learning_time': 0,
                'message_count_since_last_learning': 0,
                'total_messages_processed': 0,
                'last_expression_learning': 0,
                'last_memory_update': 0,
                'last_knowledge_update': 0,
                'learning_quality_score': 0.5
            }
        return self.group_learning_states[group_id]
    
    def _should_trigger_expression_learning(self, group_id: str, recent_messages: List[MessageData]) -> bool:
        """
        判断是否应该触发表达模式学习 - 采用MaiBot的触发条件
        """
        state = self._get_group_learning_state(group_id)
        current_time = time.time()
        
        # 检查冷却时间
        if current_time - state['last_expression_learning'] < self.LEARNING_COOLDOWN:
            return False
        
        # 检查消息数量
        if len(recent_messages) < self.MIN_MESSAGES_FOR_LEARNING:
            return False
        
        # 检查消息质量（简单的启发式规则）
        quality_messages = 0
        for msg in recent_messages:
            if len(msg.content) > 10 and not msg.content.startswith('[') and not msg.content.startswith('http'):
                quality_messages += 1
        
        quality_ratio = quality_messages / len(recent_messages)
        if quality_ratio < 0.3:  # 至少30%的消息是有质量的
            return False
        
        return True
    
    def _should_trigger_memory_update(self, group_id: str) -> bool:
        """判断是否应该更新记忆图"""
        state = self._get_group_learning_state(group_id)
        current_time = time.time()
        
        # 记忆更新频率更高
        return current_time - state['last_memory_update'] > 60  # 1分钟
    
    def _should_trigger_knowledge_update(self, group_id: str) -> bool:
        """判断是否应该更新知识图谱"""
        state = self._get_group_learning_state(group_id)
        current_time = time.time()
        
        # 知识图谱更新频率中等
        return current_time - state['last_knowledge_update'] > 120  # 2分钟
    
    async def process_message(self, message: MessageData, group_id: str) -> Dict[str, bool]:
        """
        处理单条消息 - 统一的消息处理入口
        
        Args:
            message: 消息数据
            group_id: 群组ID
            
        Returns:
            各个学习模块的处理结果
        """
        try:
            if self._status != ServiceLifecycle.RUNNING:
                return {}
            
            results = {
                'expression_learning': False,
                'memory_update': False,
                'knowledge_update': False,
                'v2_learning': False
            }

            # 添加到消息缓冲区
            if group_id not in self.message_buffers:
                self.message_buffers[group_id] = []

            self.message_buffers[group_id].append(message)

            # 限制缓冲区大小
            if len(self.message_buffers[group_id]) > self.BATCH_LEARNING_SIZE:
                self.message_buffers[group_id] = self.message_buffers[group_id][-self.BATCH_LEARNING_SIZE:]

            state = self._get_group_learning_state(group_id)
            state['message_count_since_last_learning'] += 1
            state['total_messages_processed'] += 1

            # 构建异步任务列表 (result_key, coroutine)
            named_tasks = []

            # V2 handles memory, knowledge, jargon, social, exemplar
            if self.v2_integration:
                named_tasks.append(('v2_learning', self._trigger_v2_processing(message, group_id)))

            # Expression learning always via legacy (no v2 replacement)
            if self.expression_learner and self._should_trigger_expression_learning(group_id, self.message_buffers[group_id]):
                named_tasks.append(('expression_learning', self._trigger_expression_learning(group_id)))

            # Legacy memory only when v2 doesn't handle it
            if not (self.v2_integration and self.config.memory_engine != "legacy"):
                if self.memory_graph_manager and self._should_trigger_memory_update(group_id):
                    named_tasks.append(('memory_update', self._trigger_memory_update(message, group_id)))

            # Legacy knowledge only when v2 doesn't handle it
            if not (self.v2_integration and self.config.knowledge_engine != "legacy"):
                if self.knowledge_graph_manager and self._should_trigger_knowledge_update(group_id):
                    named_tasks.append(('knowledge_update', self._trigger_knowledge_update(message, group_id)))

            # 并发执行所有任务
            if named_tasks:
                keys = [k for k, _ in named_tasks]
                coros = [c for _, c in named_tasks]
                task_results = await asyncio.gather(*coros, return_exceptions=True)

                for key, result in zip(keys, task_results):
                    if isinstance(result, Exception):
                        logger.error(f"学习任务 '{key}' 执行失败: {result}")
                    elif isinstance(result, bool):
                        results[key] = result

            return results
            
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            return {}
    
    async def _trigger_v2_processing(self, message: MessageData, group_id: str) -> bool:
        """Trigger V2 tiered learning pipeline."""
        try:
            await self.v2_integration.process_message(message, group_id)
            return True
        except Exception as exc:
            logger.error(f"V2 processing failed: {exc}")
            return False

    async def _trigger_expression_learning(self, group_id: str) -> bool:
        """触发表达模式学习"""
        try:
            recent_messages = self.message_buffers.get(group_id, [])
            if not recent_messages:
                return False
            
            success = await self.expression_learner.trigger_learning_for_group(group_id, recent_messages)
            
            if success:
                state = self._get_group_learning_state(group_id)
                state['last_expression_learning'] = time.time()
                state['message_count_since_last_learning'] = 0
            
            return success
            
        except Exception as e:
            logger.error(f"触发表达学习失败: {e}")
            return False
    
    async def _trigger_memory_update(self, message: MessageData, group_id: str) -> bool:
        """触发记忆图更新"""
        try:
            await self.memory_graph_manager.add_memory_from_message(message, group_id)
            
            state = self._get_group_learning_state(group_id)
            state['last_memory_update'] = time.time()
            
            return True
            
        except Exception as e:
            logger.error(f"触发记忆更新失败: {e}")
            return False
    
    async def _trigger_knowledge_update(self, message: MessageData, group_id: str) -> bool:
        """触发知识图谱更新"""
        try:
            await self.knowledge_graph_manager.process_message_for_knowledge_graph(message, group_id)
            
            state = self._get_group_learning_state(group_id)
            state['last_knowledge_update'] = time.time()
            
            return True
            
        except Exception as e:
            logger.error(f"触发知识更新失败: {e}")
            return False
    
    async def force_learning_for_group(self, group_id: str) -> Dict[str, Any]:
        """
        强制触发群组的全面学习
        
        Args:
            group_id: 群组ID
            
        Returns:
            学习结果统计
        """
        try:
            logger.info(f"开始强制学习，群组: {group_id}")
            
            results = {
                'expression_learning': False,
                'memory_save': False,
                'time_decay': (0, 0),
                'statistics': {}
            }
            
            # 1. 强制表达学习
            recent_messages = self.message_buffers.get(group_id, [])
            if recent_messages and self.expression_learner:
                results['expression_learning'] = await self.expression_learner.trigger_learning_for_group(group_id, recent_messages)
            
            # 2. 保存记忆图
            if self.memory_graph_manager:
                await self.memory_graph_manager.save_memory_graph(group_id)
                results['memory_save'] = True
            
            # 3. 应用时间衰减
            if self.time_decay_manager:
                decay_results = await self.time_decay_manager.apply_decay_to_all_tables(group_id)
                total_updated = sum(r[0] for r in decay_results.values())
                total_deleted = sum(r[1] for r in decay_results.values())
                results['time_decay'] = (total_updated, total_deleted)
            
            # 4. 收集统计信息
            if self.expression_learner:
                patterns = await self.expression_learner.get_expression_patterns(group_id, limit=10)
                results['statistics']['expression_patterns_count'] = len(patterns)
            
            if self.memory_graph_manager:
                memory_stats = await self.memory_graph_manager.get_memory_graph_statistics(group_id)
                results['statistics']['memory_graph'] = memory_stats
            
            if self.knowledge_graph_manager:
                kg_stats = await self.knowledge_graph_manager.get_knowledge_graph_statistics(group_id)
                results['statistics']['knowledge_graph'] = kg_stats
            
            # 更新学习状态
            state = self._get_group_learning_state(group_id)
            current_time = time.time()
            state.update({
                'last_learning_time': current_time,
                'last_expression_learning': current_time,
                'last_memory_update': current_time,
                'last_knowledge_update': current_time,
                'message_count_since_last_learning': 0
            })
            
            logger.info(f"强制学习完成，群组: {group_id}，结果: {results}")
            return results
            
        except Exception as e:
            logger.error(f"强制学习失败: {e}")
            raise SelfLearningError(f"强制学习失败: {e}")
    
    async def get_learning_status(self, group_id: str) -> Dict[str, Any]:
        """获取学习状态"""
        try:
            state = self._get_group_learning_state(group_id)
            current_time = time.time()
            
            status = {
                'group_id': group_id,
                'service_status': self._status.value,
                'learning_state': state.copy(),
                'buffer_size': len(self.message_buffers.get(group_id, [])),
                'time_since_last_learning': current_time - state['last_learning_time'],
                'can_trigger_expression_learning': self._should_trigger_expression_learning(
                    group_id, self.message_buffers.get(group_id, [])
                ),
                'can_trigger_memory_update': self._should_trigger_memory_update(group_id),
                'can_trigger_knowledge_update': self._should_trigger_knowledge_update(group_id)
            }
            
            # 添加各模块的详细状态
            if self.expression_learner:
                patterns = await self.expression_learner.get_expression_patterns(group_id, limit=5)
                status['expression_patterns'] = [p.to_dict() for p in patterns]
            
            if self.memory_graph_manager:
                status['memory_graph_stats'] = await self.memory_graph_manager.get_memory_graph_statistics(group_id)
            
            if self.knowledge_graph_manager:
                status['knowledge_graph_stats'] = await self.knowledge_graph_manager.get_knowledge_graph_statistics(group_id)
            
            return status
            
        except Exception as e:
            logger.error(f"获取学习状态失败: {e}")
            return {'error': str(e)}
    
    async def get_enhanced_context_for_response(self, query: str, group_id: str) -> Dict[str, Any]:
        """
        获取增强的上下文信息用于响应生成
        
        Args:
            query: 查询内容
            group_id: 群组ID
            
        Returns:
            增强的上下文信息
        """
        try:
            context = {
                'expression_patterns': '',
                'related_memories': [],
                'knowledge_graph_context': ''
            }

            # 1. Expression patterns — always legacy
            if self.expression_learner:
                patterns_text = await self.expression_learner.format_expression_patterns_for_prompt(group_id)
                context['expression_patterns'] = patterns_text

            # 2. V2 context (knowledge, memory, few-shot, social graph)
            v2_context_ok = False
            if self.v2_integration:
                try:
                    v2_ctx = await self.v2_integration.get_enhanced_context(query, group_id)
                    v2_context_ok = True
                    if 'knowledge_context' in v2_ctx:
                        context['knowledge_graph_context'] = v2_ctx['knowledge_context']
                    if 'related_memories' in v2_ctx:
                        context['related_memories'] = v2_ctx['related_memories']
                    if 'few_shot_examples' in v2_ctx:
                        context['few_shot_examples'] = v2_ctx['few_shot_examples']
                    if 'graph_stats' in v2_ctx:
                        context['graph_stats'] = v2_ctx['graph_stats']
                except Exception as exc:
                    logger.warning(f"V2 context retrieval failed, falling through to legacy: {exc}")

            # 3. Legacy fallbacks (when v2 not active, not handling this engine, or v2 failed)
            if not (self.v2_integration and v2_context_ok and self.config.memory_engine != "legacy"):
                if self.memory_graph_manager:
                    memories = await self.memory_graph_manager.get_related_memories(query, group_id)
                    context['related_memories'] = memories

            if not (self.v2_integration and v2_context_ok and self.config.knowledge_engine != "legacy"):
                if self.knowledge_graph_manager:
                    kg_answer = await self.knowledge_graph_manager.answer_question_with_knowledge_graph(query, group_id)
                    if kg_answer and kg_answer != "我不知道":
                        context['knowledge_graph_context'] = kg_answer

            return context
            
        except Exception as e:
            logger.error(f"获取增强上下文失败: {e}")
            return {}
    
    async def _periodic_maintenance(self):
        """定期维护任务"""
        while self._status == ServiceLifecycle.RUNNING:
            try:
                # 每小时执行一次维护
                await asyncio.sleep(3600)
                
                if self._status != ServiceLifecycle.RUNNING:
                    break
                
                logger.info("开始定期维护任务")
                
                # 1. 应用时间衰减
                if self.time_decay_manager:
                    decay_results = await self.time_decay_manager.apply_decay_to_all_tables()
                    total_updated = sum(r[0] for r in decay_results.values())
                    total_deleted = sum(r[1] for r in decay_results.values())
                    
                    if total_updated > 0 or total_deleted > 0:
                        logger.info(f"定期衰减维护完成，更新: {total_updated}，删除: {total_deleted}")
                
                # 2. 保存所有记忆图
                if self.memory_graph_manager:
                    for group_id in self.memory_graph_manager.memory_graphs:
                        await self.memory_graph_manager.save_memory_graph(group_id)
                
                # 3. 清理过大的消息缓冲区
                for group_id in list(self.message_buffers.keys()):
                    if len(self.message_buffers[group_id]) > self.BATCH_LEARNING_SIZE * 2:
                        self.message_buffers[group_id] = self.message_buffers[group_id][-self.BATCH_LEARNING_SIZE:]
                
                logger.info("定期维护任务完成")
                
            except Exception as e:
                logger.error(f"定期维护任务失败: {e}")
                await asyncio.sleep(300)  # 错误后等待5分钟再重试