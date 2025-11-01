"""
记忆图管理器 - 基于MaiBot的记忆图系统设计
使用NetworkX图结构实现概念关联和智能记忆融合
"""
import time
import json
import math
import random
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import Counter

import networkx as nx

from astrbot.api import logger

from ..core.interfaces import MessageData, ServiceLifecycle
from ..core.framework_llm_adapter import FrameworkLLMAdapter
from ..config import PluginConfig
from ..exceptions import MemoryGraphError, ModelAccessError
from ..utils.json_utils import safe_parse_llm_json
from .database_manager import DatabaseManager
from .time_decay_manager import TimeDecayManager


@dataclass
class MemoryNode:
    """记忆节点"""
    concept: str
    memory_items: str
    weight: float
    created_time: float
    last_modified: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryNode':
        return cls(**data)


@dataclass
class MemoryEdge:
    """记忆边"""
    concept1: str
    concept2: str
    strength: float
    created_time: float
    last_modified: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryEdge':
        return cls(**data)


class MemoryGraph:
    """
    记忆图 - 完全基于MaiBot的MemoryGraph设计
    使用NetworkX实现概念关联和记忆管理
    """
    
    def __init__(self):
        self.G = nx.Graph()  # 使用NetworkX的图结构
    
    def connect_concepts(self, concept1: str, concept2: str):
        """
        连接两个概念 - 参考MaiBot的connect_dot方法
        
        Args:
            concept1: 概念1
            concept2: 概念2
        """
        # 避免自连接
        if concept1 == concept2:
            return
        
        current_time = time.time()
        
        # 如果边已存在，增加strength
        if self.G.has_edge(concept1, concept2):
            self.G[concept1][concept2]["strength"] = self.G[concept1][concept2].get("strength", 1) + 1
            # 更新最后修改时间
            self.G[concept1][concept2]["last_modified"] = current_time
        else:
            # 如果是新边，初始化strength为1
            self.G.add_edge(
                concept1,
                concept2,
                strength=1,
                created_time=current_time,
                last_modified=current_time,
            )
    
    async def add_memory_node(self, concept: str, memory: str, llm_adapter: Optional[FrameworkLLMAdapter] = None):
        """
        添加记忆节点 - 参考MaiBot的add_dot方法
        支持LLM智能记忆融合
        
        Args:
            concept: 概念名称
            memory: 记忆内容
            llm_adapter: LLM适配器，用于记忆融合
        """
        current_time = time.time()
        
        if concept in self.G:
            if "memory_items" in self.G.nodes[concept]:
                # 获取现有的记忆项
                existing_memory = self.G.nodes[concept]["memory_items"]
                
                # 如果现有记忆不为空，则使用LLM整合新旧记忆
                if existing_memory and llm_adapter:
                    try:
                        integrated_memory = await self._integrate_memories_with_llm(
                            existing_memory, str(memory), llm_adapter
                        )
                        self.G.nodes[concept]["memory_items"] = integrated_memory
                        # 整合成功，增加权重
                        current_weight = self.G.nodes[concept].get("weight", 0.0)
                        self.G.nodes[concept]["weight"] = current_weight + 1.0
                        logger.debug(f"节点 {concept} 记忆整合成功，权重增加到 {current_weight + 1.0}")
                        logger.info(f"节点 {concept} 记忆内容已更新：{integrated_memory}")
                    except Exception as e:
                        logger.error(f"LLM整合记忆失败: {e}")
                        # 降级到简单连接
                        new_memory_str = f"{existing_memory} | {memory}"
                        self.G.nodes[concept]["memory_items"] = new_memory_str
                        logger.info(f"节点 {concept} 记忆内容已简单拼接并更新：{new_memory_str}")
                else:
                    new_memory_str = str(memory)
                    self.G.nodes[concept]["memory_items"] = new_memory_str
                    logger.info(f"节点 {concept} 记忆内容已直接更新：{new_memory_str}")
            else:
                self.G.nodes[concept]["memory_items"] = str(memory)
                # 如果节点存在但没有memory_items，说明是第一次添加memory，设置created_time
                if "created_time" not in self.G.nodes[concept]:
                    self.G.nodes[concept]["created_time"] = current_time
                logger.info(f"节点 {concept} 创建新记忆：{str(memory)}")
            # 更新最后修改时间
            self.G.nodes[concept]["last_modified"] = current_time
        else:
            # 如果是新节点，创建新的记忆字符串
            self.G.add_node(
                concept,
                memory_items=str(memory),
                weight=1.0,  # 新节点初始权重为1.0
                created_time=current_time,
                last_modified=current_time,
            )
            logger.info(f"新节点 {concept} 已添加，记忆内容已写入：{str(memory)}")
    
    async def _integrate_memories_with_llm(self, old_memory: str, new_memory: str, llm_adapter: FrameworkLLMAdapter) -> str:
        """
        使用LLM智能整合记忆 - 参考MaiBot的_integrate_memories_with_llm方法
        
        Args:
            old_memory: 旧记忆
            new_memory: 新记忆
            llm_adapter: LLM适配器
            
        Returns:
            整合后的记忆
        """
        from ..statics.prompts import MEMORY_INTEGRATION_PROMPT
        
        prompt = MEMORY_INTEGRATION_PROMPT.format(
            old_memory=old_memory,
            new_memory=new_memory
        )
        
        response = await llm_adapter.generate_response(
            prompt,
            temperature=0.3,
            model_type="refine"
        )
        
        return response.strip()
    
    def get_memory_node(self, concept: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        获取记忆节点 - 参考MaiBot的get_dot方法
        
        Args:
            concept: 概念名称
            
        Returns:
            (概念名称, 节点数据) 或 None
        """
        return (concept, self.G.nodes[concept]) if concept in self.G else None
    
    def get_related_concepts(self, topic: str, depth: int = 1) -> Tuple[List[str], List[str]]:
        """
        获取相关概念 - 参考MaiBot的get_related_item方法
        
        Args:
            topic: 主题概念
            depth: 搜索深度
            
        Returns:
            (第一层相关概念, 第二层相关概念)
        """
        if topic not in self.G:
            return [], []
        
        first_layer_items = []
        second_layer_items = []
        
        # 获取相邻节点
        neighbors = list(self.G.neighbors(topic))
        
        # 获取当前节点的记忆项
        node_data = self.get_memory_node(topic)
        if node_data:
            _, data = node_data
            if "memory_items" in data:
                # 将主题概念的记忆内容加入第一层
                first_layer_items.append(data["memory_items"])
        
        # 获取相邻节点的记忆项
        for neighbor in neighbors:
            neighbor_data = self.get_memory_node(neighbor)
            if neighbor_data:
                _, data = neighbor_data
                if "memory_items" in data:
                    first_layer_items.append(data["memory_items"])
                    
                    # 如果需要深度搜索，获取邻居的邻居
                    if depth > 1:
                        second_neighbors = list(self.G.neighbors(neighbor))
                        for second_neighbor in second_neighbors:
                            if second_neighbor != topic and second_neighbor not in neighbors:
                                second_data = self.get_memory_node(second_neighbor)
                                if second_data:
                                    _, second_node_data = second_data
                                    if "memory_items" in second_node_data:
                                        second_layer_items.append(second_node_data["memory_items"])
        
        return first_layer_items, second_layer_items
    
    def calculate_information_content(self, text: str) -> float:
        """
        计算文本的信息量（熵） - 参考MaiBot的calculate_information_content方法
        
        Args:
            text: 文本内容
            
        Returns:
            信息熵值
        """
        char_count = Counter(text)
        total_chars = len(text)
        if total_chars == 0:
            return 0
        
        entropy = 0
        for count in char_count.values():
            probability = count / total_chars
            entropy -= probability * math.log2(probability)
        
        return entropy
    
    def get_graph_statistics(self) -> Dict[str, Any]:
        """获取图的统计信息"""
        return {
            "nodes_count": self.G.number_of_nodes(),
            "edges_count": self.G.number_of_edges(),
            "density": nx.density(self.G),
            "connected_components": nx.number_connected_components(self.G),
            "average_clustering": nx.average_clustering(self.G) if self.G.number_of_nodes() > 0 else 0,
            "average_shortest_path": nx.average_shortest_path_length(self.G) if nx.is_connected(self.G) else 0
        }


class MemoryGraphManager:
    """
    记忆图管理器 - 负责记忆图的持久化和管理
    采用单例模式确保全局唯一实例
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: PluginConfig = None, db_manager: DatabaseManager = None, 
                 llm_adapter: FrameworkLLMAdapter = None, decay_manager: TimeDecayManager = None):
        # 防止重复初始化
        if self._initialized:
            return
            
        self.config = config
        self.db_manager = db_manager
        self.llm_adapter = llm_adapter
        self.decay_manager = decay_manager
        self._status = ServiceLifecycle.CREATED
        
        # 为每个群组维护独立的记忆图
        self.memory_graphs: Dict[str, MemoryGraph] = {}
        
        # 初始化数据库表
        if self.db_manager:
            self._init_memory_graph_tables()
            
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'MemoryGraphManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _init_memory_graph_tables(self):
        """初始化记忆图数据库表"""
        try:
            with self.db_manager.get_connection() as conn:
                # 记忆节点表
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS memory_nodes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        concept TEXT NOT NULL,
                        memory_items TEXT NOT NULL,
                        weight REAL NOT NULL DEFAULT 1.0,
                        created_time REAL NOT NULL,
                        last_modified REAL NOT NULL,
                        group_id TEXT NOT NULL,
                        UNIQUE(concept, group_id)
                    )
                ''')
                
                # 记忆边表
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS memory_edges (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        concept1 TEXT NOT NULL,
                        concept2 TEXT NOT NULL,
                        strength REAL NOT NULL DEFAULT 1.0,
                        created_time REAL NOT NULL,
                        last_modified REAL NOT NULL,
                        group_id TEXT NOT NULL,
                        UNIQUE(concept1, concept2, group_id)
                    )
                ''')
                
                conn.commit()
                logger.info("记忆图数据库表初始化完成")
        except Exception as e:
            logger.error(f"初始化记忆图数据库表失败: {e}")
            raise MemoryGraphError(f"数据库初始化失败: {e}")
    
    async def start(self) -> bool:
        """启动服务"""
        self._status = ServiceLifecycle.RUNNING
        logger.info("MemoryGraphManager服务已启动")
        return True
    
    async def stop(self) -> bool:
        """停止服务"""
        # 保存所有记忆图
        for group_id in self.memory_graphs:
            await self.save_memory_graph(group_id)
        
        self._status = ServiceLifecycle.STOPPED
        logger.info("MemoryGraphManager服务已停止")
        return True
    
    def get_memory_graph(self, group_id: str) -> MemoryGraph:
        """获取或创建群组的记忆图"""
        if group_id not in self.memory_graphs:
            self.memory_graphs[group_id] = MemoryGraph()
            # 异步加载记忆图数据
            asyncio.create_task(self.load_memory_graph(group_id))
        
        return self.memory_graphs[group_id]
    
    async def load_memory_graph(self, group_id: str):
        """从数据库加载记忆图"""
        try:
            memory_graph = self.memory_graphs.get(group_id, MemoryGraph())
            
            with self.db_manager.get_connection() as conn:
                # 加载节点
                cursor = conn.execute(
                    'SELECT concept, memory_items, weight, created_time, last_modified FROM memory_nodes WHERE group_id = ?',
                    (group_id,)
                )
                
                for concept, memory_items, weight, created_time, last_modified in cursor.fetchall():
                    memory_graph.G.add_node(
                        concept,
                        memory_items=memory_items,
                        weight=weight,
                        created_time=created_time,
                        last_modified=last_modified
                    )
                
                # 加载边
                cursor = conn.execute(
                    'SELECT concept1, concept2, strength, created_time, last_modified FROM memory_edges WHERE group_id = ?',
                    (group_id,)
                )
                
                for concept1, concept2, strength, created_time, last_modified in cursor.fetchall():
                    memory_graph.G.add_edge(
                        concept1,
                        concept2,
                        strength=strength,
                        created_time=created_time,
                        last_modified=last_modified
                    )
                
                self.memory_graphs[group_id] = memory_graph
                logger.info(f"群组 {group_id} 记忆图加载完成，节点数: {memory_graph.G.number_of_nodes()}，边数: {memory_graph.G.number_of_edges()}")
                
        except Exception as e:
            logger.error(f"加载群组 {group_id} 记忆图失败: {e}")
    
    async def save_memory_graph(self, group_id: str):
        """保存记忆图到数据库"""
        try:
            if group_id not in self.memory_graphs:
                return
            
            memory_graph = self.memory_graphs[group_id]
            
            with self.db_manager.get_connection() as conn:
                # 清除旧数据
                conn.execute('DELETE FROM memory_nodes WHERE group_id = ?', (group_id,))
                conn.execute('DELETE FROM memory_edges WHERE group_id = ?', (group_id,))
                
                # 保存节点
                for node, data in memory_graph.G.nodes(data=True):
                    conn.execute(
                        'INSERT INTO memory_nodes (concept, memory_items, weight, created_time, last_modified, group_id) VALUES (?, ?, ?, ?, ?, ?)',
                        (
                            node,
                            data.get('memory_items', ''),
                            data.get('weight', 1.0),
                            data.get('created_time', time.time()),
                            data.get('last_modified', time.time()),
                            group_id
                        )
                    )
                
                # 保存边
                for u, v, data in memory_graph.G.edges(data=True):
                    conn.execute(
                        'INSERT INTO memory_edges (concept1, concept2, strength, created_time, last_modified, group_id) VALUES (?, ?, ?, ?, ?, ?)',
                        (
                            u, v,
                            data.get('strength', 1.0),
                            data.get('created_time', time.time()),
                            data.get('last_modified', time.time()),
                            group_id
                        )
                    )
                
                conn.commit()
                logger.debug(f"群组 {group_id} 记忆图保存完成")
                
        except Exception as e:
            logger.error(f"保存群组 {group_id} 记忆图失败: {e}")
    
    async def add_memory_from_message(self, message: MessageData, group_id: str):
        """
        从消息中添加记忆
        
        Args:
            message: 消息数据
            group_id: 群组ID
        """
        try:
            memory_graph = self.get_memory_graph(group_id)
            
            # 提取概念和记忆内容
            concepts = await self._extract_concepts_from_message(message)
            
            for concept in concepts:
                # 添加记忆节点
                await memory_graph.add_memory_node(
                    concept=concept,
                    memory=message.content,
                    llm_adapter=self.llm_adapter
                )
                
                # 建立概念间的连接
                for other_concept in concepts:
                    if concept != other_concept:
                        memory_graph.connect_concepts(concept, other_concept)
            
            # 定期保存
            if random.random() < 0.1:  # 10% 概率保存
                await self.save_memory_graph(group_id)
                
        except Exception as e:
            logger.error(f"从消息添加记忆失败: {e}")
    
    async def _extract_concepts_from_message(self, message: MessageData) -> List[str]:
        """
        从消息中提取概念
        
        Args:
            message: 消息数据
            
        Returns:
            提取的概念列表
        """
        try:
            from ..statics.prompts import ENTITY_EXTRACTION_PROMPT
            
            prompt = ENTITY_EXTRACTION_PROMPT.format(text=message.content)
            
            response = await self.llm_adapter.generate_response(
                prompt,
                temperature=0.1,
                model_type="filter"  # 使用过滤模型进行快速提取
            )
            
            # 解析JSON响应
            concepts = safe_parse_llm_json(response)
            
            if isinstance(concepts, list):
                return [str(concept).strip() for concept in concepts if concept]
            else:
                return []
                
        except Exception as e:
            logger.error(f"提取概念失败: {e}")
            return []
    
    async def get_related_memories(self, query: str, group_id: str, limit: int = 5) -> List[str]:
        """
        获取与查询相关的记忆
        
        Args:
            query: 查询内容
            group_id: 群组ID
            limit: 返回数量限制
            
        Returns:
            相关记忆列表
        """
        try:
            memory_graph = self.get_memory_graph(group_id)
            
            # 提取查询中的概念
            query_concepts = await self._extract_concepts_from_text(query)
            
            related_memories = []
            
            for concept in query_concepts:
                if concept in memory_graph.G:
                    # 获取相关概念
                    first_layer, second_layer = memory_graph.get_related_concepts(concept, depth=2)
                    related_memories.extend(first_layer)
                    related_memories.extend(second_layer)
            
            # 去重并限制数量
            unique_memories = list(dict.fromkeys(related_memories))
            return unique_memories[:limit]
            
        except Exception as e:
            logger.error(f"获取相关记忆失败: {e}")
            return []
    
    async def _extract_concepts_from_text(self, text: str) -> List[str]:
        """从文本中提取概念"""
        # 简化版本的概念提取，可以后续优化
        import jieba
        
        # 使用jieba分词提取关键词
        words = jieba.lcut(text)
        
        # 过滤停用词和短词
        stopwords = {'的', '是', '在', '了', '和', '有', '我', '你', '他', '她', '它', '这', '那', '一个', '不', '没有'}
        concepts = [word for word in words if len(word) > 1 and word not in stopwords]
        
        return concepts[:5]  # 返回前5个概念
    
    async def get_memory_graph_statistics(self, group_id: str) -> Dict[str, Any]:
        """获取记忆图统计信息"""
        try:
            memory_graph = self.get_memory_graph(group_id)
            stats = memory_graph.get_graph_statistics()
            
            # 添加更多统计信息
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute(
                    'SELECT COUNT(*) FROM memory_nodes WHERE group_id = ?',
                    (group_id,)
                )
                db_nodes_count = cursor.fetchone()[0]
                
                cursor = conn.execute(
                    'SELECT COUNT(*) FROM memory_edges WHERE group_id = ?',
                    (group_id,)
                )
                db_edges_count = cursor.fetchone()[0]
                
                stats.update({
                    'db_nodes_count': db_nodes_count,
                    'db_edges_count': db_edges_count,
                    'group_id': group_id
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"获取记忆图统计信息失败: {e}")
            return {}


# 导入asyncio
import asyncio