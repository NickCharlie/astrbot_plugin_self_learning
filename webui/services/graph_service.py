"""
Dashboard graph data service.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from defusedxml import ElementTree as ET

from astrbot.api import logger


def _trim_text(value: Any, limit: int = 120) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


class GraphService:
    """Build lightweight graph payloads for dashboard visualization."""

    def __init__(self, container):
        self.container = container
        self.database_manager = getattr(container, "database_manager", None)
        self.plugin_config = getattr(container, "plugin_config", None)
        self.v2_integration = getattr(container, "v2_integration", None)

    def _delegation_status(self) -> Dict[str, Any]:
        delegation = getattr(self.container, "feature_delegation", None)
        if not delegation:
            return {}

        status_getter = getattr(delegation, "status", None)
        if not callable(status_getter):
            return {}

        try:
            status = status_getter() or {}
        except Exception as exc:
            logger.debug(f"读取功能委托状态失败: {exc}")
            return {}
        return status if isinstance(status, dict) else {}

    def _maybe_add_delegated_empty_state(
        self,
        payload: Dict[str, Any],
        graph_type: str,
    ) -> Dict[str, Any]:
        if payload.get("nodes"):
            return payload

        status = self._delegation_status()
        if not status.get("memory_delegated"):
            return payload

        plugin_name = status.get("memory_plugin") or "LivingMemory"
        if graph_type == "memory":
            message = f"{plugin_name} 后端图谱暂无可展示节点。"
        else:
            message = f"长期记忆已委托给 {plugin_name}，当前本地知识图谱为空。"

        payload.update(
            {
                "data_source": "livingmemory_backend_empty",
                "empty_reason": "graph_backend_empty",
                "message": message,
                "delegation": status,
            }
        )
        return payload

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
        source_stats: Dict[str, Any] = {}

        livingmemory_used = await self._append_livingmemory_graph_store(
            nodes,
            links,
            seen_nodes,
            seen_links,
            groups,
            group_id,
            limit,
            source_stats,
        )

        if not livingmemory_used:
            await self._append_live_memory_graph(
                nodes, links, seen_nodes, seen_links, groups, group_id, limit
            )

        if not livingmemory_used and len(nodes) < limit:
            await self._append_v2_mem0_memories(
                nodes, links, seen_nodes, seen_links, groups, group_id, limit
            )

        if not livingmemory_used and len(nodes) < 2:
            await self._append_memory_rows(
                nodes, links, seen_nodes, seen_links, groups, group_id, limit
            )

        returned_nodes = nodes[:limit]
        categories = self._apply_category_indices(
            returned_nodes,
            ["概念", "记忆", "群组", "用户", "类型"],
        )
        returned_node_ids = {node["id"] for node in returned_nodes}

        payload = {
            "success": True,
            "type": "memory",
            "data_source": (
                "livingmemory_graph_store" if livingmemory_used else "self_learning"
            ),
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
        if source_stats:
            payload["source_stats"] = source_stats
        return self._maybe_add_delegated_empty_state(payload, "memory")

    async def _append_livingmemory_graph_store(
        self,
        nodes: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
        seen_nodes: Set[str],
        seen_links: Set[Tuple[str, str, str]],
        groups: Set[str],
        group_id: Optional[str],
        limit: int,
        source_stats: Dict[str, Any],
    ) -> bool:
        """Append graph data directly from LivingMemory's backend graph store."""
        graph_store, memory_engine = self._livingmemory_graph_backend()
        if graph_store is None:
            return False

        try:
            await self._append_livingmemory_stats(memory_engine, source_stats)
            snapshot = await self._read_livingmemory_snapshot(
                graph_store,
                group_id=group_id,
                limit=limit,
            )
            if not self._livingmemory_snapshot_has_data(snapshot):
                return False

            self._append_livingmemory_snapshot(
                snapshot,
                nodes,
                links,
                seen_nodes,
                seen_links,
                groups,
                limit,
            )
            return bool(nodes)
        except Exception as e:
            logger.warning(f"读取 LivingMemory 后端图谱失败: {e}", exc_info=True)
            return False

    async def _append_livingmemory_stats(
        self,
        memory_engine: Any,
        source_stats: Dict[str, Any],
    ) -> None:
        stats_getter = getattr(memory_engine, "get_statistics", None)
        if not callable(stats_getter):
            return

        try:
            stats = stats_getter()
            if inspect.isawaitable(stats):
                stats = await stats
            if isinstance(stats, dict):
                source_stats.update(stats)
        except Exception as exc:
            logger.debug(f"读取 LivingMemory 图谱统计失败，继续加载图谱快照: {exc}")

    def _livingmemory_graph_backend(self) -> Tuple[Any, Any]:
        delegation = self._delegation()
        star = None
        if delegation:
            memory_plugin = getattr(delegation, "memory_plugin", None)
            if callable(memory_plugin):
                try:
                    star = memory_plugin()
                except Exception:
                    star = None

        plugin = getattr(star, "star_cls", None)
        if plugin is None:
            return None, None

        initializer = getattr(plugin, "initializer", None)
        memory_engine = (
            getattr(initializer, "memory_engine", None)
            or getattr(plugin, "memory_engine", None)
        )
        graph_store = getattr(memory_engine, "graph_store", None)
        return graph_store, memory_engine

    def _delegation(self) -> Optional[Any]:
        delegation = getattr(self.container, "feature_delegation", None)
        if delegation:
            return delegation

        config = getattr(self.container, "plugin_config", None)
        factory_manager = getattr(self.container, "factory_manager", None)
        if not config or not factory_manager:
            return None

        try:
            service_factory = factory_manager.get_service_factory()
            context = getattr(service_factory, "context", None)
            if not context:
                return None
            try:
                from ...core.feature_delegation import FeatureDelegation
            except ImportError:
                from core.feature_delegation import FeatureDelegation

            delegation = FeatureDelegation(config, context)
            self.container.feature_delegation = delegation
            return delegation
        except Exception:
            return None

    async def _read_livingmemory_snapshot(
        self,
        graph_store: Any,
        group_id: Optional[str],
        limit: int,
    ) -> Dict[str, Any]:
        snapshot_getter = getattr(graph_store, "get_graph_snapshot", None)
        if not callable(snapshot_getter):
            return {}

        limit_memories = max(1, min(max(limit // 8, 12), 24))
        limit_entries = max(12, min(limit, 80))
        limit_nodes = max(12, min(limit, 80))
        limit_edges = max(12, min(limit * 2, 120))

        session_candidates = self._livingmemory_session_candidates(group_id)
        last_snapshot: Dict[str, Any] = {}
        for session_id in session_candidates:
            snapshot = snapshot_getter(
                session_id=session_id,
                persona_id=None,
                limit_memories=limit_memories,
                limit_entries=limit_entries,
                limit_nodes=limit_nodes,
                limit_edges=limit_edges,
            )
            if inspect.isawaitable(snapshot):
                snapshot = await snapshot
            if isinstance(snapshot, dict):
                last_snapshot = snapshot
                if self._livingmemory_snapshot_has_data(snapshot):
                    return snapshot
        return last_snapshot

    def _livingmemory_session_candidates(self, group_id: Optional[str]) -> List[Optional[str]]:
        if not group_id:
            return [None]

        candidates: List[Optional[str]] = []
        mapping = getattr(self.container, "group_id_to_unified_origin", None)
        if isinstance(mapping, dict):
            mapped = mapping.get(str(group_id))
            if mapped:
                candidates.append(str(mapped))
        candidates.append(str(group_id))
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _livingmemory_snapshot_has_data(snapshot: Any) -> bool:
        if not isinstance(snapshot, dict):
            return False
        return any(
            bool(snapshot.get(key))
            for key in ("nodes", "edges", "entries", "memories")
        )

    def _append_livingmemory_snapshot(
        self,
        snapshot: Dict[str, Any],
        nodes: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
        seen_nodes: Set[str],
        seen_links: Set[Tuple[str, str, str]],
        groups: Set[str],
        limit: int,
    ) -> None:
        raw_nodes = self._safe_items(snapshot.get("nodes"))
        raw_edges = self._safe_items(snapshot.get("edges"))
        raw_entries = self._safe_items(snapshot.get("entries"))
        raw_memories = self._safe_items(snapshot.get("memories"))
        raw_id_to_node_id: Dict[str, str] = {}
        initial_link_count = len(links)
        max_new_links = max(1, int(limit or 1) * 3)

        def link_budget_exhausted() -> bool:
            return len(links) - initial_link_count >= max_new_links

        for item in raw_nodes:
            if len(nodes) >= limit:
                break
            raw_id = item.get("id")
            if raw_id is None:
                continue
            node_id = f"livingmemory-node:{raw_id}"
            raw_id_to_node_id[str(raw_id)] = node_id
            category = self._livingmemory_node_category(item)
            label = (
                item.get("label")
                or item.get("canonical_value")
                or item.get("value")
                or item.get("key")
                or str(raw_id)
            )
            detail = self._livingmemory_node_detail(item)
            self._add_node(
                nodes,
                seen_nodes,
                node_id,
                str(label),
                category,
                self._to_float(
                    item.get("weight")
                    or item.get("entry_count")
                    or item.get("memory_count"),
                    1,
                ),
                detail=detail,
                source="livingmemory",
                raw_id=raw_id,
            )

        memory_node_ids: Dict[str, str] = {}
        for item in raw_memories:
            session_id = item.get("session_id")
            if session_id:
                groups.add(str(session_id))
            if len(nodes) >= limit:
                continue
            memory_id = item.get("memory_id")
            if memory_id is None:
                continue
            node_id = f"livingmemory-memory:{memory_id}"
            memory_node_ids[str(memory_id)] = node_id
            summary = item.get("summary") or f"记忆 {memory_id}"
            self._add_node(
                nodes,
                seen_nodes,
                node_id,
                str(summary),
                "记忆",
                self._to_float(
                    item.get("importance") or item.get("entry_count"),
                    1,
                ),
                detail=_trim_text(summary, 240),
                group_id=str(session_id) if session_id else None,
                source="livingmemory",
                raw_id=memory_id,
            )

        for edge in raw_edges:
            if link_budget_exhausted():
                break
            source = raw_id_to_node_id.get(str(edge.get("source")))
            target = raw_id_to_node_id.get(str(edge.get("target")))
            if not source or not target:
                continue
            self._add_link(
                links,
                seen_links,
                source,
                target,
                str(edge.get("relation_type") or "关联"),
                self._to_float(edge.get("weight") or edge.get("confidence"), 1),
            )

        for entry in raw_entries:
            session_id = entry.get("session_id")
            if session_id:
                groups.add(str(session_id))
            memory_id = entry.get("memory_id")
            memory_node_id = memory_node_ids.get(str(memory_id))
            if not memory_node_id:
                continue
            label = str(
                entry.get("relation_type")
                or entry.get("entry_type")
                or "提及"
            )
            for raw_node_id in self._safe_items(entry.get("node_ids"))[:6]:
                if link_budget_exhausted():
                    break
                target = raw_id_to_node_id.get(str(raw_node_id))
                if target:
                    self._add_link(links, seen_links, memory_node_id, target, label, 1)

        if not groups and raw_memories:
            groups.add("LivingMemory")

    @staticmethod
    def _safe_items(value: Any) -> List[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _livingmemory_node_category(item: Dict[str, Any]) -> str:
        node_type = str(item.get("type") or item.get("node_type") or "实体")
        return {
            "person": "人物",
            "topic": "主题",
            "fact": "事实",
            "summary": "摘要",
            "entity": "实体",
            "other": "实体",
        }.get(node_type.lower(), node_type or "实体")

    @staticmethod
    def _livingmemory_node_detail(item: Dict[str, Any]) -> str:
        parts = [
            item.get("canonical_value"),
            f"条目 {item.get('entry_count')}" if item.get("entry_count") is not None else None,
            f"记忆 {item.get('memory_count')}" if item.get("memory_count") is not None else None,
            f"度 {item.get('degree')}" if item.get("degree") is not None else None,
        ]
        return _trim_text(" · ".join(str(part) for part in parts if part), 240)

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

    async def _append_v2_mem0_memories(
        self,
        nodes: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
        seen_nodes: Set[str],
        seen_links: Set[Tuple[str, str, str]],
        groups: Set[str],
        group_id: Optional[str],
        limit: int,
    ) -> None:
        """Append memories from the active Mem0 manager when v2 is enabled."""
        manager = self._get_v2_manager("_memory_manager")
        if manager is None:
            return

        memory_store = getattr(manager, "_memory", None)
        if not memory_store:
            return

        group_ids = self._candidate_group_ids(group_id, manager, self.v2_integration)
        if not group_ids:
            return

        try:
            for gid in group_ids:
                if len(nodes) >= limit:
                    break

                payload = await asyncio.to_thread(memory_store.get_all, agent_id=gid)
                entries = self._extract_mem0_entries(payload)
                if not entries:
                    continue

                groups.add(str(gid))
                group_node_id = f"memory-group:{gid}"
                self._add_node(nodes, seen_nodes, group_node_id, str(gid), "群组", 2)

                for index, entry in enumerate(entries):
                    if len(nodes) >= limit:
                        break
                    if not isinstance(entry, dict):
                        continue
                    content = (
                        entry.get("memory")
                        or entry.get("content")
                        or entry.get("text")
                        or entry.get("value")
                        or ""
                    )
                    if not content:
                        continue

                    entry_id = entry.get("id") or f"{index}:{_trim_text(content, 40)}"
                    memory_node_id = f"mem0:{gid}:{entry_id}"
                    self._add_node(
                        nodes,
                        seen_nodes,
                        memory_node_id,
                        _trim_text(content, 28),
                        "记忆",
                        self._to_float(entry.get("score"), 1),
                        detail=_trim_text(content, 240),
                        group_id=str(gid),
                        source="mem0",
                    )
                    self._add_link(links, seen_links, group_node_id, memory_node_id, "包含", 1)

                    user_id = entry.get("user_id")
                    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
                    if not user_id:
                        user_id = metadata.get("sender_name") or metadata.get("sender_id")
                    if user_id:
                        user_node_id = f"memory-user:{gid}:{user_id}"
                        self._add_node(nodes, seen_nodes, user_node_id, str(user_id), "用户", 1.5)
                        self._add_link(links, seen_links, user_node_id, memory_node_id, "关联记忆", 1)

                    for keyword in self._extract_keywords(str(content))[:2]:
                        concept_id = f"memory-keyword:{gid}:{keyword}"
                        self._add_node(nodes, seen_nodes, concept_id, keyword, "概念", 1.4)
                        self._add_link(links, seen_links, concept_id, memory_node_id, "提及", 1)
        except Exception as e:
            logger.warning(f"读取 Mem0 记忆失败: {e}", exc_info=True)

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
        """Return knowledge graph nodes and links from LivingMemory or local stores."""
        limit = max(10, min(int(limit or 120), 300))
        nodes: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []
        seen_nodes: Set[str] = set()
        seen_links: Set[Tuple[str, str, str]] = set()
        groups: Set[str] = set()
        categories: Set[str] = set()
        source_stats: Dict[str, Any] = {}

        livingmemory_used = await self._append_livingmemory_graph_store(
            nodes,
            links,
            seen_nodes,
            seen_links,
            groups,
            group_id,
            limit,
            source_stats,
        )

        if not livingmemory_used:
            await self._append_lightrag_graph(
                nodes, links, seen_nodes, seen_links, groups, categories, group_id, limit
            )

        if (
            not livingmemory_used
            and self.database_manager
            and hasattr(self.database_manager, "get_session")
        ):
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

        payload = {
            "success": True,
            "type": "knowledge",
            "data_source": (
                "livingmemory_graph_store" if livingmemory_used else "self_learning"
            ),
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
        if source_stats:
            payload["source_stats"] = source_stats
        return self._maybe_add_delegated_empty_state(payload, "knowledge")

    @staticmethod
    def _kg_node_id(group_id: str, name: str) -> str:
        return f"kg:{group_id}:{name}"

    def _get_v2_manager(self, attr_name: str) -> Any:
        if not self.v2_integration:
            return None
        return getattr(self.v2_integration, attr_name, None)

    def _candidate_group_ids(self, group_id: Optional[str], *sources: Any) -> List[str]:
        if group_id:
            return [str(group_id)]

        candidates: List[str] = []
        mapping = getattr(self.container, "group_id_to_unified_origin", None)
        if isinstance(mapping, dict):
            candidates.extend(str(key) for key in mapping.keys())

        for source in sources:
            for attr_name in ("memory_graphs", "_instances", "_processed_counts", "_ingestion_buffer"):
                value = getattr(source, attr_name, None)
                if isinstance(value, dict):
                    candidates.extend(str(key) for key in value.keys())

        return list(dict.fromkeys(candidate for candidate in candidates if candidate))

    @staticmethod
    def _extract_mem0_entries(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            for key in ("results", "memories", "data"):
                entries = payload.get(key)
                if isinstance(entries, list):
                    return entries
            return []
        if isinstance(payload, list):
            return payload
        return []

    async def _append_lightrag_graph(
        self,
        nodes: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
        seen_nodes: Set[str],
        seen_links: Set[Tuple[str, str, str]],
        groups: Set[str],
        categories: Set[str],
        group_id: Optional[str],
        limit: int,
    ) -> None:
        base_dir = self._lightrag_base_dir()
        if not base_dir or not os.path.isdir(base_dir):
            return

        manager = self._get_v2_manager("_knowledge_manager")
        group_ids = self._lightrag_group_ids(base_dir, group_id, manager)
        if not group_ids:
            return

        try:
            for gid in group_ids:
                if len(nodes) >= limit:
                    break
                group_dir = self._safe_child_dir(base_dir, gid)
                if not group_dir:
                    continue
                graph_file = os.path.join(group_dir, "graph_chunk_entity_relation.graphml")
                if not os.path.isfile(graph_file):
                    continue

                graph_nodes, graph_edges = self._read_graphml(graph_file)
                if not graph_nodes and not graph_edges:
                    continue

                groups.add(str(gid))
                for raw_id, data in graph_nodes:
                    if len(nodes) >= limit:
                        break
                    label = self._graphml_label(data, raw_id)
                    category = self._graphml_category(data)
                    categories.add(category)
                    self._add_node(
                        nodes,
                        seen_nodes,
                        self._lightrag_node_id(gid, raw_id),
                        label,
                        category,
                        self._to_float(data.get("weight") or data.get("rank"), 1),
                        group_id=str(gid),
                        detail=_trim_text(
                            data.get("description")
                            or data.get("source_id")
                            or category,
                            240,
                        ),
                        source="lightrag",
                    )

                for source, target, data in graph_edges:
                    label = (
                        data.get("predicate")
                        or data.get("relation")
                        or data.get("keywords")
                        or data.get("description")
                        or "关联"
                    )
                    self._add_link(
                        links,
                        seen_links,
                        self._lightrag_node_id(gid, source),
                        self._lightrag_node_id(gid, target),
                        _trim_text(label, 30),
                        self._to_float(data.get("weight") or data.get("confidence"), 1),
                    )
        except Exception as e:
            logger.warning(f"读取 LightRAG 图谱失败: {e}", exc_info=True)

    def _lightrag_base_dir(self) -> Optional[str]:
        manager = self._get_v2_manager("_knowledge_manager")
        base_dir = getattr(manager, "_base_dir", None)
        if base_dir:
            return str(base_dir)

        data_dir = getattr(self.plugin_config, "data_dir", None)
        if data_dir:
            return os.path.join(str(data_dir), "lightrag")
        return None

    def _lightrag_group_ids(
        self,
        base_dir: str,
        group_id: Optional[str],
        manager: Any,
    ) -> List[str]:
        candidates = self._candidate_group_ids(group_id, manager, self.v2_integration)
        if not group_id:
            try:
                candidates.extend(
                    entry.name
                    for entry in os.scandir(base_dir)
                    if entry.is_dir()
                )
            except OSError:
                pass
        return list(dict.fromkeys(candidate for candidate in candidates if candidate))

    @staticmethod
    def _safe_child_dir(base_dir: str, child: str) -> Optional[str]:
        base_abs = os.path.abspath(base_dir)
        candidate = os.path.abspath(os.path.join(base_abs, str(child)))
        try:
            if os.path.commonpath([base_abs, candidate]) != base_abs:
                return None
        except ValueError:
            return None
        return candidate

    @staticmethod
    def _read_graphml(path: str) -> Tuple[List[Tuple[str, Dict[str, str]]], List[Tuple[str, str, Dict[str, str]]]]:
        tree = ET.parse(path)
        root = tree.getroot()

        namespace = ""
        if root.tag.startswith("{"):
            namespace = root.tag.split("}", 1)[0][1:]

        def tag(name: str) -> str:
            return f"{{{namespace}}}{name}" if namespace else name

        key_names: Dict[str, str] = {}
        for key in root.findall(f".//{tag('key')}"):
            key_id = key.attrib.get("id")
            if key_id:
                key_names[key_id] = key.attrib.get("attr.name") or key_id

        graph = root.find(f".//{tag('graph')}")
        if graph is None:
            return [], []

        def data_map(element: ET.Element) -> Dict[str, str]:
            values: Dict[str, str] = {}
            for data in element.findall(tag("data")):
                key = data.attrib.get("key")
                if not key:
                    continue
                values[key_names.get(key, key)] = (data.text or "").strip()
            return values

        graph_nodes = [
            (node.attrib.get("id", ""), data_map(node))
            for node in graph.findall(tag("node"))
            if node.attrib.get("id")
        ]
        graph_edges = [
            (
                edge.attrib.get("source", ""),
                edge.attrib.get("target", ""),
                data_map(edge),
            )
            for edge in graph.findall(tag("edge"))
            if edge.attrib.get("source") and edge.attrib.get("target")
        ]
        return graph_nodes, graph_edges

    @staticmethod
    def _graphml_label(data: Dict[str, str], fallback: str) -> str:
        for key in ("entity_id", "entity_name", "name", "label"):
            if data.get(key):
                return str(data[key]).strip('"')
        return str(fallback).strip('"')

    @staticmethod
    def _graphml_category(data: Dict[str, str]) -> str:
        category = (
            data.get("entity_type")
            or data.get("type")
            or data.get("category")
            or "实体"
        )
        return str(category).strip('"') or "实体"

    @staticmethod
    def _lightrag_node_id(group_id: str, raw_id: str) -> str:
        return f"lightrag:{group_id}:{raw_id}"

    @staticmethod
    def _to_float(value: Any, default: float = 1.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
