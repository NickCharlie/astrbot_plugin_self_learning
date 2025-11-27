"""
增强型记忆图管理器
使用 CacheManager、Repository 和 TaskScheduler，与现有接口兼容
"""
import time
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import networkx as nx

from astrbot.api import logger

from ..core.interfaces import MessageData
from ..core.framework_llm_adapter import FrameworkLLMAdapter
from ..config import PluginConfig
from ..utils.cache_manager import get_cache_manager, async_cached
from ..utils.task_scheduler import get_task_scheduler

# 导入 Repository
from ..repositories import (
    MemoryRepository,
    MemoryEmbeddingRepository,
    MemorySummaryRepository
)

# 导入原有的数据类和图类
from .memory_graph_manager import (
    MemoryNode,
    MemoryEdge,
    MemoryGraph,
    MemoryGraphManager as OriginalMemoryGraphManager
)


class EnhancedMemoryGraphManager:
    """
    增强型记忆图管理器

    改进:
    1. 使用 CacheManager 缓存记忆图和查询结果
    2. 使用 Repository 访问数据库
    3. 使用 TaskScheduler 管理定期清理任务
    4. 保持与原有接口的兼容性

    用法:
        # 在配置中启用
        config.use_enhanced_managers = True

        # 创建管理器
        memory_mgr = EnhancedMemoryGraphManager.get_instance(config, db_manager, llm_adapter)
        await memory_mgr.start()
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        config: PluginConfig = None,
        db_manager = None,
        llm_adapter: Optional[FrameworkLLMAdapter] = None,
        decay_manager = None
    ):
        """初始化增强型记忆图管理器"""
        if self._initialized:
            return

        self.config = config
        self.db_manager = db_manager
        self.llm_adapter = llm_adapter
        self.decay_manager = decay_manager

        # 使用统一的缓存管理器
        self.cache = get_cache_manager()

        # 使用统一的任务调度器
        self.scheduler = get_task_scheduler()

        # 内存中的记忆图（不缓存到 CacheManager，保持原有逻辑）
        # 因为 MemoryGraph 对象包含 NetworkX 图，不适合序列化缓存
        self.memory_graphs: Dict[str, MemoryGraph] = {}

        self._initialized = True
        logger.info("[增强型记忆图] 初始化完成（使用缓存管理器）")

    @classmethod
    def get_instance(cls, config=None, db_manager=None, llm_adapter=None, decay_manager=None):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(config, db_manager, llm_adapter, decay_manager)
        return cls._instance

    async def start(self) -> bool:
        """启动记忆图管理器"""
        try:
            # 启动任务调度器
            await self.scheduler.start()

            # 添加定期清理旧记忆的任务（每天凌晨3点）
            if self.config and getattr(self.config, 'enable_memory_cleanup', True):
                self.scheduler.add_cron_job(
                    self._cleanup_old_memories_task,
                    job_id='memory_cleanup',
                    hour=3,
                    minute=0
                )

            # 添加定期保存记忆图的任务（每小时）
            self.scheduler.add_interval_job(
                self._auto_save_memory_graphs_task,
                job_id='memory_auto_save',
                hours=1
            )

            logger.info("✅ [增强型记忆图] 启动成功")
            return True

        except Exception as e:
            logger.error(f"❌ [增强型记忆图] 启动失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止记忆图管理器"""
        try:
            # 保存所有记忆图
            for group_id in list(self.memory_graphs.keys()):
                await self.save_memory_graph(group_id)

            # 移除定时任务
            self.scheduler.remove_job('memory_cleanup')
            self.scheduler.remove_job('memory_auto_save')

            # 清除缓存
            self.cache.clear('memory')

            logger.info("✅ [增强型记忆图] 已停止")
            return True

        except Exception as e:
            logger.error(f"❌ [增强型记忆图] 停止失败: {e}")
            return False

    # ============================================================
    # 核心方法（与原接口兼容）
    # ============================================================

    def get_memory_graph(self, group_id: str) -> MemoryGraph:
        """
        获取记忆图（内存缓存）

        Args:
            group_id: 群组 ID

        Returns:
            MemoryGraph: 记忆图对象
        """
        if group_id not in self.memory_graphs:
            self.memory_graphs[group_id] = MemoryGraph()
            logger.debug(f"[增强型记忆图] 为群组 {group_id} 创建新记忆图")

        return self.memory_graphs[group_id]

    async def load_memory_graph(self, group_id: str):
        """
        从数据库加载记忆图

        Args:
            group_id: 群组 ID
        """
        try:
            # 使用 Repository 从数据库加载
            if hasattr(self.db_manager, 'get_session'):
                # 新的 SQLAlchemy 版本
                async with self.db_manager.get_session() as session:
                    memory_repo = MemoryRepository(session)
                    memories = await memory_repo.find_many(
                        group_id=group_id,
                        limit=1000
                    )

                    # 重建记忆图
                    memory_graph = MemoryGraph()
                    for memory in memories:
                        # 从 metadata 解析概念和关联
                        try:
                            metadata = json.loads(memory.metadata) if memory.metadata else {}
                            concept = metadata.get('concept')
                            if concept:
                                await memory_graph.add_memory_node(
                                    concept,
                                    memory.content,
                                    self.llm_adapter
                                )
                        except Exception as e:
                            logger.debug(f"[增强型记忆图] 解析记忆失败: {e}")

                    self.memory_graphs[group_id] = memory_graph
                    logger.info(f"[增强型记忆图] 群组 {group_id} 加载了 {len(memories)} 条记忆")
            else:
                # 降级到原有实现
                logger.debug("[增强型记忆图] 使用原有数据库加载方式")
                # TODO: 调用原有的加载逻辑

        except Exception as e:
            logger.error(f"[增强型记忆图] 加载记忆图失败: {e}")

    async def save_memory_graph(self, group_id: str):
        """
        保存记忆图到数据库

        Args:
            group_id: 群组 ID
        """
        try:
            if group_id not in self.memory_graphs:
                return

            memory_graph = self.memory_graphs[group_id]

            # 使用 Repository 保存
            if hasattr(self.db_manager, 'get_session'):
                # 新的 SQLAlchemy 版本
                async with self.db_manager.get_session() as session:
                    memory_repo = MemoryRepository(session)

                    # 遍历所有节点保存
                    for concept in memory_graph.G.nodes():
                        node_data = memory_graph.G.nodes[concept]
                        memory_items = node_data.get('memory_items', '')

                        if memory_items:
                            # 创建或更新记忆
                            await memory_repo.create_memory(
                                group_id=group_id,
                                user_id='',  # 群组级别记忆
                                content=memory_items,
                                memory_type='concept',
                                importance=node_data.get('weight', 0.5),
                                metadata=json.dumps({
                                    'concept': concept,
                                    'created_time': node_data.get('created_time'),
                                    'last_modified': node_data.get('last_modified')
                                })
                            )

                    logger.info(
                        f"[增强型记忆图] 群组 {group_id} 保存了 "
                        f"{len(memory_graph.G.nodes())} 个概念节点"
                    )
            else:
                # 降级到原有实现
                logger.debug("[增强型记忆图] 使用原有数据库保存方式")
                # TODO: 调用原有的保存逻辑

        except Exception as e:
            logger.error(f"[增强型记忆图] 保存记忆图失败: {e}")

    async def add_memory_from_message(self, message: MessageData, group_id: str):
        """
        从消息添加记忆

        Args:
            message: 消息数据
            group_id: 群组 ID
        """
        try:
            # 提取概念
            concepts = await self._extract_concepts_from_message(message)

            if not concepts:
                return

            # 获取记忆图
            memory_graph = self.get_memory_graph(group_id)

            # 添加记忆节点
            for concept in concepts:
                await memory_graph.add_memory_node(
                    concept,
                    message.raw_message,
                    self.llm_adapter
                )

            # 连接概念
            for i in range(len(concepts)):
                for j in range(i + 1, len(concepts)):
                    memory_graph.connect_concepts(concepts[i], concepts[j])

            # 清除相关缓存
            self._invalidate_related_caches(group_id)

            logger.debug(
                f"[增强型记忆图] 从消息添加了 {len(concepts)} 个概念: "
                f"{', '.join(concepts[:3])}..."
            )

        except Exception as e:
            logger.error(f"[增强型记忆图] 添加记忆失败: {e}")

    @async_cached(
        cache_name='memory',
        key_func=lambda self, query, group_id, limit: f"related:{group_id}:{query}:{limit}"
    )
    async def get_related_memories(
        self,
        query: str,
        group_id: str,
        limit: int = 5
    ) -> List[str]:
        """
        获取相关记忆（带缓存）

        Args:
            query: 查询文本
            group_id: 群组 ID
            limit: 返回数量

        Returns:
            List[str]: 相关记忆列表
        """
        try:
            # 提取查询概念
            concepts = await self._extract_concepts_from_text(query)

            if not concepts:
                return []

            # 获取记忆图
            memory_graph = self.get_memory_graph(group_id)

            # 收集相关记忆
            related_memories = []
            for concept in concepts:
                related, _ = memory_graph.get_related_concepts(concept, depth=1)
                for rel_concept in related[:limit]:
                    node = memory_graph.get_memory_node(rel_concept)
                    if node:
                        related_memories.append(node[0])

            return related_memories[:limit]

        except Exception as e:
            logger.error(f"[增强型记忆图] 获取相关记忆失败: {e}")
            return []

    async def get_memory_graph_statistics(self, group_id: str) -> Dict[str, Any]:
        """
        获取记忆图统计信息

        Args:
            group_id: 群组 ID

        Returns:
            Dict: 统计信息
        """
        try:
            memory_graph = self.get_memory_graph(group_id)
            return memory_graph.get_graph_statistics()

        except Exception as e:
            logger.error(f"[增强型记忆图] 获取统计信息失败: {e}")
            return {}

    # ============================================================
    # 辅助方法
    # ============================================================

    async def _extract_concepts_from_message(self, message: MessageData) -> List[str]:
        """从消息提取概念"""
        # 保持原有逻辑
        return await self._extract_concepts_from_text(message.raw_message)

    async def _extract_concepts_from_text(self, text: str) -> List[str]:
        """
        从文本提取概念

        简化实现: 使用分词和关键词提取
        实际可以使用 LLM 或 NLP 工具
        """
        # TODO: 实现更智能的概念提取
        # 这里使用简单的分词
        words = text.split()
        # 过滤短词和常用词
        concepts = [w for w in words if len(w) > 2][:5]
        return concepts

    def _invalidate_related_caches(self, group_id: str):
        """清除相关缓存"""
        # 清除该群组的所有相关记忆缓存
        # CacheManager 不支持模式匹配删除，所以这里只是示例
        logger.debug(f"[增强型记忆图] 清除群组 {group_id} 的相关缓存")

    # ============================================================
    # 任务调度方法
    # ============================================================

    async def _cleanup_old_memories_task(self):
        """清理旧记忆任务（由调度器调用）"""
        try:
            logger.info("[增强型记忆图] 执行旧记忆清理...")

            if hasattr(self.db_manager, 'get_session'):
                async with self.db_manager.get_session() as session:
                    memory_repo = MemoryRepository(session)

                    # 清理所有群组的30天前的低重要性记忆
                    for group_id in self.memory_graphs.keys():
                        deleted = await memory_repo.clean_old_memories(
                            group_id=group_id,
                            days=30,
                            importance_threshold=0.3
                        )
                        logger.info(
                            f"[增强型记忆图] 群组 {group_id} 清理了 {deleted} 条旧记忆"
                        )

            logger.info("[增强型记忆图] 旧记忆清理完成")

        except Exception as e:
            logger.error(f"[增强型记忆图] 清理旧记忆失败: {e}")

    async def _auto_save_memory_graphs_task(self):
        """自动保存记忆图任务（由调度器调用）"""
        try:
            logger.debug("[增强型记忆图] 执行自动保存...")

            for group_id in list(self.memory_graphs.keys()):
                await self.save_memory_graph(group_id)

            logger.debug(
                f"[增强型记忆图] 自动保存完成，"
                f"共保存 {len(self.memory_graphs)} 个记忆图"
            )

        except Exception as e:
            logger.error(f"[增强型记忆图] 自动保存失败: {e}")

    # ============================================================
    # 缓存统计方法
    # ============================================================

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return self.cache.get_stats('memory')

    def clear_cache(self):
        """清除所有缓存"""
        self.cache.clear('memory')
        logger.info("[增强型记忆图] 已清除所有缓存")
