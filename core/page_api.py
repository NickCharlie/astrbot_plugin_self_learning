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

    # 容器未绑定时补绑的最小间隔（秒），避免服务未就绪时每次请求都重试并刷日志。
    _CONTAINER_RETRY_INTERVAL = 5.0

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self._container_bind_last_try = -self._CONTAINER_RETRY_INTERVAL

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
            ("batches", self.get_batches, ["GET"], "Self Learning embedded learning batches"),
            ("batches/action", self.post_batches_action, ["POST"], "Self Learning embedded learning batch actions"),
            ("persona", self.get_persona, ["GET"], "Self Learning embedded persona module"),
            ("persona/action", self.post_persona_action, ["POST"], "Self Learning embedded persona actions"),
            ("shadow-mode", self.get_shadow_mode, ["GET"], "Self Learning embedded shadow mode status"),
            ("shadow-mode/candidates", self.get_shadow_mode_candidates, ["GET"], "Self Learning embedded shadow mode candidates"),
            ("shadow-mode/action", self.post_shadow_mode_action, ["POST"], "Self Learning embedded shadow mode actions"),
            ("content", self.get_content, ["GET"], "Self Learning embedded learning content module"),
            ("content/action", self.post_content_action, ["POST"], "Self Learning embedded content actions"),
            ("graphs", self.get_graphs, ["GET"], "Self Learning embedded graph module"),
            ("graphs/social/groups", self.get_social_groups, ["GET"], "Self Learning embedded social graph groups"),
            ("graphs/social", self.get_social_relations, ["GET"], "Self Learning embedded social relation graph"),
            ("graphs/social/action", self.post_social_action, ["POST"], "Self Learning embedded social relation actions"),
            ("emotion/board", self.get_emotion_board, ["GET"], "Self Learning embedded emotion board"),
            ("emotion/trends", self.get_emotion_trends, ["GET"], "Self Learning embedded emotion trends"),
            ("emotion/action", self.post_emotion_action, ["POST"], "Self Learning embedded emotion actions"),
            ("metrics", self.get_metrics, ["GET"], "Self Learning embedded metrics module"),
            ("monitoring", self.get_monitoring, ["GET"], "Self Learning embedded monitoring module"),
            ("integrations", self.get_integrations, ["GET"], "Self Learning embedded integrations module"),
            ("integrations/action", self.post_integrations_action, ["POST"], "Self Learning embedded integrations actions"),
            ("settings", self.get_settings, ["GET"], "Self Learning embedded settings module"),
            ("settings/action", self.post_settings_action, ["POST"], "Self Learning embedded settings actions"),
            ("data/statistics", self.get_data_statistics, ["GET"], "Self Learning embedded data statistics"),
            ("data/clear", self.post_data_clear, ["POST"], "Self Learning embedded data clearing"),
            ("bug-report", self.get_bug_report_config, ["GET"], "Self Learning embedded bug report config"),
            ("bug-report/submit", self.post_bug_report, ["POST"], "Self Learning embedded bug report submission"),
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
            "reviews", lambda: self._load_reviews(limit=10), errors, default={}
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
        # 与独立 WebUI /api/data/statistics 同源：首页「内容样本」「记忆 / 知识图谱」读数
        data_statistics = await self._safe_section(
            "data_statistics", self._load_data_statistics, errors, default={}
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
                "data_statistics": data_statistics,
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
            if action == "batch_review":
                jargon_ids = [
                    self._as_int(item, 0)
                    for item in self._body_list(body, "ids", fallback_key="jargon_ids")
                ]
                jargon_ids = [jargon_id for jargon_id in jargon_ids if jargon_id]
                result = await service.batch_review_jargon(
                    jargon_ids,
                    str(body.get("decision") or body.get("review_action") or "approve"),
                    meaning=body.get("meaning"),
                )
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量审查黑话完成",
                    result=result,
                )
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
            if action == "batch_delete":
                jargon_ids = [
                    self._as_int(item, 0)
                    for item in self._body_list(body, "ids", fallback_key="jargon_ids")
                ]
                jargon_ids = [jargon_id for jargon_id in jargon_ids if jargon_id]
                result = await service.batch_delete_jargon(jargon_ids)
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量删除黑话完成",
                    result=result,
                )
            if action == "import_jargons":
                result = await service.import_jargons({
                    "text": str(body.get("text") or ""),
                    "group_id": str(body.get("group_id") or ""),
                    # is_global 原样透传，由 service 严格解析
                    "is_global": body.get("is_global", False),
                })
                details = result.get("details") or {}
                # 存在失败行时同样按失败应答：内嵌页据此保留输入框内容供修正
                # 重试（服务对已入库行幂等，原样重提只会计入 skipped）。
                succeeded = bool(result.get("success")) and not (details.get("failed") or [])
                return self._operation(
                    succeeded,
                    result.get("message")
                    or result.get("error")
                    or ("黑话导入完成" if succeeded else "黑话导入失败"),
                    result=result,
                )
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
        # 表达方式学习页：统计、学习模式与表达样本库（四分类内容与独立 WebUI
        # /api/style_learning/content_text 同源）。待审表达统一在审查队列处理。
        try:
            container = self._container()
            LearningService = self._imports().LearningService
            service = LearningService(container)
            results, patterns, content = await asyncio.gather(
                service.get_style_learning_results(),
                service.get_style_learning_patterns(),
                self._get_learning_content_text(),
            )
            return self._ok(
                {
                    "results": results,
                    "patterns": patterns,
                    "content": content,
                }
            )
        except Exception as exc:
            logger.error(f"[PluginPageAPI] style module failed: {exc}", exc_info=True)
            return self._ok(
                {
                    "results": {"statistics": {}, "style_progress": []},
                    "patterns": {
                        "emotion_patterns": [],
                        "language_patterns": [],
                        "topic_patterns": [],
                    },
                    "content": {"dialogues": [], "analysis": [], "features": [], "history": []},
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
            if action == "batch_review":
                review_ids = [
                    self._as_int(item, 0)
                    for item in self._body_list(body, "ids", fallback_key="review_ids")
                ]
                review_ids = [review_id for review_id in review_ids if review_id]
                result = await service.batch_review_style_learning_reviews(
                    review_ids,
                    str(body.get("decision") or body.get("review_action") or "approve"),
                    str(body.get("comment") or ""),
                )
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量表达审查完成",
                    result=result,
                )
            if action == "delete":
                success, message = await service.delete_style_learning_review(
                    self._body_int(body, "id")
                )
                return self._operation(success, message)
            if action == "batch_delete":
                review_ids = [
                    self._as_int(item, 0)
                    for item in self._body_list(body, "ids", fallback_key="review_ids")
                ]
                review_ids = [review_id for review_id in review_ids if review_id]
                result = await service.batch_delete_style_learning_reviews(review_ids)
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量删除表达审查完成",
                    result=result,
                )
            if action == "update":
                success, message, item = await self._update_style_review(body)
                return self._operation(success, message, item=item)
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
                persona_keyword=(
                    self._query_value(args, "persona_keyword")
                    or self._query_value(args, "keyword")
                    or ""
                ),
                style_keyword=(
                    self._query_value(args, "style_keyword")
                    or self._query_value(args, "keyword")
                    or ""
                ),
                jargon_keyword=(
                    self._query_value(args, "jargon_keyword")
                    or self._query_value(args, "keyword")
                    or ""
                ),
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
            if action == "batch_review_style":
                learning_service = imports.LearningService(container)
                review_ids = [
                    self._as_int(item, 0)
                    for item in self._body_list(body, "ids", fallback_key="review_ids")
                ]
                review_ids = [review_id for review_id in review_ids if review_id]
                result = await learning_service.batch_review_style_learning_reviews(
                    review_ids,
                    str(body.get("decision") or body.get("review_action") or "approve"),
                    str(body.get("comment") or ""),
                )
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量表达审查完成",
                    result=result,
                )
            if action == "batch_delete_style":
                learning_service = imports.LearningService(container)
                review_ids = [
                    self._as_int(item, 0)
                    for item in self._body_list(body, "ids", fallback_key="review_ids")
                ]
                review_ids = [review_id for review_id in review_ids if review_id]
                result = await learning_service.batch_delete_style_learning_reviews(
                    review_ids
                )
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量删除表达审查完成",
                    result=result,
                )
            if action == "batch_review_jargon":
                jargon_service = imports.JargonService(container)
                jargon_ids = [
                    self._as_int(item, 0)
                    for item in self._body_list(body, "ids", fallback_key="jargon_ids")
                ]
                jargon_ids = [jargon_id for jargon_id in jargon_ids if jargon_id]
                result = await jargon_service.batch_review_jargon(
                    jargon_ids,
                    str(body.get("decision") or body.get("review_action") or "approve"),
                    meaning=body.get("meaning"),
                )
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量黑话审查完成",
                    result=result,
                )
            if action == "batch_delete_jargon":
                jargon_service = imports.JargonService(container)
                jargon_ids = [
                    self._as_int(item, 0)
                    for item in self._body_list(body, "ids", fallback_key="jargon_ids")
                ]
                jargon_ids = [jargon_id for jargon_id in jargon_ids if jargon_id]
                result = await jargon_service.batch_delete_jargon(jargon_ids)
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "批量删除黑话完成",
                    result=result,
                )
            if action.startswith("style_"):
                learning_service = imports.LearningService(container)
                review_id = self._body_int(body, "id")
                if action == "style_approve":
                    success, message = await learning_service.approve_style_learning_review(review_id)
                elif action == "style_reject":
                    success, message = await learning_service.reject_style_learning_review(review_id)
                elif action == "style_delete":
                    success, message = await learning_service.delete_style_learning_review(review_id)
                else:
                    return self._operation(False, f"未知风格审查操作: {action}")
                return self._operation(success, message)
            if action == "import_jargons":
                jargon_service = imports.JargonService(container)
                result = await jargon_service.import_jargons({
                    "text": str(body.get("text") or ""),
                    "group_id": str(body.get("group_id") or ""),
                    # is_global 原样透传，由 service 严格解析
                    "is_global": body.get("is_global", False),
                })
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "黑话导入完成",
                    result=result,
                )
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
        # 与独立 WebUI 人格学习页同口径：备份取全部群组最近 8 条
        limit = self._query_int(args, "limit", 8)
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
            if action == "get":
                # 与独立 WebUI /api/persona_management/get/<id> 同一服务方法
                data = await persona_service.get_persona_details(str(body.get("persona_id") or ""))
                if not data:
                    return self._operation(False, "人格不存在")
                return self._operation(True, "人格详情已读取", persona=data)
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

    def _shadow_service(self) -> Any:
        imports = self._imports()
        database_manager = getattr(self._container(), "database_manager", None)
        return imports.ShadowModeService(database_manager)

    async def get_shadow_mode(self) -> dict[str, Any]:
        try:
            return self._ok(await self._shadow_service().get_status())
        except Exception as exc:
            logger.error(f"[PluginPageAPI] shadow mode status failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

    async def get_shadow_mode_candidates(self) -> dict[str, Any]:
        args = self._query()
        try:
            data = await self._shadow_service().list_candidates(
                source_type=self._query_value(args, "source", "live"),
                group_id=self._query_value(args, "group_id", ""),
            )
            return self._ok(data)
        except ValueError:
            return self._operation(False, "请求处理失败，请稍后重试")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] shadow candidates failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

    async def post_shadow_mode_action(self) -> dict[str, Any]:
        body = await self._body()
        action = str(body.get("action", "")).strip()
        try:
            service = self._shadow_service()
            if action == "learn":
                profile = await service.learn(
                    source_type=str(body.get("source_type") or body.get("source") or "live"),
                    source_group_id=str(body.get("source_group_id") or body.get("group_id") or ""),
                    target_group_id=str(body.get("target_group_id") or body.get("group_id") or ""),
                    sender_id=str(body.get("sender_id") or ""),
                    activate=self._body_bool(body, "activate", True),
                )
                return self._operation(True, "影子模式已学习并启用", profile=profile)
            if action == "set_enabled":
                profile = await service.set_enabled(
                    self._body_int(body, "profile_id"),
                    self._body_bool(body, "enabled", True),
                )
                return self._operation(True, "影子模式状态已更新", profile=profile)
            return self._operation(False, f"未知影子模式操作: {action or '(empty)'}")
        except ValueError as exc:
            logger.warning(f"[PluginPageAPI] shadow action rejected: {exc}")
            return self._operation(False, str(exc) or "请求处理失败，请稍后重试")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] shadow action failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

    async def get_emotion_board(self) -> dict[str, Any]:
        try:
            service = self._imports().EmotionBoardService(self._container())
            return self._ok(await service.get_board())
        except Exception as exc:
            logger.error(f"[内嵌页] 读取情绪板块失败: {exc}", exc_info=True)
            return self._ok({"available": False, "error": str(exc)})

    async def get_emotion_trends(self) -> dict[str, Any]:
        args = self._query()
        days = self._query_int(args, "days", 14)
        try:
            service = self._imports().EmotionBoardService(self._container())
            return self._ok(await service.get_trends(days))
        except Exception as exc:
            logger.error(f"[内嵌页] 读取情绪走向失败: {exc}", exc_info=True)
            return self._ok({"days": days, "error": str(exc)})

    async def post_emotion_action(self) -> dict[str, Any]:
        body = await self._body()
        try:
            service = self._imports().EmotionBoardService(self._container())
            result = await service.run_action(body)
            return self._operation(
                bool(result.get("success")),
                str(result.get("message", "")),
                **{k: v for k, v in result.items() if k not in {"success", "message"}},
            )
        except Exception as exc:
            logger.error(f"[内嵌页] 情绪板块操作失败: {exc}", exc_info=True)
            return self._operation(False, f"情绪板块操作失败: {exc}")

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

    async def get_batches(self) -> dict[str, Any]:
        """审查队列「最近学习批次」：与独立 WebUI /api/batches 同一服务（分页）。

        与独立版一样，分页查询失败时回退到趋势数据中的最近批次（单页）。
        """
        args = self._query()
        page = max(1, self._query_int(args, "page", 1))
        page_size = max(1, min(self._query_int(args, "page_size", 10), 100))
        try:
            return self._ok(
                await self._get_learning_batches(page=page, page_size=page_size, raise_errors=True)
            )
        except Exception as exc:
            logger.warning(f"[PluginPageAPI] learning batches fallback to trends: {exc}")
            recent: list[Any] = []
            database_manager = getattr(self._container(), "database_manager", None)
            if database_manager and hasattr(database_manager, "get_trends_data"):
                try:
                    trends = await database_manager.get_trends_data()
                    if isinstance(trends, dict) and isinstance(trends.get("recent_batches"), list):
                        recent = trends["recent_batches"]
                except Exception as trend_exc:
                    logger.warning(f"[PluginPageAPI] trends fallback unavailable: {trend_exc}")
            return self._ok(
                {
                    "batches": recent,
                    "total": len(recent),
                    "page": 1,
                    "page_size": page_size,
                    "total_pages": 1,
                }
            )

    async def post_batches_action(self) -> dict[str, Any]:
        """批次卡片动作：重跑学习（按批次群组）/ 删除批次，与独立 WebUI 同一实现。"""
        body = await self._body()
        action = str(body.get("action", "")).strip()
        try:
            if action == "relearn":
                group_id = str(body.get("group_id") or "").strip()
                if not group_id:
                    return self._operation(False, "群组ID不能为空")
                result = await self._relearn(group_id)
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "重新学习已提交",
                    result=result,
                )
            if action == "relearn_all":
                result = await self._relearn("default")
                return self._operation(
                    bool(result.get("success")),
                    result.get("message") or result.get("error") or "重新学习已提交",
                    result=result,
                )
            if action == "delete":
                success, message = await self._delete_learning_batch(self._body_int(body, "id"))
                return self._operation(success, message)
            return self._operation(False, f"未知学习批次操作: {action or '(empty)'}")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] batch action failed: {exc}", exc_info=True)
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

    # ── 社交关系图谱：与独立 WebUI /api/social_relations/* 同一组服务方法 ──
    async def get_social_groups(self) -> dict[str, Any]:
        """可分析社交关系的群组列表（独立版 GET /api/social_relations/groups）。"""
        try:
            service = self._imports().SocialService(self._container())
            groups = await service.get_available_groups()
            return self._ok({"groups": groups, "total": len(groups)})
        except Exception as exc:
            logger.error(f"[PluginPageAPI] social groups failed: {exc}", exc_info=True)
            return self._operation(False, "请求处理失败，请稍后重试")

    async def get_social_relations(self) -> dict[str, Any]:
        """指定群组的成员与关系（独立版 GET /api/social_relations/<group_id>）。"""
        group_id = str(self._query_value(self._query(), "group_id", "") or "").strip()
        if not group_id:
            return self._operation(False, "群组ID不能为空")
        try:
            service = self._imports().SocialService(self._container())
            return self._ok(await service.get_social_relations(group_id))
        except Exception as exc:
            logger.error(f"[PluginPageAPI] social relations failed: {exc}", exc_info=True)
            return self._operation(False, "请求处理失败，请稍后重试")

    async def post_social_action(self) -> dict[str, Any]:
        """重新分析 / 清空关系 / 创建分享链接，与独立版 analyze、clear、share 路由同源。"""
        body = await self._body()
        action = str(body.get("action", "")).strip()
        group_id = str(body.get("group_id") or "").strip()
        if not group_id:
            return self._operation(False, "群组ID不能为空")
        try:
            imports = self._imports()
            container = self._container()
            if action == "analyze":
                success, message = await imports.SocialService(container).trigger_analysis(group_id)
                return self._operation(success, message)
            if action == "clear":
                # 不可恢复操作：只接受页面二次确认后发出的请求
                if body.get("confirmed") is not True:
                    return self._operation(False, "清空社交关系需要在页面中确认后执行")
                success, message = await imports.SocialService(container).clear_relations(group_id)
                return self._operation(success, message)
            if action == "share":
                share_service_cls = imports.GraphShareService
                try:
                    expires_hours = int(body.get("expires_hours", 168))
                except (TypeError, ValueError):
                    return self._operation(False, "expires_hours 必须是整数")
                min_hours = share_service_cls.MIN_EXPIRES_HOURS
                max_hours = share_service_cls.MAX_EXPIRES_HOURS
                if expires_hours < min_hours or expires_hours > max_hours:
                    return self._operation(False, f"expires_hours 必须在 {min_hours}~{max_hours} 之间")
                share = share_service_cls(container).create_share(
                    group_id=group_id, expires_hours=expires_hours
                )
                share_path = f"/graph/share/{share['token']}"
                # 分享页由独立 WebUI 提供；内嵌页运行在 AstrBot 面板内，链接需指向独立 WebUI 地址
                webui = self._build_webui_snapshot(
                    getattr(self.plugin, "plugin_config", None),
                    getattr(container, "webui_config", None),
                )
                share_url = f"{webui['dashboard_url']}{share_path}" if webui.get("enabled") else None
                return self._operation(
                    True,
                    "分享链接已创建",
                    data={
                        "group_id": group_id,
                        "share_url": share_url,
                        "share_path": share_path,
                        "token": share["token"],
                        "expires_hours": share["expires_hours"],
                        "expires_at": share["expires_at_iso"],
                    },
                )
            return self._operation(False, f"未知社交关系操作: {action or '(empty)'}")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] social action failed: {exc}", exc_info=True)
            return self._operation(False, "请求处理失败，请稍后重试")

    async def get_metrics(self) -> dict[str, Any]:
        return self._ok(await self._load_metrics())

    async def get_monitoring(self) -> dict[str, Any]:
        return self._ok(await self._load_monitoring())

    async def get_integrations(self) -> dict[str, Any]:
        return self._ok(await self._load_integrations())

    async def post_integrations_action(self) -> dict[str, Any]:
        body = await self._body()
        action = str(body.get("action", "")).strip()
        try:
            imports = self._imports()
            database_manager = getattr(self._container(), "database_manager", None)
            maibot_importer = imports.MaiBotLearningImporter(database_manager)
            maibot_source_args = {
                "maibot_root": body.get("maibot_root") or None,
                "db_path": body.get("db_path") or body.get("maibot_db_path") or None,
                "memorix_db_path": body.get("memorix_db_path") or None,
                "payload": body.get("payload") if isinstance(body.get("payload"), dict) else None,
            }
            if action == "maibot_preview":
                preview = maibot_importer.preview(**maibot_source_args)
                return self._operation(True, "MaiBot 学习数据预览完成", preview=preview)
            if action == "maibot_export":
                payload = maibot_importer.export_json(**maibot_source_args)
                return self._operation(True, "MaiBot 学习数据已导出为标准包", payload=payload)
            if action == "maibot_import":
                result = await maibot_importer.import_from_source(
                    **maibot_source_args,
                    default_group_id=str(body.get("default_group_id") or "global"),
                    import_expressions=self._body_bool(body, "import_expressions", True),
                    import_jargons=self._body_bool(body, "import_jargons", True),
                    import_memories=self._body_bool(body, "import_memories", True),
                    approve_checked_expressions=self._body_bool(
                        body, "approve_checked_expressions", True
                    ),
                )
                return self._operation(
                    bool(result.get("success")),
                    "MaiBot 学习数据导入完成" if result.get("success") else "MaiBot 学习数据导入存在错误",
                    result=result,
                )
            qchat_importer = imports.QQChatHistoryImporter(database_manager)
            qchat_source_args = {
                "source_path": body.get("source_path") or body.get("path") or body.get("qq_history_path") or None,
                "payload": body.get("payload") if isinstance(body.get("payload"), (dict, list, str)) else None,
                "json_text": body.get("json_text") or None,
            }
            if action == "qchat_preview":
                preview = qchat_importer.preview(
                    **qchat_source_args,
                    default_group_id=str(body.get("default_group_id") or body.get("group_id") or ""),
                    include_training_pairs=self._body_bool(body, "include_training_pairs", False),
                    max_messages=self._body_int(body, "max_messages", 100000),
                    min_text_length=self._body_int(body, "min_text_length", 2),
                )
                return self._operation(True, "QQ 聊天记录预览完成", preview=preview)
            if action == "qchat_import":
                result = await qchat_importer.import_from_source(
                    **qchat_source_args,
                    default_group_id=str(body.get("default_group_id") or body.get("group_id") or ""),
                    include_training_pairs=self._body_bool(body, "include_training_pairs", False),
                    max_messages=self._body_int(body, "max_messages", 100000),
                    min_text_length=self._body_int(body, "min_text_length", 2),
                )
                return self._operation(
                    bool(result.get("success")),
                    "QQ 聊天记录导入完成" if result.get("success") else "QQ 聊天记录导入存在错误",
                    result=result,
                )
            if action in {"worldbook_preview", "worldbook_import", "worldbook_history"}:
                WorldBookImporter = imports.WorldBookImporter
                worldbook_importer = WorldBookImporter(database_manager)
                # 与独立 WebUI 一致：不接受请求传入的服务器端路径，只收 JSON 内容。
                payload = body.get("payload") if body.get("payload") is not None else body.get("worldbook")
                worldbook_source_args = {
                    "payload": payload if isinstance(payload, (dict, list, str)) else None,
                    "json_text": body.get("json_text") or None,
                    "json_path": None,
                }
                if action == "worldbook_preview":
                    preview = worldbook_importer.preview(**worldbook_source_args)
                    return self._operation(True, "世界书预览完成", preview=preview)
                if action == "worldbook_import":
                    result = await worldbook_importer.import_from_source(
                        **worldbook_source_args,
                        default_group_id=str(body.get("default_group_id") or body.get("group_id") or "global"),
                        import_memories=self._body_bool(body, "import_memories", True),
                        import_jargons=self._body_bool(body, "import_jargons", True),
                        import_knowledge_graph=self._body_bool(body, "import_knowledge_graph", True),
                        include_disabled=self._body_bool(body, "include_disabled", False),
                    )
                    return self._operation(
                        bool(result.get("success")),
                        "世界书导入完成" if result.get("success") else "世界书导入存在错误",
                        result=result,
                    )
                history = await worldbook_importer.import_history(
                    limit=max(1, min(self._body_int(body, "limit", 8), 50)),
                    offset=max(0, self._body_int(body, "offset", 0)),
                )
                return self._operation(True, "世界书导入历史已读取", history=history)
            return self._operation(False, f"未知融合操作: {action or '(empty)'}")
        except Exception as exc:
            logger.error(f"[PluginPageAPI] integrations action failed: {exc}", exc_info=True)
            return self._operation(False, str(exc))

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

    # ── 数据管理：与独立 WebUI /api/data/* 同一服务（DataManagementService） ──
    _DATA_CLEAR_METHODS: dict[str, str] = {
        "messages": "clear_messages",
        "persona_reviews": "clear_persona_reviews",
        "style_learning": "clear_style_learning",
        "jargon": "clear_jargon",
        "learning_history": "clear_learning_history",
        "all": "clear_all",
    }

    async def get_data_statistics(self) -> dict[str, Any]:
        """各模块数据行数统计（独立版 GET /api/data/statistics）。"""
        try:
            return self._ok(await self._load_data_statistics())
        except Exception as exc:
            logger.error(f"[PluginPageAPI] data statistics failed: {exc}", exc_info=True)
            return self._operation(False, "请求处理失败，请稍后重试")

    async def post_data_clear(self) -> dict[str, Any]:
        """按模块清空数据（独立版 DELETE /api/data/clear/<target>）。"""
        body = await self._body()
        target = str(body.get("target") or "").strip()
        method_name = self._DATA_CLEAR_METHODS.get(target)
        if not method_name:
            return self._operation(False, f"未知清空目标: {target or '(empty)'}")
        # 不可恢复操作：只接受页面二次确认后发出的请求
        if body.get("confirmed") is not True:
            return self._operation(False, "清空数据需要在页面中确认后执行")
        try:
            service = self._imports().DataManagementService(self._container())
            success, message, deleted = await getattr(service, method_name)()
            return self._operation(success, message, deleted=deleted)
        except Exception as exc:
            logger.error(f"[PluginPageAPI] data clear failed: {exc}", exc_info=True)
            return self._operation(False, "请求处理失败，请稍后重试")

    # ── Bug 反馈：与独立 WebUI /api/bug_report* 同一服务（BugReportService） ──
    async def get_bug_report_config(self) -> dict[str, Any]:
        """Bug 自助提交配置与日志预览（独立版 GET /api/bug_report/config）。"""
        try:
            service = self._imports().BugReportService(self._container())
            return self._ok(service.get_bug_report_config())
        except Exception as exc:
            logger.error(f"[PluginPageAPI] bug report config failed: {exc}", exc_info=True)
            return self._operation(False, "请求处理失败，请稍后重试")

    async def post_bug_report(self) -> dict[str, Any]:
        """提交 Bug 报告（独立版 POST /api/bug_report）。"""
        body = await self._body()
        try:
            service = self._imports().BugReportService(self._container())
            success, message, response_data = await service.submit_bug_report(body)
            return self._operation(success, message, data=response_data)
        except Exception as exc:
            logger.error(f"[PluginPageAPI] bug report submit failed: {exc}", exc_info=True)
            return self._operation(False, "请求处理失败，请稍后重试")

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

        # 首页模块卡与快捷入口已与独立 WebUI 一样由前端静态定义（内嵌页 app.js 的
        # homeModules / homeQuickLinks），这里只返回原始数据，不再下发宿主链接。
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
        persona_keyword: str = "",
        style_keyword: str = "",
        jargon_keyword: str = "",
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
                    keyword=persona_keyword,
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
                lambda: learning_service.get_style_learning_reviews(
                    limit=bounded_limit,
                    keyword=style_keyword,
                ),
                errors,
                default={"reviews": [], "total": 0},
            ),
            self._safe_section(
                "jargon_pending",
                lambda: (
                    self._load_pending_jargon_reviews(
                        jargon_service,
                        keyword=jargon_keyword,
                        limit=min(bounded_limit, 50),
                    )
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

    async def _load_pending_jargon_reviews(
        self,
        jargon_service: Any,
        *,
        keyword: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        keyword = str(keyword or "").strip()
        if keyword:
            items = await jargon_service.search_jargon(
                keyword,
                pending_only=True,
            )
            return {
                "jargon_list": items[:limit],
                "total": len(items),
                "page": 1,
                "page_size": limit,
                "total_pages": 1,
            }
        return await jargon_service.get_jargon_list(
            page=1,
            page_size=limit,
            confirmed=False,
            pending_only=True,
        )

    async def _load_persona(
        self,
        *,
        group_id: str,
        limit: int,
        pending_limit: int = 10,
        reviewed_limit: int = 5,
    ) -> dict[str, Any]:
        imports = self._imports()
        container = self._container()
        errors: dict[str, str] = {}
        persona_service = imports.PersonaService(container)
        backup_service = imports.PersonaBackupService(container)
        review_service = imports.PersonaReviewService(container)

        # 与独立 WebUI 人格学习页同源：当前人格取 group_id，备份取全部群组最近 limit 条，
        # 待审人格更新取首屏 10 条、最近已审查 5 条（/api/persona_updates、/reviewed）。
        personas, current, default_persona, backups, pending, reviewed = await asyncio.gather(
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
                lambda: backup_service.list_backups(limit=limit),
                errors,
                default={"backups": [], "total": 0, "available": False},
            ),
            self._safe_section(
                "pending",
                lambda: review_service.get_pending_persona_updates(limit=pending_limit),
                errors,
                default={"updates": [], "total": 0, "success": True},
            ),
            self._safe_section(
                "reviewed",
                lambda: review_service.get_reviewed_persona_updates(reviewed_limit, 0, None),
                errors,
                default={"updates": [], "total": 0, "success": True},
            ),
        )
        return {
            "group_id": group_id,
            "personas": personas,
            "current": current,
            "default": default_persona,
            "backups": backups,
            "pending": pending,
            "reviewed": reviewed,
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

        # 与独立 WebUI /api/metrics 同口径的顶层字段（同一组共享函数计算），
        # 首页 / 总览 / 运行监控 / AI 巡检直接读取，避免两端读数分叉。
        message_totals = message_stats if isinstance(message_stats, dict) else {}
        total_messages = self._as_int(message_totals.get("total_messages"), 0)
        filtered_messages = self._as_int(message_totals.get("filtered_messages"), 0)
        learning_efficiency, learning_dimensions = await self._safe_section(
            "learning_efficiency",
            lambda: imports.compute_learning_efficiency(db, total_messages, filtered_messages),
            errors,
            default=(0, {}),
        )
        llm_summary = imports.summarize_llm_call_statistics(llm_stats, provider_info)
        system = self._system_metrics()

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
            "system": system,
            "total_messages_collected": total_messages,
            "filtered_messages": filtered_messages,
            "learning_efficiency": learning_efficiency,
            "learning_dimensions": learning_dimensions,
            **llm_summary,
            "system_metrics": system,
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
        llm_adapter = getattr(container, "llm_adapter", None)
        llm_call_statistics: dict[str, Any] = {}
        llm_provider_info: dict[str, Any] = {}
        if llm_adapter and hasattr(llm_adapter, "get_call_statistics"):
            try:
                llm_call_statistics = llm_adapter.get_call_statistics() or {}
            except Exception as exc:
                errors["llm_stats"] = str(exc)
        if llm_adapter and hasattr(llm_adapter, "get_provider_info"):
            try:
                llm_provider_info = llm_adapter.get_provider_info() or {}
            except Exception as exc:
                errors["provider_info"] = str(exc)
        return {
            "health": health,
            "functions": functions,
            "llm": {
                "call_statistics": llm_call_statistics,
                "provider_info": llm_provider_info,
            },
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
        return await service.get_status()

    async def _load_data_statistics(self) -> dict[str, Any]:
        service = self._imports().DataManagementService(self._container())
        return await service.get_data_statistics()

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
        # 与独立 WebUI /api/style_learning/content_text 共用同一服务（同一份四分类数据）
        service = self._imports().LearningContentService(self._container())
        return await service.get_content_text()

    async def _get_learning_batches(
        self,
        *,
        page: int,
        page_size: int,
        raise_errors: bool = False,
    ) -> dict[str, Any]:
        # 与独立 WebUI /api/batches 共用同一服务；raise_errors=False 时读取失败返回空页
        page = max(1, page)
        page_size = max(1, min(page_size or 20, 100))
        try:
            service = self._imports().LearningContentService(self._container())
            return await service.list_batches(page, page_size)
        except Exception as exc:
            if raise_errors:
                raise
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

    async def _update_style_review(self, body: Mapping[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        # 与独立 WebUI PUT /api/style_learning/reviews/<id> 共用同一服务方法
        try:
            service = self._imports().LearningService(self._container())
            return await service.update_style_learning_review(self._body_int(body, "id"), dict(body))
        except Exception as exc:
            logger.error(f"[PluginPageAPI] update style review failed: {exc}", exc_info=True)
            return False, str(exc), {}

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
            return {"success": False, "error": "依赖安装只能在 WebUI 手动确认后触发"}

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
                    is_trace_enabled,
                )
            except ImportError:
                from services.monitoring.instrumentation import (
                    _func_counters,
                    _func_error_counters,
                    _func_histograms,
                    is_debug_mode,
                    is_trace_enabled,
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
                "trace_enabled": is_trace_enabled(),
                "functions": functions[:80],
                "timestamp": time.time(),
            }
        except Exception as exc:
            return {"debug_mode": False, "trace_enabled": False, "functions": [], "error": str(exc), "timestamp": time.time()}

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
        container = self._imports().get_container()
        if getattr(container, "bound", False):
            return container

        # 容器未被绑定（独立 WebUI 未启动、面板先于 on_load 被打开等），补绑一次
        now = time.monotonic()
        if now - self._container_bind_last_try >= self._CONTAINER_RETRY_INTERVAL:
            self._container_bind_last_try = now
            self._rebind_container(container)
        return container

    def _rebind_container(self, container: Any) -> None:
        """容器未绑定时从当前插件实例补绑一次。

        issue #283：面板页在插件 ``__init__`` 就已注册，但容器过去只在独立 WebUI
        服务器启动路径里绑定；WebUI 未启用、依赖缺失或端口占用时任一环节被跳过，
        页面所有 section 就会报「数据库管理器未初始化 / Plugin config not initialized」。
        """
        try:
            if container.bind_plugin(self.plugin):
                if not getattr(container, "perf_collector", None):
                    container.perf_collector = getattr(self.plugin, "_perf_tracker", None)
                logger.info("[PluginPageAPI] 已从插件实例补绑 WebUI 服务容器")
            else:
                logger.warning("[PluginPageAPI] 插件服务尚未就绪，页面数据可能不完整")
        except Exception as exc:
            logger.warning(f"[PluginPageAPI] 补绑 WebUI 服务容器失败: {exc}", exc_info=True)

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
            from ..webui.services.bug_report_service import BugReportService
            from ..webui.services.config_service import ConfigService
            from ..webui.services.data_management_service import DataManagementService
            from ..webui.services.emotion_board_service import EmotionBoardService
            from ..webui.services.graph_service import GraphService
            from ..webui.services.graph_share_service import GraphShareService
            from ..webui.services.integration_service import IntegrationService
            from ..webui.services.jargon_service import JargonService
            from ..webui.services.learning_content_service import LearningContentService
            from ..webui.services.learning_service import LearningService
            from ..webui.services.metrics_service import (
                MetricsService,
                compute_learning_efficiency,
                summarize_llm_call_statistics,
            )
            from ..webui.services.persona_backup_service import PersonaBackupService
            from ..webui.services.persona_review_service import PersonaReviewService
            from ..webui.services.persona_service import PersonaService
            from ..webui.services.social_service import SocialService
            from ..services.integration.maibot_learning_importer import MaiBotLearningImporter
            from ..services.integration.qq_chat_history_importer import QQChatHistoryImporter
            from ..services.integration.worldbook_importer import WorldBookImporter
            from ..services.shadow_mode import ShadowModeService
        except ImportError:
            from webui.blueprints.config import (
                DEPENDENCY_TIERS,
                MANUAL_DEPENDENCY_INSTALL_SOURCE,
                PIP_MIRROR_SOURCES,
            )
            from webui.dependencies import get_container
            from webui.services.bug_report_service import BugReportService
            from webui.services.config_service import ConfigService
            from webui.services.data_management_service import DataManagementService
            from webui.services.emotion_board_service import EmotionBoardService
            from webui.services.graph_service import GraphService
            from webui.services.graph_share_service import GraphShareService
            from webui.services.integration_service import IntegrationService
            from webui.services.jargon_service import JargonService
            from webui.services.learning_content_service import LearningContentService
            from webui.services.learning_service import LearningService
            from webui.services.metrics_service import (
                MetricsService,
                compute_learning_efficiency,
                summarize_llm_call_statistics,
            )
            from webui.services.persona_backup_service import PersonaBackupService
            from webui.services.persona_review_service import PersonaReviewService
            from webui.services.persona_service import PersonaService
            from webui.services.social_service import SocialService
            from services.integration.maibot_learning_importer import MaiBotLearningImporter
            from services.integration.qq_chat_history_importer import QQChatHistoryImporter
            from services.integration.worldbook_importer import WorldBookImporter
            from services.shadow_mode import ShadowModeService

        imports.get_container = get_container
        imports.BugReportService = BugReportService
        imports.ConfigService = ConfigService
        imports.DataManagementService = DataManagementService
        imports.EmotionBoardService = EmotionBoardService
        imports.GraphService = GraphService
        imports.GraphShareService = GraphShareService
        imports.IntegrationService = IntegrationService
        imports.JargonService = JargonService
        imports.LearningService = LearningService
        imports.LearningContentService = LearningContentService
        imports.MetricsService = MetricsService
        imports.compute_learning_efficiency = compute_learning_efficiency
        imports.summarize_llm_call_statistics = summarize_llm_call_statistics
        imports.PersonaBackupService = PersonaBackupService
        imports.PersonaReviewService = PersonaReviewService
        imports.PersonaService = PersonaService
        imports.SocialService = SocialService
        imports.MaiBotLearningImporter = MaiBotLearningImporter
        imports.QQChatHistoryImporter = QQChatHistoryImporter
        imports.WorldBookImporter = WorldBookImporter
        imports.ShadowModeService = ShadowModeService
        imports.DEPENDENCY_TIERS = DEPENDENCY_TIERS
        imports.MANUAL_DEPENDENCY_INSTALL_SOURCE = MANUAL_DEPENDENCY_INSTALL_SOURCE
        imports.PIP_MIRROR_SOURCES = PIP_MIRROR_SOURCES
        return imports

    @staticmethod
    async def _body() -> dict[str, Any]:
        try:
            # AstrBot v4.26+ 桥接已迁至 FastAPI，官方请求代理见 astrbot.api.web
            from astrbot.api.web import request as plugin_request

            data = await plugin_request.json(default=None)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _query() -> Any:
        try:
            from astrbot.api.web import request as plugin_request

            return plugin_request.query
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
    def _body_bool(body: Mapping[str, Any], key: str, default: bool) -> bool:
        value = body.get(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

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
