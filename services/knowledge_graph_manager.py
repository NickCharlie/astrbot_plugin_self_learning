"""
知识图谱管理器 - 基于MaiBot的知识图谱系统设计
实现实体关系提取、RDF三元组构建和知识图谱查询
"""
import json
import time
import math
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict

from astrbot.api import logger

from ..core.interfaces import MessageData, ServiceLifecycle
from ..core.framework_llm_adapter import FrameworkLLMAdapter
from ..config import PluginConfig
from ..exceptions import KnowledgeGraphError, ModelAccessError
from ..utils.json_utils import safe_parse_llm_json
from .database_manager import DatabaseManager


@dataclass
class Entity:
    """实体数据结构"""
    name: str
    entity_type: str
    appear_count: int
    last_active_time: float
    group_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Entity':
        return cls(**data)


@dataclass
class Relation:
    """关系数据结构"""
    subject: str
    predicate: str
    object: str
    confidence: float
    created_time: float
    group_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Relation':
        return cls(**data)


class KnowledgeGraphManager:
    """
    知识图谱管理器 - 基于MaiBot的知识图谱系统设计
    实现实体识别、关系提取和知识图谱构建
    采用单例模式确保全局唯一实例
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: PluginConfig = None, db_manager: DatabaseManager = None, 
                 llm_adapter: FrameworkLLMAdapter = None):
        # 防止重复初始化
        if self._initialized:
            return
            
        self.config = config
        self.db_manager = db_manager
        self.llm_adapter = llm_adapter
        self._status = ServiceLifecycle.CREATED
        
        # 实体出现次数缓存
        self.entity_appear_count: Dict[str, Dict[str, int]] = defaultdict(dict)
        
        # 存储段落的hash值，用于去重
        self.stored_paragraph_hashes: Dict[str, Set[str]] = defaultdict(set)
        
        # 初始化数据库表
        if self.db_manager:
            self._init_knowledge_graph_tables()
            
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'KnowledgeGraphManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _init_knowledge_graph_tables(self):
        """初始化知识图谱数据库表"""
        try:
            with self.db_manager.get_connection() as conn:
                # 实体表
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS kg_entities (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        entity_type TEXT DEFAULT 'general',
                        appear_count INTEGER DEFAULT 1,
                        last_active_time REAL NOT NULL,
                        group_id TEXT NOT NULL,
                        UNIQUE(name, group_id)
                    )
                ''')
                
                # 关系表
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS kg_relations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        subject TEXT NOT NULL,
                        predicate TEXT NOT NULL,
                        object TEXT NOT NULL,
                        confidence REAL DEFAULT 1.0,
                        created_time REAL NOT NULL,
                        group_id TEXT NOT NULL,
                        UNIQUE(subject, predicate, object, group_id)
                    )
                ''')
                
                # 段落hash表，用于去重
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS kg_paragraph_hashes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        hash_value TEXT NOT NULL,
                        group_id TEXT NOT NULL,
                        created_time REAL NOT NULL,
                        UNIQUE(hash_value, group_id)
                    )
                ''')
                
                conn.commit()
                logger.info("知识图谱数据库表初始化完成")
        except Exception as e:
            logger.error(f"初始化知识图谱数据库表失败: {e}")
            raise KnowledgeGraphError(f"数据库初始化失败: {e}")
    
    async def start(self) -> bool:
        """启动服务"""
        self._status = ServiceLifecycle.RUNNING
        logger.info("KnowledgeGraphManager服务已启动")
        return True
    
    async def stop(self) -> bool:
        """停止服务"""
        self._status = ServiceLifecycle.STOPPED
        logger.info("KnowledgeGraphManager服务已停止")
        return True
    
    def _get_paragraph_hash(self, text: str) -> str:
        """获取段落的hash值"""
        import hashlib
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def _is_paragraph_processed(self, text: str, group_id: str) -> bool:
        """检查段落是否已经处理过"""
        para_hash = self._get_paragraph_hash(text)
        
        # 先检查内存缓存
        if para_hash in self.stored_paragraph_hashes[group_id]:
            return True
        
        # 检查数据库
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute(
                    'SELECT 1 FROM kg_paragraph_hashes WHERE hash_value = ? AND group_id = ?',
                    (para_hash, group_id)
                )
                exists = cursor.fetchone() is not None
                
                if exists:
                    self.stored_paragraph_hashes[group_id].add(para_hash)
                
                return exists
        except Exception as e:
            logger.error(f"检查段落hash失败: {e}")
            return False
    
    def _mark_paragraph_processed(self, text: str, group_id: str):
        """标记段落为已处理"""
        para_hash = self._get_paragraph_hash(text)
        
        try:
            with self.db_manager.get_connection() as conn:
                conn.execute(
                    'INSERT OR IGNORE INTO kg_paragraph_hashes (hash_value, group_id, created_time) VALUES (?, ?, ?)',
                    (para_hash, group_id, time.time())
                )
                conn.commit()
                
                # 更新内存缓存
                self.stored_paragraph_hashes[group_id].add(para_hash)
                
        except Exception as e:
            logger.error(f"标记段落hash失败: {e}")
    
    async def extract_entities_from_text(self, text: str) -> List[str]:
        """
        从文本中提取实体 - 采用MaiBot的实体提取方法
        
        Args:
            text: 输入文本
            
        Returns:
            提取的实体列表
        """
        try:
            from ..statics.prompts import ENTITY_EXTRACTION_PROMPT
            
            prompt = ENTITY_EXTRACTION_PROMPT.format(text=text)
            
            response = await self.llm_adapter.generate_response(
                prompt,
                temperature=0.1,
                model_type="filter"  # 使用过滤模型进行快速提取
            )
            
            # 解析JSON响应
            entities = safe_parse_llm_json(response)
            
            if isinstance(entities, list):
                return [str(entity).strip() for entity in entities if entity and len(str(entity).strip()) > 1]
            else:
                return []
                
        except Exception as e:
            logger.error(f"提取实体失败: {e}")
            return []
    
    async def extract_relations_from_text(self, text: str, entities: List[str]) -> List[Tuple[str, str, str]]:
        """
        从文本中提取关系三元组 - 采用MaiBot的RDF三元组提取方法
        
        Args:
            text: 输入文本
            entities: 已识别的实体列表
            
        Returns:
            关系三元组列表 [(subject, predicate, object), ...]
        """
        try:
            from ..statics.prompts import RDF_TRIPLE_EXTRACTION_PROMPT
            
            entities_str = json.dumps(entities, ensure_ascii=False)
            prompt = RDF_TRIPLE_EXTRACTION_PROMPT.format(
                text=text,
                entities=entities_str
            )
            
            response = await self.llm_adapter.generate_response(
                prompt,
                temperature=0.1,
                model_type="refine"  # 使用精炼模型进行关系提取
            )
            
            # 解析JSON响应
            relations = safe_parse_llm_json(response)
            
            if isinstance(relations, list):
                valid_relations = []
                for relation in relations:
                    if isinstance(relation, list) and len(relation) == 3:
                        subject, predicate, obj = relation
                        if all(isinstance(x, str) and x.strip() for x in [subject, predicate, obj]):
                            valid_relations.append((subject.strip(), predicate.strip(), obj.strip()))
                
                return valid_relations
            else:
                return []
                
        except Exception as e:
            logger.error(f"提取关系失败: {e}")
            return []
    
    async def process_message_for_knowledge_graph(self, message: MessageData, group_id: str):
        """
        处理消息并更新知识图谱
        
        Args:
            message: 消息数据
            group_id: 群组ID
        """
        try:
            text = message.content.strip()
            
            # 检查文本长度和质量
            if len(text) < 10 or text.startswith('[') or text.startswith('http'):
                return
            
            # 检查是否已经处理过
            if self._is_paragraph_processed(text, group_id):
                logger.debug(f"段落已处理过，跳过: {text[:50]}...")
                return
            
            # 提取实体
            entities = await self.extract_entities_from_text(text)
            
            if not entities:
                logger.debug(f"未提取到实体，跳过: {text[:50]}...")
                return
            
            # 更新实体信息
            await self._update_entities(entities, group_id)
            
            # 提取关系
            relations = await self.extract_relations_from_text(text, entities)
            
            # 更新关系信息
            if relations:
                await self._update_relations(relations, group_id)
            
            # 标记段落为已处理
            self._mark_paragraph_processed(text, group_id)
            
            logger.info(f"知识图谱更新完成，群组: {group_id}，实体数: {len(entities)}，关系数: {len(relations)}")
            
        except Exception as e:
            logger.error(f"处理消息更新知识图谱失败: {e}")
    
    async def _update_entities(self, entities: List[str], group_id: str):
        """更新实体信息"""
        try:
            current_time = time.time()
            
            with self.db_manager.get_connection() as conn:
                for entity in entities:
                    # 查找现有实体
                    cursor = conn.execute(
                        'SELECT id, appear_count FROM kg_entities WHERE name = ? AND group_id = ?',
                        (entity, group_id)
                    )
                    existing = cursor.fetchone()
                    
                    if existing:
                        # 更新现有实体
                        entity_id, current_count = existing
                        new_count = current_count + 1
                        conn.execute(
                            'UPDATE kg_entities SET appear_count = ?, last_active_time = ? WHERE id = ?',
                            (new_count, current_time, entity_id)
                        )
                        
                        # 更新内存缓存
                        self.entity_appear_count[group_id][entity] = new_count
                    else:
                        # 插入新实体
                        conn.execute(
                            'INSERT INTO kg_entities (name, entity_type, appear_count, last_active_time, group_id) VALUES (?, ?, ?, ?, ?)',
                            (entity, 'general', 1, current_time, group_id)
                        )
                        
                        # 更新内存缓存
                        self.entity_appear_count[group_id][entity] = 1
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"更新实体失败: {e}")
    
    async def _update_relations(self, relations: List[Tuple[str, str, str]], group_id: str):
        """更新关系信息"""
        try:
            current_time = time.time()
            
            with self.db_manager.get_connection() as conn:
                for subject, predicate, obj in relations:
                    # 插入或忽略关系
                    conn.execute(
                        'INSERT OR IGNORE INTO kg_relations (subject, predicate, object, confidence, created_time, group_id) VALUES (?, ?, ?, ?, ?, ?)',
                        (subject, predicate, obj, 1.0, current_time, group_id)
                    )
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"更新关系失败: {e}")
    
    async def query_knowledge_graph(self, query: str, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        查询知识图谱
        
        Args:
            query: 查询内容
            group_id: 群组ID
            limit: 返回数量限制
            
        Returns:
            查询结果列表
        """
        try:
            # 从查询中提取实体
            query_entities = await self.extract_entities_from_text(query)
            
            if not query_entities:
                return []
            
            results = []
            
            with self.db_manager.get_connection() as conn:
                for entity in query_entities[:3]:  # 限制查询实体数量
                    # 查找相关关系
                    cursor = conn.execute('''
                        SELECT subject, predicate, object, confidence 
                        FROM kg_relations 
                        WHERE (subject = ? OR object = ?) AND group_id = ?
                        ORDER BY confidence DESC
                        LIMIT ?
                    ''', (entity, entity, group_id, limit))
                    
                    relations = cursor.fetchall()
                    
                    for subject, predicate, obj, confidence in relations:
                        results.append({
                            'subject': subject,
                            'predicate': predicate,
                            'object': obj,
                            'confidence': confidence,
                            'relevance': self._calculate_relevance(entity, subject, obj)
                        })
            
            # 按相关性排序
            results.sort(key=lambda x: x['relevance'], reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"查询知识图谱失败: {e}")
            return []
    
    def _calculate_relevance(self, query_entity: str, subject: str, obj: str) -> float:
        """计算相关性得分"""
        relevance = 0.0
        
        # 精确匹配得分更高
        if query_entity == subject or query_entity == obj:
            relevance += 1.0
        
        # 部分匹配得分较低
        if query_entity in subject or query_entity in obj:
            relevance += 0.5
        
        if subject in query_entity or obj in query_entity:
            relevance += 0.3
        
        return relevance
    
    async def get_knowledge_graph_statistics(self, group_id: str) -> Dict[str, Any]:
        """获取知识图谱统计信息"""
        try:
            with self.db_manager.get_connection() as conn:
                # 实体统计
                cursor = conn.execute(
                    'SELECT COUNT(*), AVG(appear_count), MAX(appear_count) FROM kg_entities WHERE group_id = ?',
                    (group_id,)
                )
                entity_stats = cursor.fetchone()
                
                # 关系统计
                cursor = conn.execute(
                    'SELECT COUNT(*), AVG(confidence) FROM kg_relations WHERE group_id = ?',
                    (group_id,)
                )
                relation_stats = cursor.fetchone()
                
                # 段落统计
                cursor = conn.execute(
                    'SELECT COUNT(*) FROM kg_paragraph_hashes WHERE group_id = ?',
                    (group_id,)
                )
                paragraph_count = cursor.fetchone()[0]
                
                # 最活跃实体
                cursor = conn.execute(
                    'SELECT name, appear_count FROM kg_entities WHERE group_id = ? ORDER BY appear_count DESC LIMIT 5',
                    (group_id,)
                )
                top_entities = cursor.fetchall()
                
                return {
                    'group_id': group_id,
                    'entities': {
                        'total_count': entity_stats[0] if entity_stats[0] else 0,
                        'avg_appear_count': round(entity_stats[1], 2) if entity_stats[1] else 0,
                        'max_appear_count': entity_stats[2] if entity_stats[2] else 0,
                        'top_entities': [{'name': name, 'count': count} for name, count in top_entities]
                    },
                    'relations': {
                        'total_count': relation_stats[0] if relation_stats[0] else 0,
                        'avg_confidence': round(relation_stats[1], 2) if relation_stats[1] else 0
                    },
                    'processed_paragraphs': paragraph_count,
                    'memory_cached_entities': len(self.entity_appear_count.get(group_id, {})),
                    'memory_cached_hashes': len(self.stored_paragraph_hashes.get(group_id, set()))
                }
                
        except Exception as e:
            logger.error(f"获取知识图谱统计信息失败: {e}")
            return {}
    
    async def answer_question_with_knowledge_graph(self, question: str, group_id: str) -> str:
        """
        使用知识图谱回答问题 - 采用MaiBot的QA系统设计
        
        Args:
            question: 问题
            group_id: 群组ID
            
        Returns:
            回答内容
        """
        try:
            # 查询相关知识
            knowledge_results = await self.query_knowledge_graph(question, group_id, limit=5)
            
            if not knowledge_results:
                return "我不知道"
            
            # 构建知识上下文
            knowledge_context = []
            for result in knowledge_results:
                context_item = f"{result['subject']} {result['predicate']} {result['object']}"
                knowledge_context.append(context_item)
            
            knowledge_text = "\n".join(knowledge_context)
            
            # 使用LLM生成回答
            from ..statics.prompts import KNOWLEDGE_GRAPH_QA_PROMPT
            
            prompt = KNOWLEDGE_GRAPH_QA_PROMPT.format(
                question=question,
                knowledge_context=knowledge_text
            )
            
            response = await self.llm_adapter.generate_response(
                prompt,
                temperature=0.3,
                model_type="refine"
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"使用知识图谱回答问题失败: {e}")
            return "我不知道"