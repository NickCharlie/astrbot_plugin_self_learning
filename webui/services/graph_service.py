"""
Dashboard graph data service.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from astrbot.api import logger


def _trim_text(value: Any, limit: int = 120) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


class GraphService:
    """Build lightweight graph payloads for dashboard visualization."""

    def __init__(self, container):
        self.container = container
        self.database_manager = getattr(container, "database_manager", None)

    @staticmethod
    def _add_node(
        nodes: List[Dict[str, Any]],
        seen: Set[str],
        node_id: str,
        name: str,
        category: str,
        value: float = 1.0,
        category_index: Optional[int] = None,
        **extra: Any,
    ) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "name": _trim_text(name, 36),
                "category": category_index if category_index is not None else category,
                "category_name": category,
                "value": value,
                "symbolSize": max(18, min(58, 18 + float(value or 0) * 6)),
                **extra,
            }
        )

    @staticmethod
    def _add_link(
        links: List[Dict[str, Any]],
        seen: Set[Tuple[str, str, str]],
        source: str,
        target: str,
        label: str,
        value: float = 1.0,
    ) -> None:
        key = (source, target, label)
        reverse_key = (target, source, label)
        if key in seen or reverse_key in seen:
            return
        seen.add(key)
        links.append(
            {
                "source": source,
                "target": target,
                "value": value,
                "label": {"show": False, "formatter": label},
                "lineStyle": {"width": max(1, min(5, float(value or 1)))},
            }
        )

    @staticmethod
    def _apply_category_indices(
        nodes: List[Dict[str, Any]],
        category_names: List[str],
    ) -> List[Dict[str, str]]:
        names = list(dict.fromkeys(category_names))
        for node in nodes:
            category_name = str(
                node.get("category_name")
                or node.get("category")
                or "实体"
            )
            if category_name not in names:
                names.append(category_name)

        index = {name: idx for idx, name in enumerate(names)}
        for node in nodes:
            category_name = str(
                node.get("category_name")
                or node.get("category")
                or "实体"
            )
            node["category_name"] = category_name
            node["category"] = index.get(category_name, 0)

        return [{"name": name} for name in names]

    async def get_memory_graph(
        self,
        group_id: Optional[str] = None,
        limit: int = 120,
    ) -> Dict[str, Any]:
        """Return memory graph nodes and links from live graph cache or ORM rows."""
        limit = max(10, min(int(limit or 120), 300))
        nodes: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []
        seen_nodes: Set[str] = set()
        seen_links: Set[Tuple[str, str, str]] = set()
        groups: Set[str] = set()

        await self._append_live_memory_graph(
            nodes, links, seen_nodes, seen_links, groups, group_id, limit
        )

        if len(nodes) < 2:
            await self._append_memory_rows(
                nodes, links, seen_nodes, seen_links, groups, group_id, limit
            )

        returned_nodes = nodes[:limit]
        categories = self._apply_category_indices(
            returned_nodes,
            ["概念", "记忆", "群组", "用户", "类型"],
        )
        returned_node_ids = {node["id"] for node in returned_nodes}

        return {
            "success": True,
            "type": "memory",
            "group_id": group_id,
            "groups": sorted(groups),
            "nodes": returned_nodes,
            "links": [
                link
                for link in links
                if link.get("source") in returned_node_ids and link.get("target") in returned_node_ids
            ],
            "categories": categories,
            "stats": {
                "nodes": len(nodes),
                "links": len(links),
                "groups": len(groups),
            },
        }

    async def _append_live_memory_graph(
        self,
        nodes: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
        seen_nodes: Set[str],
        seen_links: Set[Tuple[str, str, str]],
        groups: Set[str],
        group_id: Optional[str],
        limit: int,
    ) -> None:
        try:
            try:
                from ...services.state import EnhancedMemoryGraphManager
            except ImportError:
                from services.state import EnhancedMemoryGraphManager

            manager = EnhancedMemoryGraphManager.get_instance()
            memory_graphs = getattr(manager, "memory_graphs", {}) or {}

            for gid, graph in memory_graphs.items():
                if group_id and str(gid) != group_id:
                    continue
                groups.add(str(gid))
                group_node_id = f"memory-group:{gid}"
                self._add_node(nodes, seen_nodes, group_node_id, str(gid), "群组", 2)

                graph_obj = getattr(graph, "G", None)
                if not graph_obj:
                    continue

                if callable(getattr(graph_obj, "nodes", None)):
                    node_iter = graph_obj.nodes(data=True)
                else:
                    node_iter = getattr(graph_obj, "nodes", {}).items()

                for concept, data in list(node_iter)[:limit]:
                    concept_id = f"memory-concept:{gid}:{concept}"
                    weight = (data or {}).get("weight", 1) if isinstance(data, dict) else 1
                    self._add_node(
                        nodes,
                        seen_nodes,
                        concept_id,
                        str(concept),
                        "概念",
                        weight,
                        detail=_trim_text((data or {}).get("memory_items", ""), 180)
                        if isinstance(data, dict)
                        else "",
                        group_id=str(gid),
                    )
                    self._add_link(links, seen_links, group_node_id, concept_id, "包含", 1)

                if callable(getattr(graph_obj, "edges", None)):
                    edge_iter = graph_obj.edges(data=True)
                else:
                    edge_iter = []
                    raw_edges = getattr(graph_obj, "_edges", {})
                    for source, targets in raw_edges.items():
                        for target, data in targets.items():
                            edge_iter.append((source, target, data))

                for source, target, data in list(edge_iter)[: limit * 2]:
                    source_id = f"memory-concept:{gid}:{source}"
                    target_id = f"memory-concept:{gid}:{target}"
                    strength = (data or {}).get("strength", 1) if isinstance(data, dict) else 1
                    self._add_link(links, seen_links, source_id, target_id, "关联", strength)
        except Exception as e:
            logger.warning(f"读取实时记忆图失败: {e}", exc_info=True)

    async def _append_memory_rows(
        self,
        nodes: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
        seen_nodes: Set[str],
        seen_links: Set[Tuple[str, str, str]],
        groups: Set[str],
        group_id: Optional[str],
        limit: int,
    ) -> None:
        if not self.database_manager or not hasattr(self.database_manager, "get_session"):
            return

        try:
            from sqlalchemy import desc, select

            try:
                from ...models.orm import Memory
            except ImportError:
                from models.orm import Memory

            async with self.database_manager.get_session() as session:
                stmt = select(Memory).order_by(
                    desc(Memory.importance),
                    desc(Memory.last_accessed),
                ).limit(limit)
                if group_id:
                    stmt = stmt.where(Memory.group_id == group_id)

                result = await session.execute(stmt)
                rows = result.scalars().all()

            for row in rows:
                gid = str(getattr(row, "group_id", "") or "default")
                groups.add(gid)
                group_node_id = f"memory-group:{gid}"
                memory_node_id = f"memory-row:{getattr(row, 'id', '')}"
                user_id = str(getattr(row, "user_id", "") or "unknown")
                memory_type = str(getattr(row, "memory_type", "") or "memory")
                content = getattr(row, "content", "") or ""
                importance = float(getattr(row, "importance", 1) or 1)

                self._add_node(nodes, seen_nodes, group_node_id, gid, "群组", 2)
                self._add_node(
                    nodes,
                    seen_nodes,
                    memory_node_id,
                    _trim_text(content, 28) or "记忆",
                    "记忆",
                    importance,
                    detail=_trim_text(content, 240),
                    group_id=gid,
                )
                self._add_link(links, seen_links, group_node_id, memory_node_id, "包含", 1)

                user_node_id = f"memory-user:{gid}:{user_id}"
                self._add_node(nodes, seen_nodes, user_node_id, user_id, "用户", 1.5)
                self._add_link(links, seen_links, user_node_id, memory_node_id, "关联记忆", 1)

                type_node_id = f"memory-type:{memory_type}"
                self._add_node(nodes, seen_nodes, type_node_id, memory_type, "类型", 1.2)
                self._add_link(links, seen_links, type_node_id, memory_node_id, "类型", 1)

                for keyword in self._extract_keywords(content)[:2]:
                    concept_id = f"memory-keyword:{gid}:{keyword}"
                    self._add_node(nodes, seen_nodes, concept_id, keyword, "概念", 1.4)
                    self._add_link(links, seen_links, concept_id, memory_node_id, "提及", 1)
        except Exception as e:
            logger.warning(f"读取记忆表失败: {e}", exc_info=True)

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        words = re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", text or "")
        stop_words = {"这个", "那个", "什么", "可以", "就是", "一个", "没有", "我们", "你们"}
        result = []
        for word in words:
            if word in stop_words:
                continue
            if word not in result:
                result.append(word)
        return result[:8]

    async def get_knowledge_graph(
        self,
        group_id: Optional[str] = None,
        limit: int = 120,
    ) -> Dict[str, Any]:
        """Return knowledge graph nodes and links from KG ORM tables."""
        limit = max(10, min(int(limit or 120), 300))
        nodes: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []
        seen_nodes: Set[str] = set()
        seen_links: Set[Tuple[str, str, str]] = set()
        groups: Set[str] = set()
        categories: Set[str] = set()

        if self.database_manager and hasattr(self.database_manager, "get_session"):
            try:
                from sqlalchemy import desc, select

                try:
                    from ...models.orm import KGEntity, KGRelation
                except ImportError:
                    from models.orm import KGEntity, KGRelation

                async with self.database_manager.get_session() as session:
                    entity_stmt = select(KGEntity).order_by(
                        desc(KGEntity.appear_count),
                        desc(KGEntity.last_active_time),
                    ).limit(limit)
                    relation_stmt = select(KGRelation).order_by(
                        desc(KGRelation.confidence),
                        desc(KGRelation.created_time),
                    ).limit(limit * 2)
                    if group_id:
                        entity_stmt = entity_stmt.where(KGEntity.group_id == group_id)
                        relation_stmt = relation_stmt.where(KGRelation.group_id == group_id)

                    entity_result = await session.execute(entity_stmt)
                    relation_result = await session.execute(relation_stmt)
                    entities = entity_result.scalars().all()
                    relations = relation_result.scalars().all()

                for entity in entities:
                    gid = str(getattr(entity, "group_id", "") or "global")
                    groups.add(gid)
                    entity_type = str(getattr(entity, "entity_type", "") or "实体")
                    categories.add(entity_type)
                    node_id = self._kg_node_id(gid, entity.name)
                    self._add_node(
                        nodes,
                        seen_nodes,
                        node_id,
                        entity.name,
                        entity_type,
                        float(entity.appear_count or 1),
                        group_id=gid,
                        detail=f"{entity_type} · 出现 {entity.appear_count or 0} 次",
                    )

                for relation in relations:
                    gid = str(getattr(relation, "group_id", "") or "global")
                    groups.add(gid)
                    source_id = self._kg_node_id(gid, relation.subject)
                    target_id = self._kg_node_id(gid, relation.object)
                    if source_id not in seen_nodes:
                        categories.add("实体")
                        self._add_node(nodes, seen_nodes, source_id, relation.subject, "实体", 1, group_id=gid)
                    if target_id not in seen_nodes:
                        categories.add("实体")
                        self._add_node(nodes, seen_nodes, target_id, relation.object, "实体", 1, group_id=gid)
                    self._add_link(
                        links,
                        seen_links,
                        source_id,
                        target_id,
                        relation.predicate or "关联",
                        float(relation.confidence or 1),
                    )
            except Exception as e:
                logger.warning(f"读取知识图谱失败: {e}", exc_info=True)

        returned_nodes = nodes[:limit]
        categories_payload = self._apply_category_indices(
            returned_nodes,
            sorted(categories or {"实体"}),
        )
        returned_node_ids = {node["id"] for node in returned_nodes}

        return {
            "success": True,
            "type": "knowledge",
            "group_id": group_id,
            "groups": sorted(groups),
            "nodes": returned_nodes,
            "links": [
                link
                for link in links
                if link.get("source") in returned_node_ids and link.get("target") in returned_node_ids
            ],
            "categories": categories_payload,
            "stats": {
                "nodes": len(nodes),
                "links": len(links),
                "groups": len(groups),
            },
        }

    @staticmethod
    def _kg_node_id(group_id: str, name: str) -> str:
        return f"kg:{group_id}:{name}"
