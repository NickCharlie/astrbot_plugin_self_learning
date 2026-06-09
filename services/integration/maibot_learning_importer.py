"""MaiBot learning data export/import bridge.

This module intentionally does not import MaiBot runtime code.  It reads
MaiBot SQLite/JSON exports, normalizes the learning resources, and writes them
through this plugin's existing learning tables/facades.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from astrbot.api import logger
from sqlalchemy import and_, select

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None


MAIBOT_EXPORT_VERSION = 1
DEFAULT_MAIBOT_DB_CANDIDATES = (
    "data/MaiBot.db",
    "data/maibot.db",
    "data/database.db",
    "data/maibot.sqlite",
    "MaiBot.db",
    "maibot.db",
)
DEFAULT_MEMORIX_DB_CANDIDATES = (
    "data/a-memorix/metadata/metadata.db",
    "data/plugins/a-dawn.a-memorix/metadata/metadata.db",
    "data/A_memorix/metadata.db",
    "data/A_memorix/metadata/metadata.db",
    "data/metadata.db",
    "src/A_memorix/data/metadata/metadata.db",
    "src/A_memorix/data/metadata.db",
    "src/A_memorix/metadata/metadata.db",
    "metadata.db",
)


@dataclass
class MaiBotSession:
    session_id: str
    group_id: str
    user_id: str = ""
    platform: str = ""
    display_name: str = ""
    scope: str = ""


@dataclass
class MaiBotExpression:
    source_id: str
    situation: str
    style: str
    content_list: list[str] = field(default_factory=list)
    count: int = 1
    session_id: str = ""
    group_id: str = "global"
    checked: bool = False
    modified_by: str = ""
    created_at: float = 0.0
    last_active_at: float = 0.0


@dataclass
class MaiBotJargon:
    source_id: str
    content: str
    raw_content: list[Any] = field(default_factory=list)
    meaning: str = ""
    session_id_counts: dict[str, int] = field(default_factory=dict)
    group_ids: list[str] = field(default_factory=list)
    count: int = 1
    is_jargon: Optional[bool] = None
    is_complete: bool = False
    is_global: bool = False
    created_by: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class MaiBotMemoryParagraph:
    source_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    knowledge_type: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class MaiBotLearningPackage:
    version: int = MAIBOT_EXPORT_VERSION
    source: str = "maibot"
    exported_at: float = field(default_factory=time.time)
    source_paths: dict[str, str] = field(default_factory=dict)
    sessions: list[MaiBotSession] = field(default_factory=list)
    expressions: list[MaiBotExpression] = field(default_factory=list)
    jargons: list[MaiBotJargon] = field(default_factory=list)
    memories: list[MaiBotMemoryParagraph] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source": self.source,
            "exported_at": self.exported_at,
            "source_paths": self.source_paths,
            "sessions": [asdict(item) for item in self.sessions],
            "expressions": [asdict(item) for item in self.expressions],
            "jargons": [asdict(item) for item in self.jargons],
            "memories": [asdict(item) for item in self.memories],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MaiBotLearningPackage":
        return cls(
            version=int(payload.get("version") or MAIBOT_EXPORT_VERSION),
            source=str(payload.get("source") or "maibot"),
            exported_at=_to_timestamp(payload.get("exported_at"), default=time.time()),
            source_paths=dict(payload.get("source_paths") or {}),
            sessions=[
                MaiBotSession(**_pick_keys(item, MaiBotSession))
                for item in _as_list(payload.get("sessions"))
                if isinstance(item, Mapping)
            ],
            expressions=[
                MaiBotExpression(**_pick_keys(item, MaiBotExpression))
                for item in _as_list(payload.get("expressions"))
                if isinstance(item, Mapping)
            ],
            jargons=[
                MaiBotJargon(**_pick_keys(item, MaiBotJargon))
                for item in _as_list(payload.get("jargons"))
                if isinstance(item, Mapping)
            ],
            memories=[
                MaiBotMemoryParagraph(**_pick_keys(item, MaiBotMemoryParagraph))
                for item in _as_list(payload.get("memories"))
                if isinstance(item, Mapping)
            ],
        )


class MaiBotLearningImporter:
    """Read MaiBot learning resources and import them into Self Learning."""

    def __init__(self, database_manager: Any = None) -> None:
        self.database_manager = database_manager

    def preview(
        self,
        *,
        maibot_root: str | Path | None = None,
        db_path: str | Path | None = None,
        memorix_db_path: str | Path | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        package = self.load_package(
            maibot_root=maibot_root,
            db_path=db_path,
            memorix_db_path=memorix_db_path,
            payload=payload,
        )
        return self.package_summary(package)

    def load_package(
        self,
        *,
        maibot_root: str | Path | None = None,
        db_path: str | Path | None = None,
        memorix_db_path: str | Path | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> MaiBotLearningPackage:
        if payload:
            return MaiBotLearningPackage.from_dict(payload)

        resolved_db = self._resolve_db_path(
            explicit=db_path,
            root=maibot_root,
            candidates=DEFAULT_MAIBOT_DB_CANDIDATES,
        )
        resolved_memorix = self._resolve_db_path(
            explicit=memorix_db_path,
            root=maibot_root,
            candidates=DEFAULT_MEMORIX_DB_CANDIDATES,
            required=False,
        )
        if not resolved_memorix:
            resolved_memorix = self._resolve_memorix_db_from_config(maibot_root)
        if not resolved_db:
            raise FileNotFoundError("未找到 MaiBot 主数据库，请传入 db_path 或 maibot_root")

        package = MaiBotLearningPackage(
            source_paths={"maibot_db": str(resolved_db)},
        )
        sessions = self._read_sessions(resolved_db)
        session_map = {item.session_id: item for item in sessions if item.session_id}
        package.sessions = sessions
        package.expressions = self._read_expressions(resolved_db, session_map)
        package.jargons = self._read_jargons(resolved_db, session_map)
        package.memories = self._read_chat_history_memories(resolved_db, session_map)

        if resolved_memorix:
            package.source_paths["memorix_db"] = str(resolved_memorix)
            package.memories.extend(self._read_memories(resolved_memorix))
        return package

    async def import_package(
        self,
        package: MaiBotLearningPackage,
        *,
        default_group_id: str = "global",
        import_expressions: bool = True,
        import_jargons: bool = True,
        import_memories: bool = True,
        approve_checked_expressions: bool = True,
    ) -> dict[str, Any]:
        if not self.database_manager:
            raise RuntimeError("数据库管理器不可用，无法导入 MaiBot 学习数据")

        result = {
            "success": True,
            "expressions_imported": 0,
            "expression_patterns_imported": 0,
            "jargons_imported": 0,
            "memory_reviews_imported": 0,
            "skipped": 0,
            "errors": [],
        }

        if import_expressions:
            await self._import_expressions(
                package,
                result,
                default_group_id=default_group_id,
                approve_checked=approve_checked_expressions,
            )
        if import_jargons:
            await self._import_jargons(package, result, default_group_id=default_group_id)
        if import_memories:
            await self._import_memories(package, result, default_group_id=default_group_id)

        result["success"] = not result["errors"]
        return result

    async def import_from_source(self, **kwargs: Any) -> dict[str, Any]:
        package = self.load_package(
            maibot_root=kwargs.get("maibot_root"),
            db_path=kwargs.get("db_path"),
            memorix_db_path=kwargs.get("memorix_db_path"),
            payload=kwargs.get("payload"),
        )
        return await self.import_package(
            package,
            default_group_id=str(kwargs.get("default_group_id") or "global"),
            import_expressions=bool(kwargs.get("import_expressions", True)),
            import_jargons=bool(kwargs.get("import_jargons", True)),
            import_memories=bool(kwargs.get("import_memories", True)),
            approve_checked_expressions=bool(kwargs.get("approve_checked_expressions", True)),
        )

    def package_summary(self, package: MaiBotLearningPackage) -> dict[str, Any]:
        session_groups = sorted({item.group_id for item in package.sessions if item.group_id})
        expression_groups = sorted({item.group_id for item in package.expressions if item.group_id})
        jargon_groups = sorted({gid for item in package.jargons for gid in item.group_ids if gid})
        return {
            "version": package.version,
            "source": package.source,
            "source_paths": package.source_paths,
            "counts": {
                "sessions": len(package.sessions),
                "expressions": len(package.expressions),
                "checked_expressions": sum(1 for item in package.expressions if item.checked),
                "jargons": len(package.jargons),
                "confirmed_jargons": sum(1 for item in package.jargons if item.is_jargon is True),
                "memories": len(package.memories),
            },
            "groups": sorted(set(session_groups + expression_groups + jargon_groups))[:50],
            "samples": {
                "expressions": [asdict(item) for item in package.expressions[:5]],
                "jargons": [asdict(item) for item in package.jargons[:5]],
                "memories": [asdict(item) for item in package.memories[:3]],
            },
        }

    def export_json(self, **kwargs: Any) -> dict[str, Any]:
        return self.load_package(**kwargs).to_dict()

    async def _import_expressions(
        self,
        package: MaiBotLearningPackage,
        result: dict[str, Any],
        *,
        default_group_id: str,
        approve_checked: bool,
    ) -> None:
        try:
            from ...models.orm.expression import ExpressionPattern
            from ...models.orm.learning import StyleLearningReview
        except ImportError:
            from models.orm.expression import ExpressionPattern
            from models.orm.learning import StyleLearningReview

        now = time.time()
        async with self.database_manager.get_session() as session:
            for item in package.expressions:
                if not item.situation or not item.style:
                    result["skipped"] += 1
                    continue
                group_id = item.group_id or default_group_id
                source_id = str(item.source_id or "")

                exists_stmt = select(StyleLearningReview).where(
                    StyleLearningReview.group_id == group_id,
                    StyleLearningReview.metadata_.like(f'%"maibot_source_id": "{source_id}"%'),
                )
                if source_id and (await session.execute(exists_stmt)).scalar_one_or_none():
                    result["skipped"] += 1
                    continue

                pattern = {
                    "situation": item.situation,
                    "expression": item.style,
                    "source": "maibot",
                    "count": item.count,
                    "content_list": item.content_list,
                }
                status = "approved" if approve_checked and item.checked else "pending"
                review = StyleLearningReview(
                    type="maibot_expression",
                    group_id=group_id,
                    timestamp=item.last_active_at or item.created_at or now,
                    learned_patterns=json.dumps([pattern], ensure_ascii=False),
                    few_shots_content=self._format_expression_few_shot(item),
                    status=status,
                    description="从 MaiBot 表达方式学习数据导入",
                    reviewer_comment="MaiBot 已确认表达自动批准" if status == "approved" else None,
                    review_time=now if status == "approved" else None,
                    metadata_=json.dumps(
                        {
                            "source": "maibot",
                            "maibot_source_id": source_id,
                            "maibot_session_id": item.session_id,
                            "checked": item.checked,
                            "modified_by": item.modified_by,
                            "content_list": item.content_list,
                            "imported_at": now,
                        },
                        ensure_ascii=False,
                    ),
                )
                session.add(review)
                result["expressions_imported"] += 1

                if status == "approved":
                    duplicate_stmt = select(ExpressionPattern).where(
                        and_(
                            ExpressionPattern.group_id == group_id,
                            ExpressionPattern.situation == item.situation,
                            ExpressionPattern.expression == item.style,
                        )
                    )
                    existing = (await session.execute(duplicate_stmt)).scalar_one_or_none()
                    if existing:
                        existing.weight = max(float(existing.weight or 1.0), float(item.count or 1))
                        existing.last_active_time = now
                    else:
                        session.add(
                            ExpressionPattern(
                                group_id=group_id,
                                situation=item.situation,
                                expression=item.style,
                                weight=max(1.0, float(item.count or 1)),
                                last_active_time=item.last_active_at or now,
                                create_time=item.created_at or now,
                            )
                        )
                        result["expression_patterns_imported"] += 1
            await session.commit()

    async def _import_jargons(
        self,
        package: MaiBotLearningPackage,
        result: dict[str, Any],
        *,
        default_group_id: str,
    ) -> None:
        for item in package.jargons:
            groups = item.group_ids or [default_group_id]
            for group_id in groups:
                try:
                    raw_content = {
                        "source": "maibot",
                        "raw_context": item.raw_content,
                        "session_id_counts": item.session_id_counts,
                        "source_id": item.source_id,
                    }
                    jargon_id = await self.database_manager.save_or_update_jargon(
                        group_id or default_group_id,
                        item.content,
                        {
                            "raw_content": json.dumps(raw_content, ensure_ascii=False),
                            "meaning": item.meaning or None,
                            "is_jargon": item.is_jargon,
                            "count": max(1, int(item.count or 1)),
                            "last_inference_count": max(0, int(item.count or 0)),
                            "is_complete": bool(item.is_complete or item.meaning),
                            "is_global": bool(item.is_global),
                        },
                    )
                    if jargon_id:
                        result["jargons_imported"] += 1
                    else:
                        result["skipped"] += 1
                except Exception as exc:
                    logger.error(f"[MaiBotImport] 导入黑话失败: {item.content}: {exc}", exc_info=True)
                    result["errors"].append(f"黑话 {item.content}: {exc}")

    async def _import_memories(
        self,
        package: MaiBotLearningPackage,
        result: dict[str, Any],
        *,
        default_group_id: str,
    ) -> None:
        if not package.memories:
            return
        try:
            from ...models.orm.learning import PersonaLearningReview
        except ImportError:
            from models.orm.learning import PersonaLearningReview

        now = time.time()
        async with self.database_manager.get_session() as session:
            for item in package.memories:
                if not item.content:
                    result["skipped"] += 1
                    continue
                source_id = str(item.source_id or "")
                exists_stmt = select(PersonaLearningReview).where(
                    PersonaLearningReview.update_type == "maibot_memory",
                    PersonaLearningReview.metadata_.like(f'%"maibot_source_id": "{source_id}"%'),
                )
                if source_id and (await session.execute(exists_stmt)).scalar_one_or_none():
                    result["skipped"] += 1
                    continue
                group_id = _metadata_group_id(item.metadata) or default_group_id
                session.add(
                    PersonaLearningReview(
                        timestamp=item.updated_at or item.created_at or now,
                        group_id=group_id,
                        update_type="maibot_memory",
                        original_content="",
                        new_content=item.content,
                        proposed_content=item.content,
                        confidence_score=0.72,
                        reason="从 MaiBot A_memorix 记忆段落导入，等待确认后可沉淀到人格/记忆上下文。",
                        status="pending",
                        metadata_=json.dumps(
                            {
                                "source": "maibot",
                                "maibot_source_id": source_id,
                                "maibot_memory_source": item.source,
                                "knowledge_type": item.knowledge_type,
                                "metadata": item.metadata,
                                "imported_at": now,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
                result["memory_reviews_imported"] += 1
            await session.commit()

    @staticmethod
    def _resolve_db_path(
        *,
        explicit: str | Path | None,
        root: str | Path | None,
        candidates: Iterable[str],
        required: bool = True,
    ) -> Optional[Path]:
        if explicit:
            path = Path(explicit).expanduser()
            if path.is_file():
                return path.resolve()
            if required:
                raise FileNotFoundError(f"数据库文件不存在: {path}")
            return None
        if not root:
            return None
        root_path = Path(root).expanduser()
        for candidate in candidates:
            path = root_path / candidate
            if path.is_file():
                return path.resolve()
        return None

    @staticmethod
    def _resolve_memorix_db_from_config(root: str | Path | None) -> Optional[Path]:
        if not root or tomllib is None:
            return None
        root_path = Path(root).expanduser()
        config_path = root_path / "config" / "a_memorix.toml"
        if not config_path.is_file():
            return None
        try:
            with config_path.open("rb") as handle:
                config = tomllib.load(handle)
        except Exception as exc:
            logger.warning(f"[MaiBotImport] 读取 A_memorix 配置失败: {config_path}: {exc}")
            return None
        storage = config.get("storage") if isinstance(config, Mapping) else None
        raw_data_dir = storage.get("data_dir") if isinstance(storage, Mapping) else None
        data_dir = _resolve_maibot_repo_path(root_path, raw_data_dir, default="data/plugins/a-dawn.a-memorix")
        db_path = data_dir / "metadata" / "metadata.db"
        return db_path.resolve() if db_path.is_file() else None

    def _read_sessions(self, db_path: Path) -> list[MaiBotSession]:
        with _connect(db_path) as conn:
            if not _table_exists(conn, "chat_sessions"):
                return []
            columns = _columns(conn, "chat_sessions")
            select_cols = _select_columns(
                columns,
                [
                    "session_id",
                    "group_id",
                    "user_id",
                    "platform",
                    "group_name",
                    "user_nickname",
                    "user_cardname",
                    "scope",
                ],
            )
            rows = conn.execute(f"SELECT {select_cols} FROM chat_sessions").fetchall()
            sessions = []
            for row in rows:
                data = dict(row)
                display = data.get("group_name") or data.get("user_cardname") or data.get("user_nickname") or ""
                sessions.append(
                    MaiBotSession(
                        session_id=str(data.get("session_id") or ""),
                        group_id=str(data.get("group_id") or data.get("session_id") or "global"),
                        user_id=str(data.get("user_id") or ""),
                        platform=str(data.get("platform") or ""),
                        display_name=str(display or ""),
                        scope=str(data.get("scope") or ""),
                    )
                )
            return sessions

    def _read_expressions(
        self,
        db_path: Path,
        session_map: Mapping[str, MaiBotSession],
    ) -> list[MaiBotExpression]:
        with _connect(db_path) as conn:
            if not _table_exists(conn, "expressions"):
                return []
            columns = _columns(conn, "expressions")
            select_cols = _select_columns(
                columns,
                [
                    "id",
                    "situation",
                    "style",
                    "content_list",
                    "count",
                    "session_id",
                    "checked",
                    "modified_by",
                    "create_time",
                    "last_active_time",
                ],
            )
            rows = conn.execute(f"SELECT {select_cols} FROM expressions").fetchall()
            items = []
            for row in rows:
                data = dict(row)
                session_id = str(data.get("session_id") or "")
                session = session_map.get(session_id)
                items.append(
                    MaiBotExpression(
                        source_id=str(data.get("id") or ""),
                        situation=str(data.get("situation") or "").strip(),
                        style=str(data.get("style") or "").strip(),
                        content_list=_json_list(data.get("content_list")),
                        count=max(1, int(data.get("count") or 1)),
                        session_id=session_id,
                        group_id=(session.group_id if session else session_id) or "global",
                        checked=bool(data.get("checked")),
                        modified_by=str(data.get("modified_by") or ""),
                        created_at=_to_timestamp(data.get("create_time"), default=0),
                        last_active_at=_to_timestamp(data.get("last_active_time"), default=0),
                    )
                )
            return [item for item in items if item.situation and item.style]

    def _read_jargons(
        self,
        db_path: Path,
        session_map: Mapping[str, MaiBotSession],
    ) -> list[MaiBotJargon]:
        with _connect(db_path) as conn:
            if not _table_exists(conn, "jargons"):
                return []
            columns = _columns(conn, "jargons")
            select_cols = _select_columns(
                columns,
                [
                    "id",
                    "content",
                    "raw_content",
                    "meaning",
                    "session_id_dict",
                    "count",
                    "is_jargon",
                    "is_complete",
                    "is_global",
                    "last_inference_count",
                    "created_by",
                    "created_timestamp",
                    "updated_timestamp",
                ],
            )
            rows = conn.execute(f"SELECT {select_cols} FROM jargons").fetchall()
            items = []
            for row in rows:
                data = dict(row)
                session_counts = _json_dict(data.get("session_id_dict"))
                group_ids = []
                for session_id in session_counts:
                    session = session_map.get(str(session_id))
                    group_ids.append((session.group_id if session else str(session_id)) or "global")
                if not group_ids and data.get("is_global"):
                    group_ids = ["global"]
                items.append(
                    MaiBotJargon(
                        source_id=str(data.get("id") or ""),
                        content=str(data.get("content") or "").strip(),
                        raw_content=_json_list(data.get("raw_content")),
                        meaning=str(data.get("meaning") or "").strip(),
                        session_id_counts={str(k): int(v or 0) for k, v in session_counts.items()},
                        group_ids=sorted(set(group_ids)) or ["global"],
                        count=max(1, int(data.get("count") or 1)),
                        is_jargon=_optional_bool(data.get("is_jargon")),
                        is_complete=bool(data.get("is_complete")),
                        is_global=bool(data.get("is_global")),
                        created_by=str(data.get("created_by") or ""),
                        created_at=_to_timestamp(data.get("created_timestamp"), default=0),
                        updated_at=_to_timestamp(data.get("updated_timestamp"), default=0),
                    )
                )
            return [item for item in items if item.content]

    def _read_memories(self, db_path: Path) -> list[MaiBotMemoryParagraph]:
        with _connect(db_path) as conn:
            if not _table_exists(conn, "paragraphs"):
                return []
            columns = _columns(conn, "paragraphs")
            select_cols = _select_columns(
                columns,
                [
                    "hash",
                    "content",
                    "metadata",
                    "source",
                    "knowledge_type",
                    "created_at",
                    "updated_at",
                    "is_deleted",
                ],
            )
            where = " WHERE COALESCE(is_deleted, 0) = 0" if "is_deleted" in columns else ""
            rows = conn.execute(f"SELECT {select_cols} FROM paragraphs{where} LIMIT 1000").fetchall()
            items = []
            for row in rows:
                data = dict(row)
                items.append(
                    MaiBotMemoryParagraph(
                        source_id=str(data.get("hash") or ""),
                        content=str(data.get("content") or "").strip(),
                        metadata=_json_dict(data.get("metadata")),
                        source=str(data.get("source") or ""),
                        knowledge_type=str(data.get("knowledge_type") or ""),
                        created_at=_to_timestamp(data.get("created_at"), default=0),
                        updated_at=_to_timestamp(data.get("updated_at"), default=0),
                    )
                )
            return [item for item in items if item.content]

    def _read_chat_history_memories(
        self,
        db_path: Path,
        session_map: Mapping[str, MaiBotSession],
    ) -> list[MaiBotMemoryParagraph]:
        with _connect(db_path) as conn:
            if not _table_exists(conn, "chat_history"):
                return []
            columns = _columns(conn, "chat_history")
            if "summary" not in columns:
                return []
            chat_id_col = "session_id" if "session_id" in columns else "chat_id" if "chat_id" in columns else ""
            if not chat_id_col:
                return []
            start_col = "start_timestamp" if "start_timestamp" in columns else "start_time" if "start_time" in columns else ""
            end_col = "end_timestamp" if "end_timestamp" in columns else "end_time" if "end_time" in columns else ""
            wanted = ["id", chat_id_col, start_col, end_col, "participants", "theme", "keywords", "summary"]
            select_cols = _select_columns(columns, [name for name in wanted if name])
            rows = conn.execute(f"SELECT {select_cols} FROM chat_history").fetchall()
            items = []
            for row in rows:
                data = dict(row)
                session_id = str(data.get(chat_id_col) or "")
                summary = str(data.get("summary") or "").strip()
                theme = str(data.get("theme") or "").strip()
                if not summary and not theme:
                    continue
                text = f"主题：{theme}\n概括：{summary}".strip() if theme else summary
                session = session_map.get(session_id)
                metadata = {
                    "group_id": (session.group_id if session else session_id) or "global",
                    "session_id": session_id,
                    "participants": _json_decode(data.get("participants")) or data.get("participants"),
                    "keywords": _json_decode(data.get("keywords")) or data.get("keywords"),
                    "source_table": "chat_history",
                }
                items.append(
                    MaiBotMemoryParagraph(
                        source_id=f"chat_history:{data.get('id') or session_id}",
                        content=text,
                        metadata=metadata,
                        source=f"maibot.chat_history:{session_id or data.get('id')}",
                        knowledge_type="chat_summary",
                        created_at=_to_timestamp(data.get(start_col), default=0),
                        updated_at=_to_timestamp(data.get(end_col), default=0),
                    )
                )
            return items

    @staticmethod
    def _format_expression_few_shot(item: MaiBotExpression) -> str:
        examples = "\n".join(f"- {text}" for text in item.content_list[:5])
        base = f"场景: {item.situation}\n表达方式: {item.style}"
        return f"{base}\n原始片段:\n{examples}" if examples else base


@contextmanager
def _connect(path: Path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _select_columns(columns: set[str], wanted: list[str]) -> str:
    parts = []
    for name in wanted:
        if name in columns:
            parts.append(f'"{name}"')
        else:
            parts.append(f"NULL AS \"{name}\"")
    return ", ".join(parts)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_list(value: Any) -> list[Any]:
    decoded = _json_decode(value)
    if isinstance(decoded, list):
        return decoded
    if decoded in (None, ""):
        return []
    return [decoded]


def _json_dict(value: Any) -> dict[str, Any]:
    decoded = _json_decode(value)
    return decoded if isinstance(decoded, dict) else {}


def _json_decode(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def _to_timestamp(value: Any, *, default: float) -> float:
    if value in (None, ""):
        return float(default)
    if isinstance(value, (int, float)):
        number = float(value)
        return number / 1000 if number > 10_000_000_000 else number
    text = str(value).strip()
    if not text:
        return float(default)
    try:
        number = float(text)
        return number / 1000 if number > 10_000_000_000 else number
    except ValueError:
        pass
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return float(default)


def _optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _pick_keys(item: Mapping[str, Any], cls: type) -> dict[str, Any]:
    annotations = getattr(cls, "__annotations__", {})
    return {key: item[key] for key in annotations if key in item}


def _metadata_group_id(metadata: Mapping[str, Any]) -> str:
    for key in ("group_id", "chat_id", "session_id"):
        value = metadata.get(key) if isinstance(metadata, Mapping) else None
        if value:
            return str(value)
    return ""


def _resolve_maibot_repo_path(root_path: Path, raw_path: Any, *, default: str) -> Path:
    raw_value = str(raw_path or default).strip() or default
    candidate = Path(raw_value).expanduser()
    if candidate.is_absolute():
        return candidate
    return root_path / candidate
