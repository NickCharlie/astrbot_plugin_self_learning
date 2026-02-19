"""
知识图谱管理器 - 基于MaiBot的知识图谱系统设计
实现实体关系提取、RDF三元组构建和知识图谱查询
使用 SQLAlchemy ORM 进行数据库操作
"""
import json
import time
import hashlib
from typing import Dict, List, Optional, Tuple, Any, Set
from collections import defaultdict

from sqlalchemy import select, update, func, or_

from astrbot.api import logger

from ..core.interfaces import MessageData, ServiceLifecycle
from ..core.framework_llm_adapter import FrameworkLLMAdapter
from ..config import PluginConfig
from ..exceptions import KnowledgeGraphError, ModelAccessError
from ..utils.json_utils import safe_parse_llm_json
from ..models.orm.knowledge_graph import KGEntity, KGRelation, KGParagraphHash


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

    def __init__(self, config: PluginConfig = None, db_manager=None,
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

        self._initialized = True

    @classmethod
    def get_instance(cls) -> 'KnowledgeGraphManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

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
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    async def _is_paragraph_processed(self, text: str, group_id: str) -> bool:
        """检查段落是否已经处理过"""
        para_hash = self._get_paragraph_hash(text)

        # 先检查内存缓存
        if para_hash in self.stored_paragraph_hashes[group_id]:
            return True

        # 检查数据库
        if not self.db_manager or not hasattr(self.db_manager, 'get_session'):
            return False

        try:
            async with self.db_manager.get_session() as session:
                stmt = select(KGParagraphHash.id).where(
                    KGParagraphHash.hash_value == para_hash,
                    KGParagraphHash.group_id == group_id
                ).limit(1)
                result = await session.execute(stmt)
                exists = result.scalar() is not None

                if exists:
                    self.stored_paragraph_hashes[group_id].add(para_hash)

                return exists
        except Exception as e:
            logger.error(f"检查段落hash失败: {e}")
            return False

    async def _mark_paragraph_processed(self, text: str, group_id: str):
        """标记段落为已处理"""
        para_hash = self._get_paragraph_hash(text)

        if not self.db_manager or not hasattr(self.db_manager, 'get_session'):
            return

        try:
            async with self.db_manager.get_session() as session:
                # 检查是否已存在
                stmt = select(KGParagraphHash.id).where(
                    KGParagraphHash.hash_value == para_hash,
                    KGParagraphHash.group_id == group_id
                ).limit(1)
                result = await session.execute(stmt)
                if result.scalar() is None:
                    new_hash = KGParagraphHash(
                        hash_value=para_hash,
                        group_id=group_id,
                        created_time=time.time()
                    )
                    session.add(new_hash)
                    await session.commit()

                # 更新内存缓存
                self.stored_paragraph_hashes[group_id].add(para_hash)

        except Exception as e:
            logger.error(f"标记段落hash失败: {e}")

    async def add_entity(
        self,
        entity_id: str,
        entity_type: str = 'general',
        properties: Dict[str, Any] = None,
        context: str = ''
    ):
        """
        添加实体到知识图谱

        Args:
            entity_id: 实体ID/名称
            entity_type: 实体类型
            properties: 实体属性
            context: 上下文描述
        """
        if not self.db_manager or not hasattr(self.db_manager, 'get_session'):
            logger.debug("db_manager 为空或不支持 ORM，无法添加实体")
            return

        try:
            current_time = time.time()

            async with self.db_manager.get_session() as session:
                stmt = select(KGEntity).where(
                    KGEntity.name == entity_id,
                    KGEntity.group_id == 'global'
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.appear_count += 1
                    existing.last_active_time = current_time
                    existing.entity_type = entity_type
                else:
                    new_entity = KGEntity(
                        name=entity_id,
                        entity_type=entity_type,
                        appear_count=1,
                        last_active_time=current_time,
                        group_id='global'
                    )
                    session.add(new_entity)

                await session.commit()

            logger.debug(f"添加实体到知识图谱: {entity_id} ({entity_type})")

        except Exception as e:
            logger.error(f"添加实体失败: {e}")

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
                model_type="filter"
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
                model_type="refine"
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

    async def process_message_for_knowledge_graph(self, message, group_id: str):
        """
        处理消息并更新知识图谱

        Args:
            message: 消息数据（MessageData 或 dict）
            group_id: 群组ID
        """
        try:
            # 兼容 dict 和 MessageData
            if isinstance(message, dict):
                text = (message.get('content', '') or message.get('message', '')).strip()
            else:
                text = (getattr(message, 'content', '') or getattr(message, 'message', '')).strip()

            # 检查文本长度和质量
            if len(text) < 10 or text.startswith('[') or text.startswith('http'):
                return

            # 检查是否已经处理过
            if await self._is_paragraph_processed(text, group_id):
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
            await self._mark_paragraph_processed(text, group_id)

            logger.info(f"知识图谱更新完成，群组: {group_id}，实体数: {len(entities)}，关系数: {len(relations)}")

        except Exception as e:
            logger.error(f"处理消息更新知识图谱失败: {e}")

    async def _update_entities(self, entities: List[str], group_id: str):
        """更新实体信息"""
        if not self.db_manager or not hasattr(self.db_manager, 'get_session'):
            return

        try:
            current_time = time.time()

            async with self.db_manager.get_session() as session:
                for entity_name in entities:
                    stmt = select(KGEntity).where(
                        KGEntity.name == entity_name,
                        KGEntity.group_id == group_id
                    )
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.appear_count += 1
                        existing.last_active_time = current_time
                        self.entity_appear_count[group_id][entity_name] = existing.appear_count
                    else:
                        new_entity = KGEntity(
                            name=entity_name,
                            entity_type='general',
                            appear_count=1,
                            last_active_time=current_time,
                            group_id=group_id
                        )
                        session.add(new_entity)
                        self.entity_appear_count[group_id][entity_name] = 1

                await session.commit()

        except Exception as e:
            logger.error(f"更新实体失败: {e}")

    async def _update_relations(self, relations: List[Tuple[str, str, str]], group_id: str):
        """更新关系信息"""
        if not self.db_manager or not hasattr(self.db_manager, 'get_session'):
            return

        try:
            current_time = time.time()

            async with self.db_manager.get_session() as session:
                for subject, predicate, obj in relations:
                    # 检查是否已存在
                    stmt = select(KGRelation.id).where(
                        KGRelation.subject == subject,
                        KGRelation.predicate == predicate,
                        KGRelation.object == obj,
                        KGRelation.group_id == group_id
                    ).limit(1)
                    result = await session.execute(stmt)
                    if result.scalar() is None:
                        new_relation = KGRelation(
                            subject=subject,
                            predicate=predicate,
                            object=obj,
                            confidence=1.0,
                            created_time=current_time,
                            group_id=group_id
                        )
                        session.add(new_relation)

                await session.commit()

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
        if not self.db_manager or not hasattr(self.db_manager, 'get_session'):
            return []

        try:
            # 从查询中提取实体
            query_entities = await self.extract_entities_from_text(query)

            if not query_entities:
                return []

            results = []

            async with self.db_manager.get_session() as session:
                for entity in query_entities[:3]:
                    stmt = select(KGRelation).where(
                        or_(KGRelation.subject == entity, KGRelation.object == entity),
                        KGRelation.group_id == group_id
                    ).order_by(KGRelation.confidence.desc()).limit(limit)

                    result = await session.execute(stmt)
                    relations = result.scalars().all()

                    for rel in relations:
                        results.append({
                            'subject': rel.subject,
                            'predicate': rel.predicate,
                            'object': rel.object,
                            'confidence': rel.confidence,
                            'relevance': self._calculate_relevance(entity, rel.subject, rel.object)
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

        if query_entity == subject or query_entity == obj:
            relevance += 1.0

        if query_entity in subject or query_entity in obj:
            relevance += 0.5

        if subject in query_entity or obj in query_entity:
            relevance += 0.3

        return relevance

    async def get_knowledge_graph_statistics(self, group_id: str) -> Dict[str, Any]:
        """获取知识图谱统计信息"""
        if not self.db_manager or not hasattr(self.db_manager, 'get_session'):
            return {}

        try:
            async with self.db_manager.get_session() as session:
                # 实体统计
                stmt = select(
                    func.count(KGEntity.id),
                    func.avg(KGEntity.appear_count),
                    func.max(KGEntity.appear_count)
                ).where(KGEntity.group_id == group_id)
                result = await session.execute(stmt)
                entity_stats = result.one()

                # 关系统计
                stmt = select(
                    func.count(KGRelation.id),
                    func.avg(KGRelation.confidence)
                ).where(KGRelation.group_id == group_id)
                result = await session.execute(stmt)
                relation_stats = result.one()

                # 段落统计
                stmt = select(func.count(KGParagraphHash.id)).where(
                    KGParagraphHash.group_id == group_id
                )
                result = await session.execute(stmt)
                paragraph_count = result.scalar() or 0

                # 最活跃实体
                stmt = select(KGEntity.name, KGEntity.appear_count).where(
                    KGEntity.group_id == group_id
                ).order_by(KGEntity.appear_count.desc()).limit(5)
                result = await session.execute(stmt)
                top_entities = result.all()

                return {
                    'group_id': group_id,
                    'entities': {
                        'total_count': entity_stats[0] or 0,
                        'avg_appear_count': round(entity_stats[1], 2) if entity_stats[1] else 0,
                        'max_appear_count': entity_stats[2] or 0,
                        'top_entities': [{'name': name, 'count': count} for name, count in top_entities]
                    },
                    'relations': {
                        'total_count': relation_stats[0] or 0,
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
