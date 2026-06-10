"""FastMCP server for self-learning data and review workflows."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .runtime import (
    McpRuntimeSettings,
    SelfLearningMcpRuntime,
    clamp,
    fail,
    mask_config,
    normalize_action,
    normalize_status,
    ok,
    paginate,
)


@dataclass(slots=True)
class McpServerSettings(McpRuntimeSettings):
    """CLI and transport settings for the self-learning MCP server."""

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    debug: bool = False
    sse_path: str = "/sse"
    message_path: str = "/messages/"
    streamable_http_path: str = "/mcp"
    json_response: bool = False
    stateless_http: bool = False


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE_SAFE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def create_mcp(settings: McpServerSettings | None = None) -> FastMCP:
    """Create the self-learning MCP server."""
    settings = settings or McpServerSettings()
    runtime = SelfLearningMcpRuntime(settings)

    @asynccontextmanager
    async def lifespan(_: FastMCP):
        try:
            yield {"runtime": runtime}
        finally:
            await runtime.close()

    mcp = FastMCP(
        "self_learning_mcp",
        instructions=(
            "Inspect and manage AstrBot self-learning plugin data. "
            "Use read-only tools for analytics and review tools for explicit approvals."
        ),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.upper(),
        debug=settings.debug,
        sse_path=settings.sse_path,
        message_path=settings.message_path,
        streamable_http_path=settings.streamable_http_path,
        json_response=settings.json_response,
        stateless_http=settings.stateless_http,
        lifespan=lifespan,
    )

    register_tools(mcp, runtime)
    return mcp


def register_tools(mcp: FastMCP, runtime: SelfLearningMcpRuntime) -> None:
    """Register self-learning MCP tools."""

    @mcp.tool(
        name="self_learning_health",
        title="Self-Learning Health",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_health() -> str:
        """Return MCP runtime, database, and storage status."""
        return ok(runtime.status())

    @mcp.tool(
        name="self_learning_get_config",
        title="Get Self-Learning Config",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_get_config(include_sensitive: bool = False) -> str:
        """Return the loaded plugin configuration, masking secrets by default."""
        config = runtime.config.to_dict()
        return ok(config if include_sensitive else mask_config(config))

    @mcp.tool(
        name="self_learning_get_data_statistics",
        title="Get Data Statistics",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_get_data_statistics() -> str:
        """Return row counts for the plugin's main data domains."""
        return await runtime.call(lambda db: db.get_data_statistics())

    @mcp.tool(
        name="self_learning_get_metrics",
        title="Get Self-Learning Metrics",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_get_metrics(group_id: Optional[str] = None) -> str:
        """Return detailed message and learning metrics, optionally scoped to a group."""

        async def operation(db):
            return {
                "group_statistics": await db.get_group_statistics(group_id),
                "detailed_metrics": await db.get_detailed_metrics(group_id),
                "message_statistics": await db.get_message_statistics(group_id),
                "jargon_statistics": await db.get_jargon_statistics(group_id),
                "style_learning_statistics": await db.get_style_learning_statistics(),
            }

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_get_trends",
        title="Get Learning Trends",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_get_trends() -> str:
        """Return recent message and learning trend data."""
        return await runtime.call(lambda db: db.get_trends_data())

    @mcp.tool(
        name="self_learning_list_groups",
        title="List Learned Groups",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_list_groups(limit: int = 50, offset: int = 0) -> str:
        """List groups that have captured messages or social relation data."""
        limit = clamp(limit, minimum=1, maximum=200)
        offset = clamp(offset, minimum=0, maximum=100000)

        async def operation(db):
            groups = await db.get_groups_for_social_analysis()
            return paginate(
                groups[offset : offset + limit],
                total=len(groups),
                limit=limit,
                offset=offset,
            )

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_get_recent_messages",
        title="Get Recent Messages",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_get_recent_messages(
        group_id: str,
        kind: str = "raw",
        limit: int = 50,
    ) -> str:
        """Return recent raw, filtered, or bot messages for a group."""
        limit = clamp(limit, minimum=1, maximum=500)
        normalized = str(kind or "raw").strip().lower()
        if normalized not in {"raw", "filtered", "bot"}:
            return fail("kind must be one of: raw, filtered, bot", error_type="ValueError")

        async def operation(db):
            if normalized == "raw":
                return await db.get_recent_raw_messages(group_id, limit)
            if normalized == "filtered":
                return await db.get_recent_filtered_messages(group_id, limit)
            responses = await db.get_recent_bot_responses(group_id, limit)
            return [
                {"group_id": group_id, "message": message}
                for message in responses
            ]

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_get_jargon_stats",
        title="Get Jargon Statistics",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_get_jargon_stats(group_id: Optional[str] = None) -> str:
        """Return jargon learning statistics, optionally scoped to a group."""
        return await runtime.call(lambda db: db.get_jargon_statistics(group_id))

    @mcp.tool(
        name="self_learning_list_jargon",
        title="List Jargon",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_list_jargon(
        group_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        confirmed: Optional[bool] = None,
        pending_only: bool = False,
        global_only: bool = False,
        local_only: bool = False,
    ) -> str:
        """List jargon candidates or confirmed jargon with pagination."""
        limit = clamp(limit, minimum=1, maximum=200)
        offset = clamp(offset, minimum=0, maximum=100000)

        async def operation(db):
            total = await db.get_jargon_count(
                chat_id=group_id,
                only_confirmed=confirmed,
                pending_only=pending_only,
                global_only=global_only,
                local_only=local_only,
            )
            items = await db.get_recent_jargon_list(
                chat_id=group_id,
                limit=limit,
                offset=offset,
                only_confirmed=confirmed,
                pending_only=pending_only,
                global_only=global_only,
                local_only=local_only,
            )
            return paginate(items, total=total, limit=limit, offset=offset)

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_search_jargon",
        title="Search Jargon",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_search_jargon(
        keyword: str,
        group_id: Optional[str] = None,
        limit: int = 50,
        confirmed_only: bool = False,
        pending_only: bool = False,
        global_only: bool = False,
        local_only: bool = False,
    ) -> str:
        """Search jargon by keyword, optionally scoped to a group."""
        limit = clamp(limit, minimum=1, maximum=200)

        async def operation(db):
            items = await db.search_jargon(
                keyword=keyword,
                chat_id=group_id,
                confirmed_only=confirmed_only,
                pending_only=pending_only,
                global_only=global_only,
                local_only=local_only,
                limit=limit,
            )
            return {"items": items, "count": len(items), "limit": limit}

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_review_jargon",
        title="Review Jargon",
        annotations=WRITE_SAFE,
        structured_output=False,
    )
    async def self_learning_review_jargon(
        jargon_id: int,
        action: str,
        meaning: Optional[str] = None,
    ) -> str:
        """Approve or reject a jargon candidate."""
        try:
            status = normalize_action(action)
        except ValueError as exc:
            return fail(str(exc), error_type="ValueError")

        async def operation(db):
            current = await db.get_jargon_by_id(jargon_id)
            if not current:
                raise ValueError(f"jargon {jargon_id} does not exist")

            payload: dict[str, Any] = {
                "id": jargon_id,
                "is_jargon": status == "approved",
                "is_complete": True,
            }
            if meaning is not None:
                payload["meaning"] = meaning

            updated = await db.update_jargon(payload)
            if not updated:
                raise RuntimeError(f"failed to update jargon {jargon_id}")
            return {
                "jargon_id": jargon_id,
                "status": status,
                "jargon": await db.get_jargon_by_id(jargon_id),
            }

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_update_jargon",
        title="Update Jargon",
        annotations=WRITE_SAFE,
        structured_output=False,
    )
    async def self_learning_update_jargon(
        jargon_id: int,
        content: Optional[str] = None,
        meaning: Optional[str] = None,
        is_global: Optional[bool] = None,
    ) -> str:
        """Update jargon content, meaning, or global sharing status."""

        async def operation(db):
            current = await db.get_jargon_by_id(jargon_id)
            if not current:
                raise ValueError(f"jargon {jargon_id} does not exist")

            payload: dict[str, Any] = {"id": jargon_id}
            if content is not None:
                payload["content"] = content
            if meaning is not None:
                payload["meaning"] = meaning

            changed = False
            if len(payload) > 1:
                changed = await db.update_jargon(payload)
                if not changed:
                    raise RuntimeError(f"failed to update jargon {jargon_id}")

            if is_global is not None:
                changed = await db.set_jargon_global(jargon_id, is_global) or changed

            return {
                "changed": changed,
                "jargon": await db.get_jargon_by_id(jargon_id),
            }

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_sync_global_jargon",
        title="Sync Global Jargon",
        annotations=WRITE_SAFE,
        structured_output=False,
    )
    async def self_learning_sync_global_jargon(target_group_id: str) -> str:
        """Copy global jargon entries to a target group."""
        return await runtime.call(
            lambda db: db.sync_global_jargon_to_group(target_group_id)
        )

    @mcp.tool(
        name="self_learning_list_style_reviews",
        title="List Style Reviews",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_list_style_reviews(
        status: str = "pending",
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """List style learning reviews by status: pending, reviewed, approved, rejected, or all."""
        limit = clamp(limit, minimum=1, maximum=200)
        offset = clamp(offset, minimum=0, maximum=100000)
        normalized = normalize_status(status)

        async def operation(db):
            if normalized == "pending":
                items = await db.get_pending_style_reviews(limit=limit, offset=offset)
                return paginate(items, total=None, limit=limit, offset=offset)
            if normalized in {"approved", "rejected"}:
                items = await db.get_reviewed_style_learning_updates(
                    limit=limit,
                    offset=offset,
                    status_filter=normalized,
                )
                return paginate(items, total=None, limit=limit, offset=offset)
            if normalized == "reviewed":
                items = await db.get_reviewed_style_learning_updates(
                    limit=limit,
                    offset=offset,
                )
                return paginate(items, total=None, limit=limit, offset=offset)
            if normalized == "all":
                pending = await db.get_pending_style_reviews(limit=limit, offset=0)
                reviewed = await db.get_reviewed_style_learning_updates(
                    limit=limit,
                    offset=0,
                )
                items = _sort_reviews([*pending, *reviewed])[offset : offset + limit]
                return paginate(items, total=None, limit=limit, offset=offset)
            raise ValueError(
                "status must be pending, reviewed, approved, rejected, or all"
            )

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_review_style",
        title="Review Style Learning",
        annotations=WRITE_SAFE,
        structured_output=False,
    )
    async def self_learning_review_style(
        review_id: int,
        action: str,
        comment: str = "",
        group_id: Optional[str] = None,
    ) -> str:
        """Approve or reject a style learning review without applying AstrBot persona changes."""
        try:
            status = normalize_action(action)
        except ValueError as exc:
            return fail(str(exc), error_type="ValueError")

        async def operation(db):
            changed = await db.update_style_review_status(
                review_id,
                status,
                reviewer_comment=comment,
                group_id=group_id,
            )
            if not changed:
                raise RuntimeError(f"failed to update style review {review_id}")
            return {"review_id": review_id, "status": status}

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_list_persona_reviews",
        title="List Persona Reviews",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_list_persona_reviews(
        status: str = "pending",
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """List persona learning reviews by status: pending, reviewed, approved, rejected, or all."""
        limit = clamp(limit, minimum=1, maximum=200)
        offset = clamp(offset, minimum=0, maximum=100000)
        normalized = normalize_status(status)

        async def operation(db):
            if normalized == "pending":
                items = await db.get_pending_persona_learning_reviews(limit, offset)
                return paginate(items, total=None, limit=limit, offset=offset)
            if normalized in {"approved", "rejected"}:
                items = await db.get_reviewed_persona_learning_updates(
                    limit=limit,
                    offset=offset,
                    status_filter=normalized,
                )
                return paginate(items, total=None, limit=limit, offset=offset)
            if normalized == "reviewed":
                items = await db.get_reviewed_persona_learning_updates(
                    limit=limit,
                    offset=offset,
                )
                return paginate(items, total=None, limit=limit, offset=offset)
            if normalized == "all":
                pending = await db.get_pending_persona_learning_reviews(limit, 0)
                reviewed = await db.get_reviewed_persona_learning_updates(limit=limit, offset=0)
                items = _sort_reviews([*pending, *reviewed])[offset : offset + limit]
                return paginate(items, total=None, limit=limit, offset=offset)
            raise ValueError(
                "status must be pending, reviewed, approved, rejected, or all"
            )

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_review_persona",
        title="Review Persona Learning",
        annotations=WRITE_SAFE,
        structured_output=False,
    )
    async def self_learning_review_persona(
        review_id: int,
        action: str,
        comment: str = "",
        modified_content: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> str:
        """Approve or reject a persona learning review without applying AstrBot persona changes."""
        try:
            status = normalize_action(action)
        except ValueError as exc:
            return fail(str(exc), error_type="ValueError")

        async def operation(db):
            changed = await db.update_persona_learning_review_status(
                review_id,
                status,
                comment=comment,
                modified_content=modified_content,
                group_id=group_id,
            )
            if not changed:
                raise RuntimeError(f"failed to update persona review {review_id}")
            return {"review_id": review_id, "status": status}

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_get_learning_summary",
        title="Get Learning Summary",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_get_learning_summary(
        group_id: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """Return recent learning batches, sessions, style stats, and approved few-shots."""
        limit = clamp(limit, minimum=1, maximum=100)

        async def operation(db):
            return {
                "style_statistics": await db.get_style_learning_statistics(),
                "recent_batches": await db.get_recent_learning_batches(limit=limit),
                "recent_sessions": await db.get_recent_learning_sessions(days=7),
                "approved_few_shots": (
                    await db.get_approved_few_shots(group_id, limit=min(limit, 20))
                    if group_id
                    else []
                ),
                "learning_batch_history": (
                    await db.get_learning_batch_history(group_id, limit=limit)
                    if group_id
                    else []
                ),
            }

        return await runtime.call(operation)

    @mcp.tool(
        name="self_learning_get_social_relations",
        title="Get Social Relations",
        annotations=READ_ONLY,
        structured_output=False,
    )
    async def self_learning_get_social_relations(
        group_id: str,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> str:
        """Return social relations for a group or for a single user in that group."""
        limit = clamp(limit, minimum=1, maximum=500)

        async def operation(db):
            if user_id:
                data = await db.get_user_social_relations(group_id, user_id)
                relations = data.get("relations", [])
                data["relations"] = relations[:limit]
                data["count"] = len(data["relations"])
                return data
            relations = await db.get_social_relations_by_group(group_id)
            return {"group_id": group_id, "count": min(len(relations), limit), "relations": relations[:limit]}

        return await runtime.call(operation)


def _sort_reviews(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> float:
        value = item.get("review_time") or item.get("timestamp") or item.get("created_at") or 0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    return sorted(items, key=key, reverse=True)
