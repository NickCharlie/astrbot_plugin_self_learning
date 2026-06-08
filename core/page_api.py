"""AstrBot official Plugin Page API adapter.

The embedded dashboard runs inside AstrBot's Plugin Page iframe and can only
call plugin-relative bridge endpoints such as ``page/jargon``.  This module
keeps that bridge surface stable while reusing the existing WebUI service
container and services.  The standalone Quart WebUI remains available, but the
embedded page does not proxy or iframe it.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Mapping, Optional

from astrbot.api import logger

PLUGIN_NAME = "astrbot_plugin_self_learning"
PAGE_API_PREFIX = f"/{PLUGIN_NAME}/page"


class PluginPageApi:
    """Official AstrBot Plugin Page API for the self-learning dashboard."""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin

    def register_routes(self) -> None:
        """Register all routes consumed by ``pages/dashboard``."""
        register = self.plugin.context.register_web_api
        routes: list[tuple[str, Callable[..., Awaitable[Any]], list[str], str]] = [
            ("overview", self.get_overview, ["GET"], "Self Learning embedded overview"),
            ("dashboard", self.get_dashboard, ["GET"], "Self Learning embedded dashboard aggregate"),
            ("jargon", self.get_jargon, ["GET"], "Self Learning embedded jargon module"),
            ("jargon/action", self.post_jargon_action, ["POST"], "Self Learning embedded jargon actions"),
            ("style", self.get_style, ["GET"], "Self Learning embedded expression learning module"),
            ("style/action", self.post_style_action, ["POST"], "Self Learning embedded expression actions"),
            ("reviews", self.get_reviews, ["GET"], "Self Learning embedded review queues"),
            ("reviews/action", self.post_reviews_action, ["POST"], "Self Learning embedded review actions"),
            ("persona", self.get_persona, ["GET"], "Self Learning embedded persona module"),
            ("persona/action", self.post_persona_action, ["POST"], "Self Learning embedded persona actions"),
            ("content", self.get_content, ["GET"], "Self Learning embedded learning content module"),
            ("content/action", self.post_content_action, ["POST"], "Self Learning embedded content actions"),
            ("graphs", self.get_graphs, ["GET"], "Self Learning embedded graph module"),
            ("metrics", self.get_metrics, ["GET"], "Self Learning embedded metrics module"),
            ("monitoring", self.get_monitoring, ["GET"], "Self Learning embedded monitoring module"),
            ("integrations", self.get_integrations, ["GET"], "Self Learning embedded integrations module"),
            ("settings", self.get_settings, ["GET"], "Self Learning embedded settings module"),
            ("settings/action", self.post_settings_action, ["POST"], "Self Learning embedded settings actions"),
        ]
        for endpoint, handler, methods, description in routes:
            register(f"{PAGE_API_PREFIX}/{endpoint}", handler, methods, description)

    async def get_overview(self) -> dict[str, Any]:
        return self._ok(await self._load_overview())

    async def get_dashboard(self) -> dict[str, Any]:
        errors: dict[str, str] = {}
        overview = await self._safe_section(
            "overview", self._load_overview, errors, default={}
        )
        reviews = await self._safe_section(
            "reviews", lambda: self._load_reviews(limit=8), errors, default={}
        )
        content = await self._safe_section(
            "content", lambda: self._load_content(page=1, page_size=6), errors, default={}
        )
        metrics = await self._safe_section(
            "metrics", self._load_metrics, errors, default={}
        )
        monitoring = await self._safe_section(
            "monitoring", self._load_monitoring, errors, default={}
        )
        integrations = await self._safe_section(
            "integrations", self._load_integrations, errors, default={}
        )
        graphs = await self._safe_section(
            "graphs",
            lambda: self._load_graphs(graph_type="both", limit=60),
            errors,
            default={},
        )
        settings = await self._safe_section(
            "settings",
            lambda: self._load_settings(include_schema=False),
            errors,
            default={},
        )

        merged_errors = dict(overview.get("errors", {}) if isinstance(overview, dict) else {})
        merged_errors.update(errors)
        return self._ok(
            {
                "overview": overview,
                "reviews": reviews,
                "content": content,
                "metrics": metrics,
                "monitoring": monitoring,
                "integrations": integrations,
                "graphs": graphs,
                "settings": settings,
                "errors": merged_errors,
            }
        )

    async def get_jargon(self) -> dict[str, Any]:
        args = self._query()
        payload = await self._load_jargon(
            group_id=self._query_value(args, "group_id"),
            keyword=self._query_value(args, "keyword", ""),
            page=self._query_int(args, "page", 1),
            page_size=self._query_int(args, "page_size", self._query_int(args, "limit", 20)),
            confirmed=self._query_optional_bool(args, "confirmed"),
            pending=self._query_bool(args, "pending", False),
            filter_mode=self._query_value(args, "filter", ""),
        )
        return self._ok(payload)

    async def post_jargon_action(self) -> dict[str, Any]:
        body = await self._body()
        action = str(body.get("action", "")).strip()
        try:
            container = self._container()
            JargonService = self._imports().JargonService
            service = JargonService(container)

            if action in {"approve", "reject"}:
                success, message, item = await service.review_jargon(
                    self._body_int(body, "id"),
                    action,
                    meaning=body.get("meaning"),
                )
                return self._operation(success, message, item=item)
            if action == "update":
                success, message, item = await service.update_jargon(
                    self._body_int(body, "id"),
                    content=body.get("content"),
                    meaning=body.get("meaning"),
                )
                return self._operation(success, message, item=item)
            if action == "toggle_global":
                success, message, is_global = await service.toggle_jargon_global(
                    self._body_int(body, "id")
                )
                return self._operation(success, message, is_global=is_global)
            if action == "delete":
                success, message = await service.delete_jargon(self._body_int(body, "id"))
                return self._operation(success, message)
            if action == "sync_global":
                target_group_id = str(body.get("group_id") or "").strip()
                if not target_group_id:
                    return self._operation(False, "群组ID不能为空")
                success, message, count = await service.sync_global_to_group(target_group_id)
                return self._operation(success, message, synced_count=count)
            return self._operation(False, f"未知黑话操作: {action or '(empty)'}")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] jargon action failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

    async def get_style(self) -> dict[str, Any]:
        args = self._query()
        limit = self._query_int(args, "limit", 50)
        try:
            container = self._container()
            LearningService = self._imports().LearningService
            service = LearningService(container)
            results, reviews, patterns = await asyncio.gather(
                service.get_style_learning_results(),
                service.get_style_learning_reviews(limit=limit),
                service.get_style_learning_patterns(),
            )
            return self._ok(
                {
                    "results": results,
                    "reviews": reviews,
                    "patterns": patterns,
                }
            )
        except Exception as exc:
            logger.error(f"[PluginPageAPI] style module failed: {exc}", exc_info=True)
            return self._ok(
                {
                    "results": {"statistics": {}, "style_progress": []},
                    "reviews": {"reviews": [], "total": 0},
                    "patterns": {
                        "emotion_patterns": [],
                        "language_patterns": [],
                        "topic_patterns": [],
                    },
                    "error": str(exc),
                }
            )

    async def post_style_action(self) -> dict[str, Any]:
        body = await self._body()
        action = str(body.get("action", "")).strip()
        try:
            LearningService = self._imports().LearningService
            service = LearningService(self._container())

            if action == "approve":
                success, message = await service.approve_style_learning_review(
                    self._body_int(body, "id")
                )
                return self._operation(success, message)
            if action == "reject":
                success, message = await service.reject_style_learning_review(
                    self._body_int(body, "id")
                )
                return self._operation(success, message)
            return self._operation(False, f"未知表达学习操作: {action or '(empty)'}")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] style action failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

    async def get_reviews(self) -> dict[str, Any]:
        args = self._query()
        return self._ok(
            await self._load_reviews(
                limit=self._query_int(args, "limit", 50),
                offset=self._query_int(args, "offset", 0),
                status_filter=self._query_value(args, "status"),
            )
        )

    async def post_reviews_action(self) -> dict[str, Any]:
        body = await self._body()
        action = str(body.get("action", "")).strip()
        try:
            imports = self._imports()
            container = self._container()
            review_service = imports.PersonaReviewService(container)

            if action == "review":
                success, message = await review_service.review_persona_update(
                    str(body.get("id") or ""),
                    str(body.get("decision") or body.get("review_action") or "approve"),
                    str(body.get("comment") or ""),
                    body.get("modified_content"),
                )
                return self._operation(success, message)
            if action == "revert":
                success, message = await review_service.revert_persona_update(
                    str(body.get("id") or ""),
                    str(body.get("reason") or "撤回审查决定"),
                )
                return self._operation(success, message)
            if action == "delete":
                success, message = await review_service.delete_persona_update(
                    str(body.get("id") or "")
                )
                return self._operation(success, message)
            if action == "batch_review":
                result = await review_service.batch_review_persona_updates(
                    self._body_list(body, "ids", fallback_key="update_ids"),
                    str(body.get("decision") or body.get("review_action") or "approve"),
                    str(body.get("comment") or ""),
                )
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量审查完成",
                    result=result,
                )
            if action == "batch_delete":
                result = await review_service.batch_delete_persona_updates(
                    self._body_list(body, "ids", fallback_key="update_ids")
                )
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量删除完成",
                    result=result,
                )
            if action.startswith("style_"):
                learning_service = imports.LearningService(container)
                review_id = self._body_int(body, "id")
                if action == "style_approve":
                    success, message = await learning_service.approve_style_learning_review(review_id)
                elif action == "style_reject":
                    success, message = await learning_service.reject_style_learning_review(review_id)
                else:
                    return self._operation(False, f"未知风格审查操作: {action}")
                return self._operation(success, message)
            if action.startswith("jargon_"):
                jargon_service = imports.JargonService(container)
                jargon_id = self._body_int(body, "id")
                if action == "jargon_approve":
                    success, message, item = await jargon_service.review_jargon(
                        jargon_id, "approve", meaning=body.get("meaning")
                    )
                    return self._operation(success, message, item=item)
                if action == "jargon_reject":
                    success, message, item = await jargon_service.review_jargon(
                        jargon_id, "reject", meaning=body.get("meaning")
                    )
                    return self._operation(success, message, item=item)
                if action == "jargon_delete":
                    success, message = await jargon_service.delete_jargon(jargon_id)
                    return self._operation(success, message)
            return self._operation(False, f"未知审查操作: {action or '(empty)'}")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] review action failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

    async def get_persona(self) -> dict[str, Any]:
        args = self._query()
        group_id = self._query_value(args, "group_id", "default") or "default"
        limit = self._query_int(args, "limit", 20)
        return self._ok(await self._load_persona(group_id=group_id, limit=limit))

    async def post_persona_action(self) -> dict[str, Any]:
        body = await self._body()
        action = str(body.get("action", "")).strip()
        try:
            imports = self._imports()
            container = self._container()
            persona_service = imports.PersonaService(container)
            backup_service = imports.PersonaBackupService(container)

            if action == "create":
                success, message, persona_id = await persona_service.create_persona(
                    dict(body.get("persona") or body.get("data") or {})
                )
                return self._operation(success, message, persona_id=persona_id)
            if action == "update":
                success, message = await persona_service.update_persona(
                    str(body.get("persona_id") or ""),
                    dict(body.get("persona") or body.get("data") or {}),
                )
                return self._operation(success, message)
            if action == "delete":
                success, message = await persona_service.delete_persona(
                    str(body.get("persona_id") or "")
                )
                return self._operation(success, message)
            if action == "import":
                success, message, persona_id = await persona_service.import_persona(
                    dict(body.get("persona") or body.get("data") or {})
                )
                return self._operation(success, message, persona_id=persona_id)
            if action == "export":
                data = await persona_service.export_persona(str(body.get("persona_id") or ""))
                return self._operation(True, "人格导出成功", persona=data)
            if action == "backup_detail":
                data = await backup_service.get_backup(
                    self._body_int(body, "id"),
                    group_id=body.get("group_id"),
                )
                return self._operation(True, "人格备份详情已读取", backup=data)
            if action == "backup_restore":
                success, message = await backup_service.restore_backup(
                    self._body_int(body, "id"),
                    group_id=body.get("group_id"),
                )
                return self._operation(success, message)
            if action == "backup_delete":
                success, message = await backup_service.delete_backup(
                    self._body_int(body, "id"),
                    group_id=body.get("group_id"),
                )
                return self._operation(success, message)
            return self._operation(False, f"未知人格操作: {action or '(empty)'}")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] persona action failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

    async def get_content(self) -> dict[str, Any]:
        args = self._query()
        return self._ok(
            await self._load_content(
                page=self._query_int(args, "page", 1),
                page_size=self._query_int(args, "page_size", 20),
            )
        )

    async def post_content_action(self) -> dict[str, Any]:
        body = await self._body()
        action = str(body.get("action", "")).strip()
        try:
            if action == "delete_content":
                success, message = await self._delete_content_item(
                    str(body.get("bucket") or ""),
                    self._body_int(body, "id"),
                )
                return self._operation(success, message)
            if action == "delete_batch":
                success, message = await self._delete_learning_batch(
                    self._body_int(body, "id")
                )
                return self._operation(success, message)
            if action == "relearn":
                result = await self._relearn(str(body.get("group_id") or "default"))
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "重新学习已提交",
                    result=result,
                )
            return self._operation(False, f"未知学习内容操作: {action or '(empty)'}")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] content action failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

    async def get_graphs(self) -> dict[str, Any]:
        args = self._query()
        return self._ok(
            await self._load_graphs(
                graph_type=self._query_value(args, "type", "memory") or "memory",
                group_id=self._query_value(args, "group_id"),
                limit=self._query_int(args, "limit", 120),
            )
        )

    async def get_metrics(self) -> dict[str, Any]:
        return self._ok(await self._load_metrics())

    async def get_monitoring(self) -> dict[str, Any]:
        return self._ok(await self._load_monitoring())

    async def get_integrations(self) -> dict[str, Any]:
        return self._ok(await self._load_integrations())

    async def get_settings(self) -> dict[str, Any]:
        args = self._query()
        include_schema = self._query_bool(args, "schema", True)
        return self._ok(await self._load_settings(include_schema=include_schema))

    async def post_settings_action(self) -> dict[str, Any]:
        body = await self._body()
        action = str(body.get("action", "")).strip()
        try:
            if action in {"save", "update_config"}:
                ConfigService = self._imports().ConfigService
                service = ConfigService(self._container())
                success, message, config = await service.update_config(
                    dict(body.get("config") or body.get("settings") or body.get("data") or {})
                )
                return self._operation(success, message, config=config)
            if action == "install_dependencies":
                result = await self._install_dependencies(body)
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "依赖安装完成",
                    result=result,
                )
            return self._operation(False, f"未知设置操作: {action or '(empty)'}")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] settings action failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

    async def _load_overview(self) -> dict[str, Any]:
        imports = self._imports()
        container = self._container()
        errors: dict[str, str] = {}

        plugin_config = getattr(self.plugin, "plugin_config", None)
        webui_config = getattr(container, "webui_config", None)
        db_manager = getattr(container, "database_manager", None) or getattr(
            self.plugin, "db_manager", None
        )

        learning_stats = self._serialize_learning_stats(
            getattr(self.plugin, "learning_stats", None)
        )
        jargon_stats = await self._safe_section(
            "jargon",
            lambda: imports.JargonService(container).get_jargon_stats(),
            errors,
            default=self._empty_jargon_stats(),
        )
        style_results = await self._safe_section(
            "style",
            lambda: imports.LearningService(container).get_style_learning_results(),
            errors,
            default={"statistics": {}, "style_progress": []},
        )
        persona_state = await self._safe_section(
            "persona",
            lambda: imports.PersonaService(container).get_current_persona_state("default"),
            errors,
            default=self._empty_persona_state(),
        )
        backups = await self._safe_section(
            "persona_backups",
            lambda: imports.PersonaBackupService(container).list_backups(limit=8),
            errors,
            default={"backups": [], "total": 0, "available": False},
        )
        metrics = await self._safe_section(
            "metrics",
            lambda: imports.MetricsService(container).get_intelligence_metrics("default"),
            errors,
            default={"overall_score": 0, "dimensions": {}, "trends": []},
        )

        style_stats = style_results.get("statistics") if isinstance(style_results, dict) else {}
        style_stats = style_stats if isinstance(style_stats, dict) else {}

        modules = self._build_modules(
            plugin_config=plugin_config,
            jargon_stats=jargon_stats,
            style_stats=style_stats,
            persona_state=persona_state,
            backups=backups,
            metrics=metrics,
        )

        return {
            "plugin": {
                "name": PLUGIN_NAME,
                "display_name": "Self Learning",
                "version": self._metadata_version(),
                "generated_at": datetime.now().isoformat(),
            },
            "runtime": {
                "database_ready": bool(db_manager),
                "database_degraded": bool(getattr(container, "database_degraded", False)),
                "database_error": getattr(container, "database_start_error", None),
                "services": {
                    "plugin_config": bool(plugin_config),
                    "webui_config": bool(webui_config),
                    "database_manager": bool(db_manager),
                    "persona_manager": bool(getattr(container, "persona_manager", None)),
                    "persona_web_manager": bool(getattr(container, "persona_web_manager", None)),
                    "intelligence_metrics": bool(
                        getattr(container, "intelligence_metrics_service", None)
                    ),
                    "progressive_learning": bool(
                        getattr(container, "progressive_learning", None)
                    ),
                },
            },
            "webui": self._build_webui_snapshot(plugin_config, webui_config),
            "learning_stats": learning_stats,
            "jargon": jargon_stats,
            "style": style_results,
            "persona": persona_state,
            "persona_backups": backups,
            "metrics": metrics,
            "modules": modules,
            "quick_links": self._build_quick_links(plugin_config, webui_config),
            "errors": errors,
        }

    async def _load_jargon(
        self,
        *,
        group_id: Optional[str],
        keyword: str,
        page: int,
        page_size: int,
        confirmed: Optional[bool],
        pending: bool,
        filter_mode: str,
    ) -> dict[str, Any]:
        imports = self._imports()
        service = imports.JargonService(self._container())
        errors: dict[str, str] = {}
        global_only = filter_mode == "global"
        local_only = filter_mode == "local"

        stats = await self._safe_section(
            "stats",
            lambda: service.get_jargon_stats(group_id=group_id),
            errors,
            default=self._empty_jargon_stats(),
        )
        groups = await self._safe_section(
            "groups",
            service.get_jargon_groups,
            errors,
            default=[],
        )
        if keyword:
            items = await self._safe_section(
                "list",
                lambda: service.search_jargon(
                    keyword,
                    chat_id=group_id,
                    confirmed_only=confirmed is True,
                    unconfirmed_only=confirmed is False,
                    pending_only=pending,
                    global_only=global_only,
                    local_only=local_only,
                ),
                errors,
                default=[],
            )
            listing = {
                "jargon_list": items,
                "total": len(items) if isinstance(items, list) else 0,
                "page": 1,
                "page_size": len(items) if isinstance(items, list) else 0,
                "total_pages": 1,
            }
        else:
            listing = await self._safe_section(
                "list",
                lambda: service.get_jargon_list(
                    group_id=group_id,
                    confirmed=confirmed,
                    page=max(1, page),
                    page_size=max(1, min(page_size or 20, 100)),
                    pending_only=pending,
                    global_only=global_only,
                    local_only=local_only,
                ),
                errors,
                default={
                    "jargon_list": [],
                    "total": 0,
                    "page": max(1, page),
                    "page_size": max(1, min(page_size or 20, 100)),
                    "total_pages": 1,
                },
            )

        return {
            "stats": stats,
            "groups": groups,
            "list": listing,
            "filters": {
                "group_id": group_id,
                "keyword": keyword,
                "confirmed": confirmed,
                "pending": pending,
                "filter": filter_mode,
            },
            "errors": errors,
        }

    async def _load_reviews(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None,
    ) -> dict[str, Any]:
        imports = self._imports()
        container = self._container()
        errors: dict[str, str] = {}
        review_service = imports.PersonaReviewService(container)
        learning_service = imports.LearningService(container)
        jargon_service = imports.JargonService(container)
        bounded_limit = max(1, min(limit or 50, 100))

        pending, reviewed, style_reviews, pending_jargon = await asyncio.gather(
            self._safe_section(
                "persona_pending",
                lambda: review_service.get_pending_persona_updates(
                    limit=bounded_limit,
                    offset=max(0, offset),
                ),
                errors,
                default={"updates": [], "total": 0, "success": True},
            ),
            self._safe_section(
                "persona_reviewed",
                lambda: review_service.get_reviewed_persona_updates(
                    bounded_limit,
                    max(0, offset),
                    status_filter,
                ),
                errors,
                default={"updates": [], "total": 0, "success": True},
            ),
            self._safe_section(
                "style_reviews",
                lambda: learning_service.get_style_learning_reviews(limit=bounded_limit),
                errors,
                default={"reviews": [], "total": 0},
            ),
            self._safe_section(
                "jargon_pending",
                lambda: jargon_service.get_jargon_list(
                    page=1,
                    page_size=min(bounded_limit, 50),
                    confirmed=False,
                    pending_only=True,
                ),
                errors,
                default={"jargon_list": [], "total": 0},
            ),
        )

        return {
            "persona_pending": pending,
            "persona_reviewed": reviewed,
            "style_reviews": style_reviews,
            "jargon_pending": pending_jargon,
            "errors": errors,
        }

    async def _load_persona(self, *, group_id: str, limit: int) -> dict[str, Any]:
        imports = self._imports()
        container = self._container()
        errors: dict[str, str] = {}
        persona_service = imports.PersonaService(container)
        backup_service = imports.PersonaBackupService(container)

        personas, current, default_persona, backups = await asyncio.gather(
            self._safe_section("list", persona_service.get_all_personas, errors, default=[]),
            self._safe_section(
                "current",
                lambda: persona_service.get_current_persona_state(group_id),
                errors,
                default=self._empty_persona_state(group_id),
            ),
            self._safe_section(
                "default",
                lambda: persona_service.get_default_persona(group_id),
                errors,
                default={"persona_id": "default", "system_prompt": "", "begin_dialogs": []},
            ),
            self._safe_section(
                "backups",
                lambda: backup_service.list_backups(group_id=group_id, limit=limit),
                errors,
                default={"backups": [], "total": 0, "available": False},
            ),
        )
        return {
            "group_id": group_id,
            "personas": personas,
            "current": current,
            "default": default_persona,
            "backups": backups,
            "errors": errors,
        }

    async def _load_content(self, *, page: int, page_size: int) -> dict[str, Any]:
        errors: dict[str, str] = {}
        content, batches = await asyncio.gather(
            self._safe_section(
                "content",
                self._get_learning_content_text,
                errors,
                default={"dialogues": [], "analysis": [], "features": [], "history": []},
            ),
            self._safe_section(
                "batches",
                lambda: self._get_learning_batches(page=page, page_size=page_size),
                errors,
                default={"batches": [], "total": 0, "page": page, "page_size": page_size},
            ),
        )
        return {"content": content, "batches": batches, "errors": errors}

    async def _load_graphs(
        self,
        *,
        graph_type: str,
        group_id: Optional[str] = None,
        limit: int = 120,
    ) -> dict[str, Any]:
        service = self._imports().GraphService(self._container())
        bounded_limit = max(10, min(limit or 120, 300))
        if graph_type == "both":
            memory, knowledge = await asyncio.gather(
                service.get_memory_graph(group_id=group_id, limit=bounded_limit),
                service.get_knowledge_graph(group_id=group_id, limit=bounded_limit),
            )
            return {"memory": memory, "knowledge": knowledge}
        if graph_type == "knowledge":
            return {"knowledge": await service.get_knowledge_graph(group_id=group_id, limit=bounded_limit)}
        return {"memory": await service.get_memory_graph(group_id=group_id, limit=bounded_limit)}

    async def _load_metrics(self) -> dict[str, Any]:
        imports = self._imports()
        container = self._container()
        db = getattr(container, "database_manager", None)
        metrics_service = imports.MetricsService(container)
        errors: dict[str, str] = {}

        intelligence, diversity, affection = await asyncio.gather(
            self._safe_section(
                "intelligence",
                lambda: metrics_service.get_intelligence_metrics("default"),
                errors,
                default={"overall_score": 0, "dimensions": {}, "trends": []},
            ),
            self._safe_section(
                "diversity",
                lambda: metrics_service.get_diversity_metrics("default"),
                errors,
                default={
                    "vocabulary_diversity": 0,
                    "topic_diversity": 0,
                    "style_diversity": 0,
                    "total_score": 0,
                },
            ),
            self._safe_section(
                "affection",
                lambda: metrics_service.get_affection_metrics("default"),
                errors,
                default={
                    "average_affection": 0,
                    "total_users": 0,
                    "high_affection_count": 0,
                    "low_affection_count": 0,
                    "distribution": [],
                },
            ),
        )

        message_stats = await self._safe_section(
            "messages",
            lambda: db.get_messages_statistics() if db else self._async_value({}),
            errors,
            default={},
        )
        trends = await self._safe_section(
            "trends",
            lambda: db.get_trends_data() if db and hasattr(db, "get_trends_data") else self._async_value({}),
            errors,
            default={},
        )

        llm_adapter = getattr(container, "llm_adapter", None)
        llm_stats = {}
        provider_info = {}
        if llm_adapter and hasattr(llm_adapter, "get_call_statistics"):
            try:
                llm_stats = llm_adapter.get_call_statistics() or {}
            except Exception as exc:
                errors["llm_stats"] = str(exc)
        if llm_adapter and hasattr(llm_adapter, "get_provider_info"):
            try:
                provider_info = llm_adapter.get_provider_info() or {}
            except Exception as exc:
                errors["provider_info"] = str(exc)

        return {
            "intelligence": intelligence,
            "diversity": diversity,
            "affection": affection,
            "messages": message_stats,
            "trends": trends,
            "llm": {
                "call_statistics": llm_stats,
                "provider_info": provider_info,
            },
            "learning": {
                "active_sessions": self._active_learning_sessions(container),
                "learning_stats": self._serialize_learning_stats(
                    getattr(self.plugin, "learning_stats", None)
                ),
            },
            "system": self._system_metrics(),
            "errors": errors,
        }

    async def _load_monitoring(self) -> dict[str, Any]:
        container = self._container()
        errors: dict[str, str] = {}
        health = await self._safe_section(
            "health",
            lambda: self._async_value(self._health_summary(container)),
            errors,
            default={"overall": "unknown", "checks": {}},
        )
        functions = await self._safe_section(
            "functions",
            lambda: self._async_value(self._function_metrics()),
            errors,
            default={"debug_mode": False, "functions": [], "timestamp": time.time()},
        )
        return {
            "health": health,
            "functions": functions,
            "runtime": {
                "database_degraded": bool(getattr(container, "database_degraded", False)),
                "database_start_error": getattr(container, "database_start_error", None),
                "perf_collector": bool(getattr(container, "perf_collector", None)),
                "metric_collector": bool(getattr(container, "metric_collector", None)),
                "health_checker": bool(getattr(container, "health_checker", None)),
            },
            "errors": errors,
        }

    async def _load_integrations(self) -> dict[str, Any]:
        service = self._imports().IntegrationService(self._container())
        status = service.get_status()
        return {
            **status,
            "embed_targets": {
                "livingmemory": service.get_embed_target("livingmemory"),
                "group_chat_plus": service.get_embed_target("group_chat_plus"),
            },
        }

    async def _load_settings(self, *, include_schema: bool) -> dict[str, Any]:
        imports = self._imports()
        service = imports.ConfigService(self._container())
        config = await service.get_config()
        payload: dict[str, Any] = {
            "config": config,
            "dependency_tiers": imports.DEPENDENCY_TIERS,
            "pip_mirrors": imports.PIP_MIRROR_SOURCES,
            "manual_dependency_source": imports.MANUAL_DEPENDENCY_INSTALL_SOURCE,
        }
        if include_schema:
            payload["schema"] = await service.get_config_schema()
        else:
            payload["schema_summary"] = {
                "groups": len((await service.get_config_schema()).get("groups", []))
            }
        return payload

    async def _get_learning_content_text(self) -> dict[str, list[dict[str, Any]]]:
        container = self._container()
        database_manager = getattr(container, "database_manager", None)
        content_data: dict[str, list[dict[str, Any]]] = {
            "dialogues": [],
            "analysis": [],
            "features": [],
            "history": [],
        }
        if not database_manager or not hasattr(database_manager, "get_session"):
            return content_data

        try:
            from sqlalchemy import desc, select

            try:
                from ..models.orm import (
                    ExpressionPattern,
                    LearningBatch,
                    RawMessage,
                    StyleLearningReview,
                )
            except ImportError:
                from models.orm import (
                    ExpressionPattern,
                    LearningBatch,
                    RawMessage,
                    StyleLearningReview,
                )

            async with database_manager.get_session() as session:
                raw_messages = (
                    await session.execute(
                        select(RawMessage).order_by(desc(RawMessage.timestamp)).limit(24)
                    )
                ).scalars().all()
                style_reviews = (
                    await session.execute(
                        select(StyleLearningReview)
                        .order_by(desc(StyleLearningReview.timestamp))
                        .limit(24)
                    )
                ).scalars().all()
                expression_patterns = (
                    await session.execute(
                        select(ExpressionPattern)
                        .order_by(desc(ExpressionPattern.last_active_time))
                        .limit(24)
                    )
                ).scalars().all()
                batches = (
                    await session.execute(
                        select(LearningBatch).order_by(desc(LearningBatch.start_time)).limit(24)
                    )
                ).scalars().all()

            for msg in raw_messages:
                message_text = getattr(msg, "message", "") or ""
                if len(message_text.strip()) < 2:
                    continue
                sender = getattr(msg, "sender_name", None) or getattr(msg, "sender_id", None) or "未知发送者"
                content_data["dialogues"].append(
                    {
                        "id": getattr(msg, "id", None),
                        "type": "dialogue",
                        "title": sender,
                        "timestamp": self._format_ts(getattr(msg, "timestamp", None)),
                        "text": f"{sender}: {message_text}",
                        "detail": message_text,
                        "metadata": f"群组: {getattr(msg, 'group_id', '')}, 平台: {getattr(msg, 'platform', '') or '未知'}",
                        "raw": {
                            "sender_id": getattr(msg, "sender_id", None),
                            "sender_name": getattr(msg, "sender_name", None),
                            "group_id": getattr(msg, "group_id", None),
                            "platform": getattr(msg, "platform", None),
                            "processed": bool(getattr(msg, "processed", False)),
                        },
                    }
                )

            for review in style_reviews:
                patterns = self._parse_jsonish(getattr(review, "learned_patterns", None), [])
                description = getattr(review, "description", "") or ""
                few_shots = getattr(review, "few_shots_content", "") or ""
                content_data["analysis"].append(
                    {
                        "id": getattr(review, "id", None),
                        "type": getattr(review, "type", None) or "style_learning",
                        "title": description or f"风格学习 ({getattr(review, 'type', '') or 'style'})",
                        "timestamp": self._format_ts(getattr(review, "timestamp", None)),
                        "text": description or few_shots,
                        "detail": few_shots or description,
                        "status": getattr(review, "status", None),
                        "patterns": patterns,
                        "metadata": f"群组: {getattr(review, 'group_id', '')}, 状态: {getattr(review, 'status', '')}",
                    }
                )

            for pattern in expression_patterns:
                weight = getattr(pattern, "weight", None) or 0
                situation = getattr(pattern, "situation", "") or "表达模式"
                expression = getattr(pattern, "expression", "") or ""
                content_data["features"].append(
                    {
                        "id": getattr(pattern, "id", None),
                        "type": "expression_pattern",
                        "title": situation,
                        "timestamp": self._format_ts(getattr(pattern, "last_active_time", None)),
                        "text": f"场景: {situation}\n表达: {expression}",
                        "detail": expression,
                        "metadata": f"群组: {getattr(pattern, 'group_id', '')}, 权重: {float(weight):.2f}",
                    }
                )

            max_batch_size = self._config_value(
                getattr(container, "plugin_config", None),
                "max_messages_per_batch",
                200,
            )
            for batch in batches:
                quality_score = self._effective_batch_quality(batch, max_batch_size)
                content_data["history"].append(
                    {
                        "id": getattr(batch, "id", None),
                        "type": "learning_batch",
                        "title": getattr(batch, "batch_name", None)
                        or getattr(batch, "batch_id", None)
                        or "学习批次",
                        "timestamp": self._format_ts(getattr(batch, "start_time", None)),
                        "text": f"质量: {quality_score:.3f}",
                        "detail": getattr(batch, "error_message", None)
                        or f"状态: {getattr(batch, 'status', None) or 'unknown'}",
                        "status": getattr(batch, "status", None),
                        "metadata": (
                            f"群组: {getattr(batch, 'group_id', '')}, "
                            f"消息: {getattr(batch, 'processed_messages', 0) or 0}, "
                            f"成功: {'是' if getattr(batch, 'success', False) else '否'}"
                        ),
                    }
                )
        except Exception as exc:
            logger.warning(f"[PluginPageAPI] learning content unavailable: {exc}", exc_info=True)
        return content_data

    async def _get_learning_batches(self, *, page: int, page_size: int) -> dict[str, Any]:
        database_manager = getattr(self._container(), "database_manager", None)
        page = max(1, page)
        page_size = max(1, min(page_size or 20, 100))
        if not database_manager or not hasattr(database_manager, "get_session"):
            return {"batches": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 1}

        try:
            from sqlalchemy import desc, func, select

            try:
                from ..models.orm import LearningBatch
            except ImportError:
                from models.orm import LearningBatch

            async with database_manager.get_session() as session:
                total = (await session.execute(select(func.count()).select_from(LearningBatch))).scalar() or 0
                rows = (
                    await session.execute(
                        select(LearningBatch)
                        .order_by(desc(LearningBatch.start_time))
                        .offset((page - 1) * page_size)
                        .limit(page_size)
                    )
                ).scalars().all()
            max_batch_size = self._config_value(
                getattr(self._container(), "plugin_config", None),
                "max_messages_per_batch",
                200,
            )
            batches = [
                {
                    "id": getattr(batch, "id", None),
                    "batch_id": getattr(batch, "batch_id", None),
                    "batch_name": getattr(batch, "batch_name", None),
                    "group_id": getattr(batch, "group_id", None),
                    "start_time": getattr(batch, "start_time", None),
                    "end_time": getattr(batch, "end_time", None),
                    "quality_score": self._effective_batch_quality(batch, max_batch_size),
                    "raw_quality_score": getattr(batch, "quality_score", None),
                    "processed_messages": getattr(batch, "processed_messages", 0),
                    "message_count": getattr(batch, "message_count", 0),
                    "filtered_count": getattr(batch, "filtered_count", 0),
                    "success": bool(getattr(batch, "success", False)),
                    "status": getattr(batch, "status", None),
                    "error_message": getattr(batch, "error_message", None),
                }
                for batch in rows
            ]
            return {
                "batches": batches,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": max(1, (total + page_size - 1) // page_size),
            }
        except Exception as exc:
            logger.warning(f"[PluginPageAPI] learning batches unavailable: {exc}", exc_info=True)
            return {"batches": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 1}

    async def _delete_content_item(self, bucket: str, item_id: int) -> tuple[bool, str]:
        database_manager = getattr(self._container(), "database_manager", None)
        if not database_manager or not hasattr(database_manager, "get_session"):
            return False, "数据库管理器未初始化"

        bucket = bucket.strip()
        try:
            from sqlalchemy import delete as sql_delete

            try:
                from ..models.orm import (
                    ExpressionPattern,
                    LearningBatch,
                    RawMessage,
                    StyleLearningReview,
                )
            except ImportError:
                from models.orm import (
                    ExpressionPattern,
                    LearningBatch,
                    RawMessage,
                    StyleLearningReview,
                )

            bucket_models = {
                "dialogues": (RawMessage, "原始对话"),
                "analysis": (StyleLearningReview, "分析结果"),
                "features": (ExpressionPattern, "表达模式"),
                "history": (LearningBatch, "学习批次"),
            }
            model_info = bucket_models.get(bucket)
            if not model_info:
                return False, f"不支持的学习内容类型: {bucket}"

            model, label = model_info
            async with database_manager.get_session() as session:
                result = await session.execute(sql_delete(model).where(model.id == item_id))
                await session.commit()
            if result.rowcount > 0:
                return True, f"{label} {item_id} 已删除"
            return False, f"{label} {item_id} 不存在"
        except Exception as exc:
            logger.error(f"[PluginPageAPI] delete content failed: {exc}", exc_info=True)
            return False, str(exc)

    async def _delete_learning_batch(self, batch_id: int) -> tuple[bool, str]:
        return await self._delete_content_item("history", batch_id)

    async def _relearn(self, group_id: str) -> dict[str, Any]:
        container = self._container()
        database_manager = getattr(container, "database_manager", None)
        group_id = (group_id or "default").strip()
        if not group_id or group_id == "default":
            detected = await self._detect_group_with_most_messages(database_manager)
            if detected:
                group_id = detected

        if not group_id:
            return {"success": False, "error": "没有可用的群组数据"}

        total_messages = 0
        if database_manager:
            try:
                stats = await database_manager.get_messages_statistics()
                if isinstance(stats, dict):
                    total_messages = int(stats.get("total_messages", 0) or 0)
            except Exception:
                pass

        progressive_learning = getattr(container, "progressive_learning", None)
        if not progressive_learning:
            return {"success": False, "error": "学习服务未初始化"}

        asyncio.create_task(progressive_learning.start_learning(group_id))
        return {
            "success": True,
            "message": f"重新学习已启动，群组: {group_id}",
            "group_id": group_id,
            "total_messages": total_messages,
        }

    async def _detect_group_with_most_messages(self, database_manager: Any) -> Optional[str]:
        if not database_manager or not hasattr(database_manager, "get_session"):
            return None
        try:
            from sqlalchemy import and_, func, select

            try:
                from ..models.orm import RawMessage
            except ImportError:
                from models.orm import RawMessage

            async with database_manager.get_session() as session:
                result = await session.execute(
                    select(RawMessage.group_id, func.count().label("message_count"))
                    .where(and_(RawMessage.group_id.isnot(None), RawMessage.group_id != ""))
                    .group_by(RawMessage.group_id)
                    .order_by(func.count().desc())
                )
                row = result.first()
                return str(row[0]) if row else None
        except Exception as exc:
            logger.warning(f"[PluginPageAPI] auto detect group failed: {exc}")
            return None

    async def _install_dependencies(self, body: Mapping[str, Any]) -> dict[str, Any]:
        imports = self._imports()
        manual_confirmed = body.get("manual_confirmed") is True or (
            body.get("manual_confirm") is True and body.get("user_confirmed") is True
        )
        if not manual_confirmed:
            return {"success": False, "error": "依赖安装只能在设置界面手动确认后触发"}
        source = body.get("source")
        if source != imports.MANUAL_DEPENDENCY_INSTALL_SOURCE and body.get("mode") != "plugin_page":
            return {"success": False, "error": "缺少合法的依赖安装来源"}

        tier = str(body.get("tier") or "full").strip().lower()
        tier_definition = imports.DEPENDENCY_TIERS.get(tier)
        if not tier_definition:
            return {"success": False, "error": "未知依赖安装档位"}

        mirror_key = str(body.get("pip_mirror") or "default").strip().lower()
        mirror_definition = imports.PIP_MIRROR_SOURCES.get(mirror_key)
        if not mirror_definition:
            return {"success": False, "error": "未知 pip 镜像源"}

        pip_index_args: list[str] = []
        if mirror_definition["index_url"]:
            pip_index_args = ["--index-url", mirror_definition["index_url"]]

        packages = list(tier_definition["packages"])
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            *pip_index_args,
            *packages,
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=os.path.dirname(os.path.dirname(__file__)),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        combined = (
            stdout.decode("utf-8", errors="replace")
            + "\n"
            + stderr.decode("utf-8", errors="replace")
        ).strip()
        return {
            "success": process.returncode == 0,
            "message": (
                f"{tier_definition['label']}安装完成"
                if process.returncode == 0
                else f"{tier_definition['label']}安装失败，退出码: {process.returncode}"
            ),
            "tier": tier,
            "tier_label": tier_definition["label"],
            "pip_mirror": mirror_key,
            "pip_mirror_label": mirror_definition["label"],
            "pip_index_url": mirror_definition["index_url"],
            "packages": packages,
            "output": combined[-8000:],
        }

    def _health_summary(self, container: Any) -> dict[str, Any]:
        checker = getattr(container, "health_checker", None)
        if checker is not None and hasattr(checker, "get_summary"):
            return checker.get_summary()
        try:
            try:
                from ..services.monitoring.health_checker import HealthChecker
            except ImportError:
                from services.monitoring.health_checker import HealthChecker
            try:
                from ..utils.cache_manager import get_cache_manager
            except ImportError:
                from utils.cache_manager import get_cache_manager

            registry = None
            try:
                if getattr(container, "factory_manager", None):
                    registry = (
                        container.factory_manager.get_service_factory().get_service_registry()
                    )
            except Exception:
                registry = None
            return HealthChecker(
                service_registry=registry,
                cache_manager=get_cache_manager(),
                llm_adapter=getattr(container, "llm_adapter", None),
            ).get_summary()
        except Exception as exc:
            return {"overall": "degraded", "checks": {}, "error": str(exc), "timestamp": time.time()}

    def _function_metrics(self) -> dict[str, Any]:
        try:
            try:
                from ..services.monitoring.instrumentation import (
                    _func_counters,
                    _func_error_counters,
                    _func_histograms,
                    is_debug_mode,
                )
            except ImportError:
                from services.monitoring.instrumentation import (
                    _func_counters,
                    _func_error_counters,
                    _func_histograms,
                    is_debug_mode,
                )

            functions = []
            for fqn, histogram in _func_histograms.items():
                calls = 0
                errors = 0
                duration_count = 0
                duration_sum = 0.0
                counter = _func_counters.get(fqn)
                if counter:
                    for sample in counter.collect()[0].samples:
                        if sample.name.endswith("_total"):
                            calls = int(sample.value)
                error_counter = _func_error_counters.get(fqn)
                if error_counter:
                    for sample in error_counter.collect()[0].samples:
                        if sample.name.endswith("_total"):
                            errors = int(sample.value)
                for sample in histogram.collect()[0].samples:
                    if sample.name.endswith("_count"):
                        duration_count = int(sample.value)
                    elif sample.name.endswith("_sum"):
                        duration_sum = float(sample.value)
                avg = duration_sum / duration_count if duration_count > 0 else 0.0
                functions.append(
                    {
                        "name": fqn,
                        "calls": calls,
                        "errors": errors,
                        "error_rate": round(errors / calls, 4) if calls else 0,
                        "duration": {
                            "count": duration_count,
                            "sum": round(duration_sum, 4),
                            "avg": round(avg, 6),
                        },
                    }
                )
            functions.sort(key=lambda item: item["duration"]["avg"], reverse=True)
            return {
                "debug_mode": is_debug_mode(),
                "functions": functions[:80],
                "timestamp": time.time(),
            }
        except Exception as exc:
            return {"debug_mode": False, "functions": [], "error": str(exc), "timestamp": time.time()}

    @staticmethod
    async def _safe_section(
        name: str,
        loader: Callable[[], Awaitable[Any]],
        errors: dict[str, str],
        *,
        default: Any,
    ) -> Any:
        try:
            data = await loader()
            return default if data is None else data
        except Exception as exc:
            logger.warning(f"[PluginPageAPI] {name} section unavailable: {exc}", exc_info=True)
            errors[name] = str(exc)
            return default

    @staticmethod
    async def _async_value(value: Any) -> Any:
        return value

    def _container(self) -> Any:
        return self._imports().get_container()

    @staticmethod
    def _imports() -> Any:
        class Imports:
            pass

        imports = Imports()
        try:
            from ..webui.blueprints.config import (
                DEPENDENCY_TIERS,
                MANUAL_DEPENDENCY_INSTALL_SOURCE,
                PIP_MIRROR_SOURCES,
            )
            from ..webui.dependencies import get_container
            from ..webui.services.config_service import ConfigService
            from ..webui.services.graph_service import GraphService
            from ..webui.services.integration_service import IntegrationService
            from ..webui.services.jargon_service import JargonService
            from ..webui.services.learning_service import LearningService
            from ..webui.services.metrics_service import MetricsService
            from ..webui.services.persona_backup_service import PersonaBackupService
            from ..webui.services.persona_review_service import PersonaReviewService
            from ..webui.services.persona_service import PersonaService
        except ImportError:
            from webui.blueprints.config import (
                DEPENDENCY_TIERS,
                MANUAL_DEPENDENCY_INSTALL_SOURCE,
                PIP_MIRROR_SOURCES,
            )
            from webui.dependencies import get_container
            from webui.services.config_service import ConfigService
            from webui.services.graph_service import GraphService
            from webui.services.integration_service import IntegrationService
            from webui.services.jargon_service import JargonService
            from webui.services.learning_service import LearningService
            from webui.services.metrics_service import MetricsService
            from webui.services.persona_backup_service import PersonaBackupService
            from webui.services.persona_review_service import PersonaReviewService
            from webui.services.persona_service import PersonaService

        imports.get_container = get_container
        imports.ConfigService = ConfigService
        imports.GraphService = GraphService
        imports.IntegrationService = IntegrationService
        imports.JargonService = JargonService
        imports.LearningService = LearningService
        imports.MetricsService = MetricsService
        imports.PersonaBackupService = PersonaBackupService
        imports.PersonaReviewService = PersonaReviewService
        imports.PersonaService = PersonaService
        imports.DEPENDENCY_TIERS = DEPENDENCY_TIERS
        imports.MANUAL_DEPENDENCY_INSTALL_SOURCE = MANUAL_DEPENDENCY_INSTALL_SOURCE
        imports.PIP_MIRROR_SOURCES = PIP_MIRROR_SOURCES
        return imports

    @staticmethod
    async def _body() -> dict[str, Any]:
        try:
            from quart import request

            data = await request.get_json(silent=True)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _query() -> Any:
        try:
            from quart import request

            return request.args
        except Exception:
            return {}

    @staticmethod
    def _query_value(args: Any, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            value = args.get(key, default)
        except Exception:
            value = default
        if value is None:
            return default
        value = str(value)
        return value if value != "" else default

    @classmethod
    def _query_int(cls, args: Any, key: str, default: int) -> int:
        try:
            value = args.get(key, default)
        except Exception:
            value = default
        return cls._as_int(value, default)

    @classmethod
    def _query_bool(cls, args: Any, key: str, default: bool) -> bool:
        value = cls._query_value(args, key, str(default).lower())
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def _query_optional_bool(cls, args: Any, key: str) -> Optional[bool]:
        value = cls._query_value(args, key)
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return None

    @classmethod
    def _body_int(cls, body: Mapping[str, Any], key: str, default: int = 0) -> int:
        return cls._as_int(body.get(key), default)

    @staticmethod
    def _body_list(
        body: Mapping[str, Any],
        key: str,
        *,
        fallback_key: Optional[str] = None,
    ) -> list[str]:
        value = body.get(key)
        if value is None and fallback_key:
            value = body.get(fallback_key)
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item is not None]

    @staticmethod
    def _serialize_learning_stats(stats: Any) -> dict[str, Any]:
        if stats is None:
            return {
                "total_messages_collected": 0,
                "filtered_messages": 0,
                "style_updates": 0,
                "persona_updates": 0,
                "last_learning_time": None,
                "last_persona_update": None,
            }
        if is_dataclass(stats):
            return asdict(stats)
        return {
            "total_messages_collected": int(getattr(stats, "total_messages_collected", 0) or 0),
            "filtered_messages": int(getattr(stats, "filtered_messages", 0) or 0),
            "style_updates": int(getattr(stats, "style_updates", 0) or 0),
            "persona_updates": int(getattr(stats, "persona_updates", 0) or 0),
            "last_learning_time": getattr(stats, "last_learning_time", None),
            "last_persona_update": getattr(stats, "last_persona_update", None),
        }

    @classmethod
    def _build_modules(
        cls,
        *,
        plugin_config: Any,
        jargon_stats: dict[str, Any],
        style_stats: dict[str, Any],
        persona_state: dict[str, Any],
        backups: dict[str, Any],
        metrics: dict[str, Any],
    ) -> list[dict[str, Any]]:
        confirmed_jargon = cls._as_int(jargon_stats.get("confirmed_jargon"), 0)
        unique_styles = cls._as_int(
            style_stats.get("unique_styles") or style_stats.get("total_samples"), 0
        )
        persona_prompt_len = cls._as_int(persona_state.get("prompt_length"), 0)
        backup_total = cls._as_int(backups.get("total"), 0)
        intelligence_score = cls._as_number(metrics.get("overall_score"))

        return [
            {
                "id": "jargon",
                "title": "黑话学习",
                "description": "群内专属词、梗和语义推断",
                "enabled": cls._config_bool(plugin_config, "enable_jargon_learning", True),
                "metric": confirmed_jargon,
                "metric_label": "已确认黑话",
                "accent": "#0f9f8f",
                "target": "jargon-learning",
            },
            {
                "id": "style",
                "title": "表达方式学习",
                "description": "语气、句式、few-shot 与表达模式",
                "enabled": cls._config_bool(plugin_config, "enable_style_learning", True),
                "metric": unique_styles,
                "metric_label": "风格样本",
                "accent": "#4169e1",
                "target": "expression-learning",
            },
            {
                "id": "persona",
                "title": "人格学习",
                "description": "人格演化、更新审查与备份恢复",
                "enabled": cls._config_bool(plugin_config, "enable_persona_evolution", True),
                "metric": persona_prompt_len,
                "metric_label": "人格提示词字数",
                "accent": "#d97706",
                "target": "persona-learning",
            },
            {
                "id": "reviews",
                "title": "审查队列",
                "description": "学习结果进入人格前的确认区",
                "enabled": True,
                "metric": backup_total,
                "metric_label": "近期人格备份",
                "accent": "#e11d48",
                "target": "reviews",
            },
            {
                "id": "metrics",
                "title": "智能指标",
                "description": "回复多样性、好感度与智能评分",
                "enabled": True,
                "metric": round(intelligence_score, 2),
                "metric_label": "综合评分",
                "accent": "#0ea5e9",
                "target": "metrics",
            },
        ]

    @staticmethod
    def _build_webui_snapshot(plugin_config: Any, webui_config: Any) -> dict[str, Any]:
        enabled = PluginPageApi._config_bool(plugin_config, "enable_web_interface", True)
        host = getattr(webui_config, "host", None) or PluginPageApi._config_value(
            plugin_config, "web_interface_host", "127.0.0.1"
        )
        port = getattr(webui_config, "port", None) or PluginPageApi._config_value(
            plugin_config, "web_interface_port", 7833
        )
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 7833
        display_host = "127.0.0.1" if str(host) in {"0.0.0.0", "::"} else str(host)
        return {
            "enabled": enabled,
            "host": host,
            "bind_host": host,
            "display_host": display_host,
            "port": port,
            "dashboard_url": f"http://{display_host}:{port}",
            "public_url_strategy": "browser_host_for_local_bind",
            "client_rewrite_hosts": [
                "localhost",
                "127.0.0.1",
                "0.0.0.0",
                "::",
                "::1",
                "[::]",
                "[::1]",
            ],
        }

    @staticmethod
    def _build_quick_links(plugin_config: Any, webui_config: Any) -> list[dict[str, str]]:
        webui = PluginPageApi._build_webui_snapshot(plugin_config, webui_config)
        return [
            {
                "id": "embedded_dashboard",
                "label": "内嵌 WebUI",
                "url": "#/plugin-page/astrbot_plugin_self_learning/dashboard",
                "description": "AstrBot 官方插件页",
            },
            {
                "id": "full_dashboard",
                "label": "独立 WebUI",
                "url": webui["dashboard_url"],
                "description": "打开 7833 独立管理界面",
            },
            {
                "id": "plugin_settings",
                "label": "插件设置",
                "url": "#/extension",
                "description": "回到 AstrBot 插件管理",
            },
        ]

    @staticmethod
    def _empty_jargon_stats() -> dict[str, Any]:
        return {
            "total_candidates": 0,
            "confirmed_jargon": 0,
            "completed_inference": 0,
            "total_occurrences": 0,
            "average_count": 0,
            "active_groups": 0,
        }

    @staticmethod
    def _empty_persona_state(group_id: str = "default") -> dict[str, Any]:
        return {
            "group_id": group_id,
            "persona": {"persona_id": "default", "name": "默认人格"},
            "prompt_preview": "",
            "prompt_length": 0,
            "begin_dialog_count": 0,
            "tool_count": 0,
            "degraded": True,
        }

    @staticmethod
    def _config_value(config: Any, name: str, default: Any = None) -> Any:
        if config is None:
            return default
        if isinstance(config, dict):
            return config.get(name, default)
        return getattr(config, name, default)

    @staticmethod
    def _config_bool(config: Any, name: str, default: bool = False) -> bool:
        value = PluginPageApi._config_value(config, name, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _as_int(value: Any, default: int = 0) -> int:
        try:
            return int(value if value is not None else default)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_number(value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _system_metrics() -> dict[str, Any]:
        metrics = {"cpu_percent": 0, "memory_percent": 0, "disk_usage_percent": 0}
        try:
            import psutil

            metrics["cpu_percent"] = psutil.cpu_percent(interval=0)
            memory = psutil.virtual_memory()
            metrics["memory_percent"] = memory.percent
            metrics["memory_used_gb"] = round(memory.used / (1024**3), 2)
            metrics["memory_total_gb"] = round(memory.total / (1024**3), 2)
            disk = psutil.disk_usage("/")
            metrics["disk_usage_percent"] = round(disk.used / disk.total * 100, 2)
        except Exception:
            pass
        return metrics

    @staticmethod
    def _active_learning_sessions(container: Any) -> int:
        progressive_learning = getattr(container, "progressive_learning", None)
        if not progressive_learning:
            return 0
        try:
            return sum(1 for active in progressive_learning.learning_active.values() if active)
        except Exception:
            return 0

    @staticmethod
    def _parse_jsonish(value: Any, fallback: Any) -> Any:
        if value is None or value == "":
            return fallback
        if isinstance(value, (list, dict)):
            return value
        try:
            import json

            return json.loads(value)
        except Exception:
            return fallback

    @classmethod
    def _effective_batch_quality(cls, batch: Any, max_batch_size: int = 200) -> float:
        stored = cls._optional_float(getattr(batch, "quality_score", None))
        if stored is not None and stored > 0:
            return stored
        if getattr(batch, "success", None) is False:
            return stored if stored is not None else 0.0

        processed = max(
            cls._as_int(getattr(batch, "processed_messages", 0), 0),
            cls._as_int(getattr(batch, "message_count", 0), 0),
        )
        filtered = cls._as_int(getattr(batch, "filtered_count", 0), 0)
        if processed <= 0 and filtered <= 0:
            return stored if stored is not None else 0.0

        batch_size = max(1, cls._as_int(max_batch_size, 200))
        volume_score = min(processed / batch_size, 1.0)
        filtered_score = min(filtered / max(processed, filtered, 1), 1.0) if filtered else 0.0
        success_score = 0.10 if getattr(batch, "success", True) else 0.0
        return max(0.0, min(1.0, 0.25 + volume_score * 0.45 + filtered_score * 0.20 + success_score))

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_ts(value: Any) -> str:
        if not value:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        try:
            return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)

    @staticmethod
    def _metadata_version() -> str:
        metadata_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "metadata.yaml")
        try:
            with open(metadata_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip().startswith("version:"):
                        return line.split(":", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
        return "3.2.1"

    @classmethod
    def _to_plain(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if is_dataclass(value):
            return cls._to_plain(asdict(value))
        if isinstance(value, dict):
            return {str(key): cls._to_plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._to_plain(item) for item in value]
        if hasattr(value, "model_dump"):
            try:
                return cls._to_plain(value.model_dump())
            except Exception:
                return str(value)
        return str(value)

    @classmethod
    def _ok(cls, data: Any) -> dict[str, Any]:
        return {"status": "ok", "success": True, "data": cls._to_plain(data)}

    @classmethod
    def _operation(cls, success: bool, message: str, **data: Any) -> dict[str, Any]:
        return cls._ok({"success": bool(success), "message": message, **data})
