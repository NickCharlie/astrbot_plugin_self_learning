"""SillyTavern worldbook import bridge.

This module reads standard SillyTavern worldbook JSON, normalizes entries, and
writes them through the plugin's existing review, jargon, and knowledge graph
tables. It deliberately avoids schema changes: full entry text is preserved in
persona review metadata/content, while the local KG tables store entry/keyword
nodes and trigger relations.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from astrbot.api import logger
from sqlalchemy import and_, desc, func, select


WORLDBOOK_EXPORT_VERSION = 1
WORLDBOOK_SOURCE = "sillytavern_worldbook"
WORLDBOOK_REVIEW_TYPE = "worldbook_entry"
WORLDBOOK_TRIGGER_PREDICATE = "触发关键词"


@dataclass
class WorldBookEntry:
    """Normalized SillyTavern worldbook entry."""

    source_id: str
    title: str
    content: str
    keys: list[str] = field(default_factory=list)
    secondary_keys: list[str] = field(default_factory=list)
    constant: bool = False
    order: float = 100.0
    insertion_order: int = 0
    enabled: bool = True
    comment: str = ""
    selective: bool = False
    position: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def keywords(self) -> list[str]:
        return _unique_terms([*self.keys, *self.secondary_keys])


@dataclass
class WorldBookPackage:
    """Normalized import package for a SillyTavern worldbook."""

    version: int = WORLDBOOK_EXPORT_VERSION
    source: str = WORLDBOOK_SOURCE
    name: str = "SillyTavern WorldBook"
    exported_at: float = field(default_factory=time.time)
    source_paths: dict[str, str] = field(default_factory=dict)
    entries: list[WorldBookEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source": self.source,
            "name": self.name,
            "exported_at": self.exported_at,
            "source_paths": self.source_paths,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorldBookPackage":
        return cls(
            version=int(payload.get("version") or WORLDBOOK_EXPORT_VERSION),
            source=str(payload.get("source") or WORLDBOOK_SOURCE),
            name=str(payload.get("name") or "SillyTavern WorldBook"),
            exported_at=_to_timestamp(payload.get("exported_at"), default=time.time()),
            source_paths=dict(payload.get("source_paths") or {}),
            entries=[
                WorldBookEntry(**_pick_keys(entry, WorldBookEntry))
                for entry in _as_list(payload.get("entries"))
                if isinstance(entry, Mapping)
            ],
        )


class WorldBookImporter:
    """Parse and import SillyTavern worldbook JSON."""

    def __init__(self, database_manager: Any = None) -> None:
        self.database_manager = database_manager

    def preview(
        self,
        *,
        payload: Mapping[str, Any] | str | None = None,
        json_text: str | None = None,
        json_path: str | Path | None = None,
    ) -> dict[str, Any]:
        package = self.load_package(payload=payload, json_text=json_text, json_path=json_path)
        return self.package_summary(package)

    def load_package(
        self,
        *,
        payload: Mapping[str, Any] | str | None = None,
        json_text: str | None = None,
        json_path: str | Path | None = None,
    ) -> WorldBookPackage:
        source_paths: dict[str, str] = {}
        if payload is None and json_text:
            payload = _json_decode(json_text)
        if payload is None and json_path:
            path = Path(json_path).expanduser()
            if not path.is_file():
                raise FileNotFoundError(f"世界书 JSON 文件不存在: {path}")
            payload = _json_decode(path.read_text(encoding="utf-8-sig"))
            source_paths["worldbook_json"] = str(path.resolve())
        if isinstance(payload, str):
            payload = _json_decode(payload)
        if not isinstance(payload, Mapping):
            raise ValueError("请提供 SillyTavern 世界书 JSON 对象或 JSON 字符串")

        if payload.get("source") == WORLDBOOK_SOURCE and isinstance(payload.get("entries"), list):
            package = WorldBookPackage.from_dict(payload)
            package.source_paths.update(source_paths)
            return package

        package = self._parse_sillytavern_payload(payload)
        package.source_paths.update(source_paths)
        return package

    async def import_from_source(self, **kwargs: Any) -> dict[str, Any]:
        package = self.load_package(
            payload=kwargs.get("payload"),
            json_text=kwargs.get("json_text"),
            json_path=kwargs.get("json_path"),
        )
        return await self.import_package(
            package,
            default_group_id=str(kwargs.get("default_group_id") or "global"),
            import_memories=_to_bool(kwargs.get("import_memories", True), True),
            import_jargons=_to_bool(kwargs.get("import_jargons", True), True),
            import_knowledge_graph=_to_bool(kwargs.get("import_knowledge_graph", True), True),
            include_disabled=_to_bool(kwargs.get("include_disabled", False), False),
        )

    async def import_package(
        self,
        package: WorldBookPackage,
        *,
        default_group_id: str = "global",
        import_memories: bool = True,
        import_jargons: bool = True,
        import_knowledge_graph: bool = True,
        include_disabled: bool = False,
    ) -> dict[str, Any]:
        if not self.database_manager:
            raise RuntimeError("数据库管理器不可用，无法导入世界书数据")

        result = {
            "success": True,
            "entries_imported": 0,
            "memory_reviews_imported": 0,
            "jargons_imported": 0,
            "kg_entities_imported": 0,
            "kg_relations_imported": 0,
            "destinations": worldbook_import_destinations(),
            "review_breakdown": {
                "persona_memory_reviews": 0,
                "jargon_candidates": 0,
                "knowledge_graph_entities": 0,
                "knowledge_graph_relations": 0,
            },
            "skipped": 0,
            "errors": [],
        }

        now = time.time()
        import_id = f"worldbook:{_safe_slug(package.name)}:{int(now)}"
        group_id = str(default_group_id or "global")

        try:
            async with self.database_manager.get_session() as session:
                for entry in package.entries:
                    if not include_disabled and not entry.enabled:
                        result["skipped"] += 1
                        continue

                    imported_any = False
                    if import_memories and entry.content:
                        review_exists = await self._entry_review_exists(
                            session,
                            package.name,
                            entry,
                            group_id,
                        )
                        if not review_exists:
                            self._add_memory_review(
                                session,
                                package,
                                entry,
                                group_id=group_id,
                                now=now,
                                import_id=import_id,
                            )
                            result["memory_reviews_imported"] += 1
                            imported_any = True

                    if import_jargons:
                        imported = await self._import_jargon_candidates(
                            session,
                            package,
                            entry,
                            group_id=group_id,
                            now=now,
                            import_id=import_id,
                        )
                        result["jargons_imported"] += imported
                        imported_any = imported_any or imported > 0

                    if import_knowledge_graph:
                        entities, relations = await self._import_knowledge_graph(
                            session,
                            package,
                            entry,
                            group_id=group_id,
                            now=now,
                        )
                        result["kg_entities_imported"] += entities
                        result["kg_relations_imported"] += relations
                        imported_any = imported_any or entities > 0 or relations > 0

                    if imported_any:
                        result["entries_imported"] += 1
                    else:
                        result["skipped"] += 1
                await session.commit()
        except Exception as exc:
            logger.error(f"[WorldBookImport] 导入世界书失败: {exc}", exc_info=True)
            result["errors"].append(str(exc))

        result["success"] = not result["errors"]
        result["review_breakdown"] = {
            "persona_memory_reviews": result["memory_reviews_imported"],
            "jargon_candidates": result["jargons_imported"],
            "knowledge_graph_entities": result["kg_entities_imported"],
            "knowledge_graph_relations": result["kg_relations_imported"],
        }
        return result

    async def import_history(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        if not self.database_manager:
            raise RuntimeError("数据库管理器不可用，无法读取世界书导入历史")
        try:
            from ...models.orm.learning import PersonaLearningReview
        except ImportError:
            from models.orm.learning import PersonaLearningReview

        safe_limit = max(1, min(int(limit or 20), 100))
        safe_offset = max(0, int(offset or 0))
        async with self.database_manager.get_session() as session:
            total = (
                await session.execute(
                    select(func.count(PersonaLearningReview.id)).where(
                        PersonaLearningReview.update_type == WORLDBOOK_REVIEW_TYPE
                    )
                )
            ).scalar() or 0
            rows = (
                await session.execute(
                    select(PersonaLearningReview)
                    .where(PersonaLearningReview.update_type == WORLDBOOK_REVIEW_TYPE)
                    .order_by(desc(PersonaLearningReview.timestamp))
                    .offset(safe_offset)
                    .limit(safe_limit)
                )
            ).scalars().all()

        items = []
        imports: dict[str, dict[str, Any]] = {}
        for row in rows:
            metadata = _json_dict(getattr(row, "metadata_", None))
            imported_at = metadata.get("imported_at") or row.timestamp
            import_id = str(metadata.get("import_id") or f"review:{row.id}")
            item = {
                "review_id": row.id,
                "group_id": row.group_id,
                "status": row.status,
                "worldbook_name": metadata.get("worldbook_name"),
                "worldbook_entry_id": metadata.get("worldbook_entry_id"),
                "title": metadata.get("title"),
                "import_id": import_id,
                "imported_at": imported_at,
                "content_preview": _preview_text(row.new_content or row.proposed_content or ""),
            }
            items.append(item)
            aggregate = imports.setdefault(
                import_id,
                {
                    "import_id": import_id,
                    "worldbook_name": item["worldbook_name"],
                    "group_id": row.group_id,
                    "imported_at": imported_at,
                    "entries": 0,
                    "review_ids": [],
                },
            )
            aggregate["entries"] += 1
            aggregate["review_ids"].append(row.id)

        return {
            "total": int(total),
            "limit": safe_limit,
            "offset": safe_offset,
            "items": items,
            "imports": list(imports.values()),
        }

    def package_summary(self, package: WorldBookPackage) -> dict[str, Any]:
        keyword_count = sum(len(entry.keys) for entry in package.entries)
        secondary_keyword_count = sum(len(entry.secondary_keys) for entry in package.entries)
        content_chars = sum(len(entry.content) for entry in package.entries)
        return {
            "version": package.version,
            "source": package.source,
            "name": package.name,
            "source_paths": package.source_paths,
            "counts": {
                "entries": len(package.entries),
                "enabled_entries": sum(1 for entry in package.entries if entry.enabled),
                "disabled_entries": sum(1 for entry in package.entries if not entry.enabled),
                "constant_entries": sum(1 for entry in package.entries if entry.constant),
                "keywords": keyword_count,
                "secondary_keywords": secondary_keyword_count,
                "content_chars": content_chars,
                "estimated_tokens": max(1, content_chars // 4) if content_chars else 0,
            },
            "samples": {
                "entries": [entry.to_dict() for entry in package.entries[:5]],
            },
            "destinations": worldbook_import_destinations(),
            "review_breakdown": {
                "persona_memory_reviews": sum(1 for entry in package.entries if entry.content),
                "jargon_candidates": keyword_count + secondary_keyword_count,
                "knowledge_graph_entities": len(package.entries) + len(_all_keywords(package.entries)),
                "knowledge_graph_relations": keyword_count + secondary_keyword_count,
            },
        }

    def export_json(self, **kwargs: Any) -> dict[str, Any]:
        return self.load_package(**kwargs).to_dict()

    def _parse_sillytavern_payload(self, payload: Mapping[str, Any]) -> WorldBookPackage:
        entries_payload = payload.get("entries")
        if entries_payload is None and isinstance(payload.get("data"), Mapping):
            entries_payload = payload["data"].get("entries")
        if entries_payload is None and isinstance(payload, list):
            entries_payload = payload
        if not isinstance(entries_payload, (Mapping, list)):
            raise ValueError("不是有效的 SillyTavern 世界书 JSON：缺少 entries 对象或数组")

        entries: list[WorldBookEntry] = []
        for index, (source_key, raw_entry) in enumerate(_iter_entries(entries_payload)):
            entry = self._parse_entry(source_key, raw_entry, index)
            if entry:
                entries.append(entry)

        return WorldBookPackage(
            name=str(payload.get("name") or payload.get("worldbook_name") or "SillyTavern WorldBook"),
            exported_at=_to_timestamp(payload.get("exported_at"), default=time.time()),
            entries=entries,
        )

    @staticmethod
    def _parse_entry(source_key: Any, raw_entry: Any, index: int) -> Optional[WorldBookEntry]:
        if not isinstance(raw_entry, Mapping):
            return None
        content = str(raw_entry.get("content") or "").strip()
        keys = _normalize_terms(_first_present(raw_entry, ("key", "keys", "primaryKeys", "primary_keys")))
        secondary_keys = _normalize_terms(
            _first_present(
                raw_entry,
                (
                    "secondaryKeys",
                    "secondary_keys",
                    "keysecondary",
                    "keySecondary",
                    "secondary",
                ),
            )
        )
        if not content and not keys and not secondary_keys:
            return None

        disabled = _to_bool(
            _first_present(raw_entry, ("disable", "disabled", "is_disabled")),
            False,
        )
        enabled_value = _first_present(raw_entry, ("enabled", "is_enabled"))
        enabled = _to_bool(enabled_value, True) if enabled_value is not None else not disabled
        enabled = bool(enabled and not disabled)

        source_id = str(
            raw_entry.get("uid")
            or raw_entry.get("id")
            or raw_entry.get("entry_id")
            or source_key
            or index
        )
        comment = str(raw_entry.get("comment") or "").strip()
        title = str(
            raw_entry.get("name")
            or raw_entry.get("title")
            or comment
            or (keys[0] if keys else "")
            or f"entry-{source_id}"
        ).strip()

        return WorldBookEntry(
            source_id=source_id,
            title=title,
            content=content,
            keys=keys,
            secondary_keys=secondary_keys,
            constant=_to_bool(raw_entry.get("constant"), False),
            order=_to_float(raw_entry.get("order"), default=100.0),
            insertion_order=_to_int(
                _first_present(raw_entry, ("insertion_order", "insertionOrder")),
                default=index,
            ),
            enabled=enabled,
            comment=comment,
            selective=_to_bool(raw_entry.get("selective"), False),
            position=raw_entry.get("position"),
            metadata=_entry_metadata(raw_entry),
        )

    async def _entry_review_exists(
        self,
        session: Any,
        worldbook_name: str,
        entry: WorldBookEntry,
        group_id: str,
    ) -> bool:
        try:
            from ...models.orm.learning import PersonaLearningReview
        except ImportError:
            from models.orm.learning import PersonaLearningReview

        stmt = select(PersonaLearningReview.id).where(
            and_(
                PersonaLearningReview.update_type == WORLDBOOK_REVIEW_TYPE,
                PersonaLearningReview.group_id == group_id,
                PersonaLearningReview.metadata_.like(
                    f'%"worldbook_name": "{_like_json_text(worldbook_name)}"%'
                ),
                PersonaLearningReview.metadata_.like(
                    f'%"worldbook_entry_id": "{_like_json_text(entry.source_id)}"%'
                ),
            )
        )
        return (await session.execute(stmt)).scalar_one_or_none() is not None

    @staticmethod
    def _add_memory_review(
        session: Any,
        package: WorldBookPackage,
        entry: WorldBookEntry,
        *,
        group_id: str,
        now: float,
        import_id: str,
    ) -> None:
        try:
            from ...models.orm.learning import PersonaLearningReview
        except ImportError:
            from models.orm.learning import PersonaLearningReview

        session.add(
            PersonaLearningReview(
                timestamp=now,
                group_id=group_id,
                update_type=WORLDBOOK_REVIEW_TYPE,
                original_content="",
                new_content=entry.content,
                proposed_content=entry.content,
                confidence_score=0.7,
                reason="从 SillyTavern 世界书导入的设定条目，等待确认后可沉淀到人格/记忆上下文。",
                status="pending",
                metadata_=json.dumps(
                    _entry_import_metadata(package, entry, now=now, import_id=import_id),
                    ensure_ascii=False,
                ),
            )
        )

    @staticmethod
    async def _import_jargon_candidates(
        session: Any,
        package: WorldBookPackage,
        entry: WorldBookEntry,
        *,
        group_id: str,
        now: float,
        import_id: str,
    ) -> int:
        try:
            from ...models.orm.jargon import Jargon
        except ImportError:
            from models.orm.jargon import Jargon

        imported = 0
        now_int = int(now)
        for keyword in entry.keywords:
            existing = (
                await session.execute(
                    select(Jargon.id).where(
                        and_(
                            Jargon.chat_id == group_id,
                            Jargon.content == keyword,
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue
            raw_content = {
                "source": WORLDBOOK_SOURCE,
                "worldbook_name": package.name,
                "worldbook_entry_id": entry.source_id,
                "title": entry.title,
                "content_preview": _preview_text(entry.content, limit=240),
                "keys": entry.keys,
                "secondary_keys": entry.secondary_keys,
                "constant": entry.constant,
                "order": entry.order,
                "insertion_order": entry.insertion_order,
                "import_id": import_id,
            }
            session.add(
                Jargon(
                    content=keyword,
                    raw_content=json.dumps(raw_content, ensure_ascii=False),
                    meaning=None,
                    is_jargon=None,
                    count=1,
                    last_inference_count=0,
                    is_complete=False,
                    is_global=group_id == "global",
                    chat_id=group_id,
                    created_at=now_int,
                    updated_at=now_int,
                )
            )
            imported += 1
        return imported

    @staticmethod
    async def _import_knowledge_graph(
        session: Any,
        package: WorldBookPackage,
        entry: WorldBookEntry,
        *,
        group_id: str,
        now: float,
    ) -> tuple[int, int]:
        try:
            from ...models.orm.knowledge_graph import KGEntity, KGRelation
        except ImportError:
            from models.orm.knowledge_graph import KGEntity, KGRelation

        entities_imported = 0
        relations_imported = 0
        entry_name = _db_text(f"世界书:{package.name}:{entry.title}", 191)
        if await _touch_entity(session, KGEntity, entry_name, group_id, "worldbook_entry", now):
            entities_imported += 1

        for keyword in entry.keywords:
            keyword_name = _db_text(keyword, 191)
            if await _touch_entity(session, KGEntity, keyword_name, group_id, "worldbook_keyword", now):
                entities_imported += 1
            relation_exists = (
                await session.execute(
                    select(KGRelation.id).where(
                        and_(
                            KGRelation.subject == entry_name,
                            KGRelation.predicate == WORLDBOOK_TRIGGER_PREDICATE,
                            KGRelation.object == keyword_name,
                            KGRelation.group_id == group_id,
                        )
                    )
                )
            ).scalar_one_or_none()
            if relation_exists:
                continue
            session.add(
                KGRelation(
                    subject=entry_name,
                    predicate=WORLDBOOK_TRIGGER_PREDICATE,
                    object=keyword_name,
                    confidence=1.0,
                    created_time=now,
                    group_id=group_id,
                )
            )
            relations_imported += 1
        return entities_imported, relations_imported


async def _touch_entity(
    session: Any,
    entity_cls: Any,
    name: str,
    group_id: str,
    entity_type: str,
    now: float,
) -> bool:
    existing = (
        await session.execute(
            select(entity_cls).where(
                and_(
                    entity_cls.name == name,
                    entity_cls.group_id == group_id,
                )
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.appear_count = (existing.appear_count or 0) + 1
        existing.last_active_time = now
        if entity_type != "general":
            existing.entity_type = entity_type
        return False
    session.add(
        entity_cls(
            name=name,
            entity_type=entity_type,
            appear_count=1,
            last_active_time=now,
            group_id=group_id,
        )
    )
    return True


def worldbook_import_destinations() -> dict[str, str]:
    return {
        "memories": "persona_update_reviews",
        "jargons": "jargon",
        "knowledge_graph_entities": "kg_entities",
        "knowledge_graph_relations": "kg_relations",
    }


def _iter_entries(entries_payload: Mapping[str, Any] | list[Any]):
    if isinstance(entries_payload, Mapping):
        return sorted(entries_payload.items(), key=lambda item: _entry_sort_key(item[0]))
    return list(enumerate(entries_payload))


def _entry_sort_key(key: Any) -> tuple[int, int | str]:
    text = str(key)
    try:
        return (0, int(text))
    except ValueError:
        return (1, text)


def _entry_metadata(entry: Mapping[str, Any]) -> dict[str, Any]:
    omitted = {
        "content",
        "key",
        "keys",
        "primaryKeys",
        "primary_keys",
        "secondaryKeys",
        "secondary_keys",
        "keysecondary",
        "keySecondary",
        "secondary",
    }
    return {str(key): value for key, value in entry.items() if key not in omitted}


def _entry_import_metadata(
    package: WorldBookPackage,
    entry: WorldBookEntry,
    *,
    now: float,
    import_id: str,
) -> dict[str, Any]:
    return {
        "source": WORLDBOOK_SOURCE,
        "worldbook_name": package.name,
        "worldbook_entry_id": entry.source_id,
        "title": entry.title,
        "keys": entry.keys,
        "secondary_keys": entry.secondary_keys,
        "constant": entry.constant,
        "order": entry.order,
        "insertion_order": entry.insertion_order,
        "enabled": entry.enabled,
        "comment": entry.comment,
        "selective": entry.selective,
        "position": entry.position,
        "entry_metadata": entry.metadata,
        "import_id": import_id,
        "imported_at": now,
    }


def _normalize_terms(value: Any) -> list[str]:
    terms: list[str] = []
    if value is None:
        return terms
    if isinstance(value, str):
        parts = value.replace("\n", ",").split(",")
        terms.extend(part.strip() for part in parts)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            terms.extend(_normalize_terms(item))
    else:
        terms.append(str(value).strip())
    return _unique_terms(terms)


def _unique_terms(values: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _all_keywords(entries: list[WorldBookEntry]) -> list[str]:
    return _unique_terms([keyword for entry in entries for keyword in entry.keywords])


def _first_present(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_decode(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return json.loads(text)


def _json_dict(value: Any) -> dict[str, Any]:
    decoded = None
    try:
        decoded = _json_decode(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


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


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _to_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _preview_text(value: str, *, limit: int = 120) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}…"


def _db_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _safe_slug(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "-" for ch in str(value or "worldbook").lower())
    return "-".join(part for part in text.split("-") if part)[:48] or "worldbook"


def _like_json_text(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _pick_keys(item: Mapping[str, Any], cls: type) -> dict[str, Any]:
    annotations = getattr(cls, "__annotations__", {})
    return {key: item[key] for key in annotations if key in item}
