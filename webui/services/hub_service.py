"""Service layer for the stable Self Learning Hub API."""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional

from .graph_service import GraphService
from .integration_service import IntegrationService
from .learning_service import LearningService
from .metrics_service import MetricsService
from .persona_review_service import PersonaReviewService


class HubService:
    """Aggregate self-learning capabilities behind a stable platform contract."""

    API_VERSION = "v1"
    BASE_PATH = "/api/hub/v1"

    ENDPOINTS = [
        {
            "method": "GET",
            "path": f"{BASE_PATH}/manifest",
            "capability": "discovery",
            "description": "Discover Hub API version, auth, endpoint map, and payload examples.",
        },
        {
            "method": "GET",
            "path": f"{BASE_PATH}/status",
            "capability": "status",
            "description": "Read runtime health, integration delegation, and available capabilities.",
        },
        {
            "method": "POST",
            "path": f"{BASE_PATH}/context",
            "capability": "context.build",
            "description": "Build prompt-ready social, jargon, few-shot, and V2 memory context.",
        },
        {
            "method": "POST",
            "path": f"{BASE_PATH}/memories/remember",
            "capability": "memory.write",
            "description": "Persist an explicit quoted memory and link expression examples.",
        },
        {
            "method": "POST",
            "path": f"{BASE_PATH}/messages/ingest",
            "capability": "message.ingest",
            "description": "Ingest a normalized external message into Self Learning stores.",
        },
        {
            "method": "POST",
            "path": f"{BASE_PATH}/learning/trigger",
            "capability": "learning.trigger",
            "description": "Trigger progressive learning for a group.",
        },
        {
            "method": "GET",
            "path": f"{BASE_PATH}/reviews",
            "capability": "review.list",
            "description": "List pending review queue items.",
        },
        {
            "method": "POST",
            "path": f"{BASE_PATH}/reviews/<review_id>/decision",
            "capability": "review.decide",
            "description": "Approve or reject a review queue item.",
        },
        {
            "method": "GET",
            "path": f"{BASE_PATH}/graphs/memory",
            "capability": "graph.memory",
            "description": "Read memory graph data in the dashboard ECharts payload shape.",
        },
        {
            "method": "GET",
            "path": f"{BASE_PATH}/graphs/knowledge",
            "capability": "graph.knowledge",
            "description": "Read knowledge graph data in the dashboard ECharts payload shape.",
        },
        {
            "method": "GET",
            "path": f"{BASE_PATH}/metrics",
            "capability": "metrics.read",
            "description": "Read hub-level intelligence, diversity, and affection metrics.",
        },
    ]

    def __init__(self, container: Any) -> None:
        self.container = container
        self.config = getattr(container, "plugin_config", None)
        self.database_manager = getattr(container, "database_manager", None)

    def manifest(self) -> Dict[str, Any]:
        """Describe stable endpoints and runtime feature availability."""
        config = self.config
        return {
            "name": "self-learning-hub",
            "version": self.API_VERSION,
            "base_path": self.BASE_PATH,
            "description": "Self Learning capability hub for companion AstrBot plugins.",
            "architecture": {
                "mvc": {
                    "controller": "webui.blueprints.hub",
                    "service": "webui.services.hub_service.HubService",
                    "domain_services": [
                        "RememberService",
                        "SocialContextInjector",
                        "JargonQueryService",
                        "V2LearningIntegration",
                        "ProgressiveLearningService",
                        "PersonaReviewService",
                        "GraphService",
                        "MetricsService",
                    ],
                },
                "aop": {
                    "aspects": [
                        "api_key_auth",
                        "stable_success_error_envelope",
                        "timing_log",
                        "safe_exception_mapping",
                    ],
                    "implementation": "webui.middleware.hub_aspects",
                },
            },
            "auth": {
                "api_key_enabled": bool(getattr(config, "enable_api_auth", False)),
                "schemes": ["Authorization: Bearer <api_key>", "X-Self-Learning-Key"],
            },
            "capabilities": self.capabilities(),
            "endpoints": self.endpoints(),
            "envelope": {
                "success": {"success": True, "message": "ok", "data": {}},
                "error": {
                    "success": False,
                    "message": "Unauthorized",
                    "error": {"code": "unauthorized", "message": "Unauthorized"},
                },
            },
            "examples": {
                "context": {
                    "group_id": "group_123",
                    "user_id": "user_456",
                    "query": "最近这句话该怎么接？",
                    "include": {"social": True, "jargon": True, "few_shots": True, "v2": True},
                    "top_k": 5,
                },
                "remember": {
                    "group_id": "group_123",
                    "sender_id": "user_456",
                    "content": "A: 这事怎么说？\nB: 可以这样接。",
                },
                "message_ingest": {
                    "group_id": "group_123",
                    "sender_id": "user_456",
                    "sender_name": "Alice",
                    "message": "今晚继续测试自学习。",
                    "platform": "companion_plugin",
                },
            },
        }

    @classmethod
    def endpoints(cls) -> list[Dict[str, str]]:
        """Return a copy of the public endpoint contract."""
        return [dict(item) for item in cls.ENDPOINTS]

    def capabilities(self) -> Dict[str, bool]:
        plugin = getattr(self.container, "plugin_instance", None)
        return {
            "database": bool(self.database_manager),
            "message_ingest": bool(getattr(self.container, "progressive_learning", None)),
            "remember": bool(getattr(plugin, "remember_service", None)),
            "social_context": bool(getattr(plugin, "social_context_injector", None)),
            "v2_context": bool(getattr(self.container, "v2_integration", None)),
            "jargon": bool(getattr(plugin, "jargon_query_service", None)),
            "graphs": True,
            "reviews": bool(self.database_manager or getattr(self.container, "persona_updater", None)),
            "metrics": True,
        }

    async def status(self) -> Dict[str, Any]:
        integration = IntegrationService(self.container).get_status()
        db_ready = bool(self.database_manager)
        if self.database_manager and hasattr(self.database_manager, "is_ready"):
            try:
                db_ready = bool(self.database_manager.is_ready())
            except Exception:
                db_ready = bool(self.database_manager)
        return {
            "healthy": db_ready and not bool(getattr(self.container, "database_degraded", False)),
            "database": {
                "ready": db_ready,
                "degraded": bool(getattr(self.container, "database_degraded", False)),
                "error": getattr(self.container, "database_start_error", None),
            },
            "capabilities": self.capabilities(),
            "integration": integration,
        }

    async def build_context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        group_id = self._required_text(payload, "group_id")
        user_id = self._text(payload.get("user_id") or payload.get("sender_id") or "unknown")
        query = self._text(payload.get("query") or payload.get("message") or "")
        include = payload.get("include") if isinstance(payload.get("include"), dict) else {}
        top_k = self._bounded_int(payload.get("top_k"), 1, 20, getattr(self.config, "rerank_top_k", 5))

        plugin = getattr(self.container, "plugin_instance", None)
        social_context = None
        social = getattr(plugin, "social_context_injector", None)
        if social and include.get("social", True):
            social_context = await social.format_complete_context(
                group_id=group_id,
                user_id=user_id,
                include_social_relations=bool(include.get("social_relations", getattr(self.config, "include_social_relations", True))),
                include_affection=bool(include.get("affection", getattr(self.config, "include_affection_info", True))),
                include_mood=bool(include.get("mood", getattr(self.config, "include_mood_info", True))),
                include_expression_patterns=bool(include.get("expression_patterns", getattr(self.config, "enable_expression_patterns", True))),
                include_psychological=bool(include.get("psychological", True)),
                include_behavior_guidance=bool(include.get("behavior_guidance", True)),
                include_conversation_goal=bool(include.get("conversation_goal", getattr(self.config, "enable_goal_driven_chat", False))),
                enable_protection=bool(include.get("protection", True)),
            )

        v2_context = None
        v2 = getattr(self.container, "v2_integration", None)
        if v2 and include.get("v2", True) and query:
            try:
                v2_context = await v2.get_enhanced_context(query, group_id, top_k=top_k)
            except TypeError:
                v2_context = await v2.get_enhanced_context(query, group_id)
            v2_context = self._serialize(v2_context)

        jargon_context = None
        jargon = getattr(plugin, "jargon_query_service", None)
        if jargon and include.get("jargon", True) and query:
            jargon_context = await jargon.check_and_explain_jargon(text=query, chat_id=group_id)

        few_shots = []
        if self.database_manager and include.get("few_shots", True):
            getter = getattr(self.database_manager, "get_approved_few_shots", None)
            if callable(getter):
                few_shots = await getter(group_id, limit=top_k)
                few_shots = [str(item) for item in (few_shots or [])]

        parts = []
        for label, value in (
            ("social", social_context),
            ("jargon", jargon_context),
            ("few_shots", "\n\n".join(few_shots) if few_shots else None),
        ):
            if value:
                parts.append({"type": label, "content": value})

        return {
            "group_id": group_id,
            "user_id": user_id,
            "query": query,
            "context_text": "\n\n".join(part["content"] for part in parts),
            "parts": parts,
            "v2": v2_context or {},
            "few_shots": few_shots,
        }

    async def remember(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        plugin = getattr(self.container, "plugin_instance", None)
        service = getattr(plugin, "remember_service", None)
        if not service:
            raise ValueError("remember service is not initialized")

        result = await service.remember(
            group_id=self._required_text(payload, "group_id"),
            sender_id=self._text(payload.get("sender_id") or payload.get("user_id") or "api"),
            content=self._required_text(payload, "content"),
        )
        return {
            "memory_id": result.memory_id,
            "expression_saved": result.expression_saved,
            "exemplar_id": result.exemplar_id,
            "style_review_id": result.style_review_id,
        }

    async def ingest_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        group_id = self._required_text(payload, "group_id")
        sender_id = self._required_text(payload, "sender_id")
        message = self._required_text(payload, "message")
        sender_name = self._text(payload.get("sender_name") or sender_id)
        timestamp = float(payload.get("timestamp") or time.time())

        message_data = {
            "sender_id": sender_id,
            "sender_name": sender_name,
            "message": message,
            "group_id": group_id,
            "timestamp": timestamp,
            "platform": self._text(payload.get("platform") or "hub_api"),
            "message_id": payload.get("message_id"),
            "reply_to": payload.get("reply_to"),
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        }

        collector = None
        plugin = getattr(self.container, "plugin_instance", None)
        if plugin:
            collector = getattr(plugin, "message_collector", None)
        if collector is None:
            factory_manager = getattr(self.container, "factory_manager", None)
            if factory_manager:
                service_factory = factory_manager.get_service_factory()
                if service_factory:
                    collector = service_factory.create_message_collector()

        collected = False
        if collector and hasattr(collector, "collect_message"):
            collected = bool(await collector.collect_message(message_data))
        elif self.database_manager and hasattr(self.database_manager, "save_raw_message"):
            try:
                from ...core.interfaces import MessageData
            except ImportError:
                from core.interfaces import MessageData

            collected = bool(
                await self.database_manager.save_raw_message(
                    MessageData(
                        sender_id=sender_id,
                        sender_name=sender_name,
                        message=message,
                        group_id=group_id,
                        timestamp=timestamp,
                        platform=message_data["platform"],
                        message_id=message_data.get("message_id"),
                        reply_to=message_data.get("reply_to"),
                    )
                )
            )

        v2_result = None
        if payload.get("process_v2", True):
            v2 = getattr(self.container, "v2_integration", None)
            if v2 and hasattr(v2, "process_message"):
                try:
                    from ...core.interfaces import MessageData
                except ImportError:
                    from core.interfaces import MessageData

                v2_message = MessageData(
                    sender_id=sender_id,
                    sender_name=sender_name,
                    message=message,
                    group_id=group_id,
                    timestamp=timestamp,
                    platform=message_data["platform"],
                    message_id=message_data.get("message_id"),
                    reply_to=message_data.get("reply_to"),
                )
                v2_result = await v2.process_message(v2_message, group_id)
                v2_result = self._serialize(v2_result)

        return {"collected": collected, "v2": v2_result or {}, "message": message_data}

    async def trigger_learning(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        group_id = self._required_text(payload, "group_id")
        wait = bool(payload.get("wait", False))
        progressive = getattr(self.container, "progressive_learning", None)
        if not progressive or not hasattr(progressive, "start_learning"):
            raise ValueError("progressive learning service is not initialized")

        if wait:
            result = await progressive.start_learning(group_id)
            return {"started": True, "completed": True, "group_id": group_id, "result": result}

        task = asyncio.create_task(progressive.start_learning(group_id))
        plugin = getattr(self.container, "plugin_instance", None)
        background_tasks = getattr(plugin, "background_tasks", None)
        if isinstance(background_tasks, set):
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
        return {"started": True, "completed": False, "group_id": group_id}

    async def reviews(self, *, limit: int = 50, offset: int = 0, status_filter: str = "pending") -> Dict[str, Any]:
        if status_filter != "pending":
            return {"updates": [], "total": 0, "status": status_filter}
        service = PersonaReviewService(self.container)
        return await service.get_pending_persona_updates(limit=limit, offset=offset)

    async def decide_review(self, review_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        decision = self._required_text(payload, "decision")
        comment = self._text(payload.get("comment") or "")
        modified_content = payload.get("modified_content")
        service = PersonaReviewService(self.container)
        success, message = await service.review_persona_update(
            review_id,
            decision,
            comment,
            modified_content,
        )
        return {"success": bool(success), "message": message, "review_id": review_id, "decision": decision}

    async def memory_graph(self, *, group_id: Optional[str] = None, limit: int = 120) -> Dict[str, Any]:
        return await GraphService(self.container).get_memory_graph(group_id=group_id, limit=limit)

    async def knowledge_graph(self, *, group_id: Optional[str] = None, limit: int = 120) -> Dict[str, Any]:
        return await GraphService(self.container).get_knowledge_graph(group_id=group_id, limit=limit)

    async def metrics(self, *, group_id: str = "default") -> Dict[str, Any]:
        service = MetricsService(self.container)
        intelligence, diversity, affection = await asyncio.gather(
            service.get_intelligence_metrics(group_id),
            service.get_diversity_metrics(group_id),
            service.get_affection_metrics(group_id),
        )
        return {
            "group_id": group_id,
            "intelligence": intelligence,
            "diversity": diversity,
            "affection": affection,
        }

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _required_text(cls, payload: Dict[str, Any], key: str) -> str:
        value = cls._text(payload.get(key))
        if not value:
            raise ValueError(f"{key} is required")
        return value

    @staticmethod
    def _bounded_int(value: Any, low: int, high: int, default: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(low, min(high, number))

    @classmethod
    def _serialize(cls, value: Any) -> Any:
        """Return JSON-friendly data for services that expose dataclasses/objects."""
        if is_dataclass(value):
            return cls._serialize(asdict(value))
        if isinstance(value, dict):
            return {str(key): cls._serialize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._serialize(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if hasattr(value, "to_dict") and callable(value.to_dict):
            try:
                return cls._serialize(value.to_dict())
            except Exception:
                pass
        return str(value)
