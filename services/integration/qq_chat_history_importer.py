"""QQ chat history import bridge.

The importer focuses on QQChatExporter V5 chunked JSONL exports and the
Alpaca-style training data produced by the local formatting script.  It also
contains a small best-effort parser for plain QQ TXT/HTML logs so the WebUI can
accept common lightweight exports without a schema change.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

from astrbot.api import logger
from sqlalchemy import select

try:
    from ...models.orm.message import RawMessage
    from ...utils.text_utils import truncate_for_db
except ImportError:
    from models.orm.message import RawMessage
    from utils.text_utils import truncate_for_db


QQ_HISTORY_EXPORT_VERSION = 1
QQ_HISTORY_SOURCE = "qq_chat_history"
QQ_HISTORY_MESSAGE_PREFIX = "qq-history"
DEFAULT_IMPORT_LIMIT = 100_000
DEFAULT_PREVIEW_LIMIT = 100_000
DEFAULT_BATCH_SIZE = 500


@dataclass
class QQChatMessage:
    """Normalized message ready for the raw_messages table."""

    source_id: str
    sender_id: str
    sender_name: str
    message: str
    group_id: str
    timestamp: int
    platform: str = "qq"
    message_id: str = ""
    reply_to: Optional[str] = None
    is_bot: bool = False
    source_type: str = "qce"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_raw_message(self) -> dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "message": self.message,
            "group_id": self.group_id,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "message_id": self.message_id,
            "reply_to": self.reply_to,
        }

    def sample(self) -> dict[str, Any]:
        data = asdict(self)
        data["message"] = _preview_text(self.message, limit=120)
        data["metadata"] = {}
        return data


@dataclass
class QQChatSource:
    """Resolved import source."""

    path: Optional[Path] = None
    manifest: dict[str, Any] = field(default_factory=dict)
    qce_files: list[Path] = field(default_factory=list)
    training_file: Optional[Path] = None
    text_file: Optional[Path] = None
    html_file: Optional[Path] = None
    payload: Any = None
    source_format: str = "unknown"

    @property
    def source_paths(self) -> dict[str, Any]:
        paths: dict[str, Any] = {}
        if self.path:
            paths["root"] = str(self.path)
        if self.manifest:
            paths["manifest"] = str((self.path / "manifest.json") if self.path and self.path.is_dir() else "")
        if self.qce_files:
            paths["chunks"] = [str(path) for path in self.qce_files]
        if self.training_file:
            paths["training_file"] = str(self.training_file)
        if self.text_file:
            paths["text_file"] = str(self.text_file)
        if self.html_file:
            paths["html_file"] = str(self.html_file)
        return {key: value for key, value in paths.items() if value}


class QQChatHistoryImporter:
    """Parse QQ/QCE chat history and import it into raw_messages."""

    def __init__(self, database_manager: Any = None) -> None:
        self.database_manager = database_manager

    def preview(
        self,
        *,
        source_path: str | Path | None = None,
        payload: Any = None,
        json_text: str | None = None,
        default_group_id: str = "",
        include_training_pairs: bool = False,
        max_messages: int = DEFAULT_PREVIEW_LIMIT,
        min_text_length: int = 2,
    ) -> dict[str, Any]:
        source = self.resolve_source(
            source_path=source_path,
            payload=payload,
            json_text=json_text,
            include_training_pairs=include_training_pairs,
        )
        summary = _empty_summary(source, default_group_id=default_group_id)
        limit = _positive_int(max_messages, DEFAULT_PREVIEW_LIMIT)

        for message in self.iter_messages(
            source,
            default_group_id=default_group_id,
            include_training_pairs=include_training_pairs,
            min_text_length=min_text_length,
        ):
            if summary["counts"]["messages"] >= limit:
                summary["truncated"] = True
                break
            _add_summary_message(summary, message)

        summary.pop("_sender_counts", None)
        return summary

    async def import_from_source(self, **kwargs: Any) -> dict[str, Any]:
        source = self.resolve_source(
            source_path=kwargs.get("source_path") or kwargs.get("path"),
            payload=kwargs.get("payload"),
            json_text=kwargs.get("json_text"),
            include_training_pairs=_to_bool(kwargs.get("include_training_pairs", False), False),
        )
        return await self.import_source(
            source,
            default_group_id=str(kwargs.get("default_group_id") or ""),
            include_training_pairs=_to_bool(kwargs.get("include_training_pairs", False), False),
            max_messages=_positive_int(kwargs.get("max_messages"), DEFAULT_IMPORT_LIMIT),
            min_text_length=_positive_int(kwargs.get("min_text_length"), 2),
            batch_size=_positive_int(kwargs.get("batch_size"), DEFAULT_BATCH_SIZE),
        )

    async def import_source(
        self,
        source: QQChatSource,
        *,
        default_group_id: str = "",
        include_training_pairs: bool = False,
        max_messages: int = DEFAULT_IMPORT_LIMIT,
        min_text_length: int = 2,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> dict[str, Any]:
        if not self.database_manager:
            raise RuntimeError("数据库管理器不可用，无法导入 QQ 聊天记录")

        result = {
            "success": True,
            "source": QQ_HISTORY_SOURCE,
            "source_format": source.source_format,
            "source_paths": source.source_paths,
            "group_id": self._group_id(source, default_group_id),
            "messages_seen": 0,
            "messages_imported": 0,
            "duplicate_messages": 0,
            "skipped": 0,
            "truncated": False,
            "destinations": qq_chat_import_destinations(),
            "queued_for_learning": True,
            "errors": [],
        }

        seen_ids: set[str] = set()
        batch: list[QQChatMessage] = []
        safe_batch = max(1, min(int(batch_size or DEFAULT_BATCH_SIZE), 500))
        safe_limit = max(1, int(max_messages or DEFAULT_IMPORT_LIMIT))

        try:
            async with self.database_manager.get_session() as session:
                for message in self.iter_messages(
                    source,
                    default_group_id=default_group_id,
                    include_training_pairs=include_training_pairs,
                    min_text_length=min_text_length,
                ):
                    if result["messages_seen"] >= safe_limit:
                        result["truncated"] = True
                        break
                    result["messages_seen"] += 1

                    if message.message_id in seen_ids:
                        result["duplicate_messages"] += 1
                        continue
                    seen_ids.add(message.message_id)
                    batch.append(message)
                    if len(batch) >= safe_batch:
                        imported, duplicates = await self._flush_batch(session, batch)
                        result["messages_imported"] += imported
                        result["duplicate_messages"] += duplicates
                        batch.clear()

                if batch:
                    imported, duplicates = await self._flush_batch(session, batch)
                    result["messages_imported"] += imported
                    result["duplicate_messages"] += duplicates

                await session.commit()
        except Exception as exc:
            logger.error(f"[QQChatImport] 导入 QQ 聊天记录失败: {exc}", exc_info=True)
            result["errors"].append(str(exc))

        result["success"] = not result["errors"]
        result["skipped"] = result["duplicate_messages"]
        return result

    async def _flush_batch(self, session: Any, batch: list[QQChatMessage]) -> tuple[int, int]:
        if not batch:
            return 0, 0
        message_ids = [item.message_id for item in batch if item.message_id]
        existing_ids = set()
        if message_ids:
            rows = (
                await session.execute(
                    select(RawMessage.message_id).where(RawMessage.message_id.in_(message_ids))
                )
            ).scalars().all()
            existing_ids = {str(item) for item in rows if item}

        imported = 0
        duplicates = 0
        now = int(time.time())
        for item in batch:
            if item.message_id in existing_ids:
                duplicates += 1
                continue
            raw = item.to_raw_message()
            session.add(
                RawMessage(
                    sender_id=str(raw.get("sender_id") or ""),
                    sender_name=str(raw.get("sender_name") or ""),
                    message=truncate_for_db(str(raw.get("message") or "")),
                    group_id=str(raw.get("group_id") or ""),
                    timestamp=int(raw.get("timestamp") or now),
                    platform=str(raw.get("platform") or "qq"),
                    message_id=raw.get("message_id"),
                    reply_to=raw.get("reply_to"),
                    created_at=now,
                    processed=False,
                )
            )
            imported += 1
        return imported, duplicates

    def resolve_source(
        self,
        *,
        source_path: str | Path | None = None,
        payload: Any = None,
        json_text: str | None = None,
        include_training_pairs: bool = False,
    ) -> QQChatSource:
        if payload is None and json_text:
            payload = _json_decode(json_text)
        if payload is not None:
            return QQChatSource(payload=payload, source_format=_payload_format(payload))

        if not source_path:
            raise ValueError("请提供 QQ 聊天记录路径、JSON 内容或 payload")

        path = Path(source_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"QQ 聊天记录路径不存在: {path}")
        path = path.resolve()

        if path.is_dir():
            manifest_path = path / "manifest.json"
            manifest = _read_json_file(manifest_path) if manifest_path.is_file() else {}
            qce_files = sorted((path / "chunks").glob("*.jsonl")) if (path / "chunks").is_dir() else []
            if not qce_files:
                qce_files = sorted(path.glob("*.jsonl"))
            training_file = path / "train_data.json" if (path / "train_data.json").is_file() else None
            if qce_files:
                return QQChatSource(
                    path=path,
                    manifest=manifest if isinstance(manifest, dict) else {},
                    qce_files=qce_files,
                    training_file=training_file if include_training_pairs else None,
                    source_format="qce_chunked_jsonl",
                )
            if training_file:
                return QQChatSource(
                    path=path,
                    manifest=manifest if isinstance(manifest, dict) else {},
                    training_file=training_file,
                    source_format="alpaca_training_json",
                )
            raise FileNotFoundError("目录中未找到 QCE chunks/*.jsonl 或 train_data.json")

        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            return QQChatSource(path=path, qce_files=[path], source_format="qce_jsonl")
        if suffix == ".json":
            payload = _read_json_file(path)
            return QQChatSource(path=path, payload=payload, source_format=_payload_format(payload))
        if suffix in {".txt", ".log"}:
            return QQChatSource(path=path, text_file=path, source_format="qq_text")
        if suffix in {".html", ".htm"}:
            return QQChatSource(path=path, html_file=path, source_format="qq_html_text")
        raise ValueError(f"暂不支持的聊天记录格式: {suffix or path.name}")

    def iter_messages(
        self,
        source: QQChatSource,
        *,
        default_group_id: str = "",
        include_training_pairs: bool = False,
        min_text_length: int = 2,
    ) -> Iterator[QQChatMessage]:
        group_id = self._group_id(source, default_group_id)
        chat_info = _chat_info(source.manifest)
        self_uid = str(chat_info.get("selfUid") or chat_info.get("selfUin") or "")

        if source.qce_files:
            for path in source.qce_files:
                yield from self._iter_qce_jsonl(path, group_id=group_id, self_uid=self_uid, min_text_length=min_text_length)
            if include_training_pairs and source.training_file:
                yield from self._iter_training_json(source.training_file, source, group_id=group_id, min_text_length=min_text_length)
            return

        if source.training_file:
            yield from self._iter_training_json(source.training_file, source, group_id=group_id, min_text_length=min_text_length)
            return

        if source.text_file:
            yield from self._iter_text_export(source.text_file, group_id=group_id, min_text_length=min_text_length)
            return

        if source.html_file:
            text = _html_to_text(source.html_file.read_text(encoding="utf-8-sig", errors="ignore"))
            yield from self._iter_text_blocks(text.splitlines(), group_id=group_id, source_label=str(source.html_file), min_text_length=min_text_length)
            return

        if source.payload is not None:
            yield from self._iter_payload(source.payload, group_id=group_id, self_uid=self_uid, min_text_length=min_text_length)

    def _iter_qce_jsonl(
        self,
        path: Path,
        *,
        group_id: str,
        self_uid: str,
        min_text_length: int,
    ) -> Iterator[QQChatMessage]:
        with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
            for line_number, line in enumerate(handle, 1):
                text = line.strip()
                if not text:
                    continue
                try:
                    raw = json.loads(text)
                except json.JSONDecodeError:
                    logger.debug(f"[QQChatImport] 跳过无法解析的 JSONL 行: {path}:{line_number}")
                    continue
                message = self._message_from_qce(raw, group_id=group_id, self_uid=self_uid, min_text_length=min_text_length)
                if message:
                    yield message

    def _iter_payload(
        self,
        payload: Any,
        *,
        group_id: str,
        self_uid: str,
        min_text_length: int,
    ) -> Iterator[QQChatMessage]:
        if isinstance(payload, str):
            payload = _json_decode(payload)
        if isinstance(payload, list):
            if _looks_like_training_items(payload):
                yield from self._training_items_to_messages(payload, group_id=group_id, source_label="payload", min_text_length=min_text_length)
            else:
                for raw in payload:
                    message = self._message_from_qce(raw, group_id=group_id, self_uid=self_uid, min_text_length=min_text_length)
                    if message:
                        yield message
            return
        if isinstance(payload, Mapping):
            chat_info = payload.get("chatInfo") if isinstance(payload.get("chatInfo"), Mapping) else {}
            payload_group_id = str(group_id or chat_info.get("name") or payload.get("group_id") or "global")
            payload_self_uid = str(chat_info.get("selfUid") or chat_info.get("selfUin") or self_uid)
            for key in ("messages", "data", "items", "records"):
                value = payload.get(key)
                if isinstance(value, list):
                    yield from self._iter_payload(
                        value,
                        group_id=payload_group_id,
                        self_uid=payload_self_uid,
                        min_text_length=min_text_length,
                    )
                    return
            if _looks_like_training_items([payload]):
                yield from self._training_items_to_messages([payload], group_id=payload_group_id, source_label="payload", min_text_length=min_text_length)

    def _iter_training_json(
        self,
        path: Path,
        source: QQChatSource,
        *,
        group_id: str,
        min_text_length: int,
    ) -> Iterator[QQChatMessage]:
        payload = _read_json_file(path)
        if not isinstance(payload, list):
            raise ValueError(f"训练集 JSON 不是数组: {path}")
        yield from self._training_items_to_messages(
            payload,
            group_id=group_id,
            source_label=str(path),
            min_text_length=min_text_length,
            self_info=_chat_info(source.manifest),
        )

    def _training_items_to_messages(
        self,
        items: list[Any],
        *,
        group_id: str,
        source_label: str,
        min_text_length: int,
        self_info: Optional[Mapping[str, Any]] = None,
    ) -> Iterator[QQChatMessage]:
        self_info = self_info or {}
        bot_uid = str(self_info.get("selfUid") or self_info.get("selfUin") or "bot")
        bot_name = str(self_info.get("selfName") or "Bot")
        base_ts = _to_timestamp(self_info.get("exportTime"), default=time.time())
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                continue
            instruction = _clean_text(
                "\n".join(
                    part
                    for part in [str(item.get("instruction") or "").strip(), str(item.get("input") or "").strip()]
                    if part
                )
            )
            output = _clean_text(str(item.get("output") or ""))
            pair_id = str(item.get("id") or index)
            timestamp = int(base_ts) + index * 2
            if len(instruction) >= min_text_length:
                yield self._build_message(
                    source_id=f"train:{pair_id}:instruction",
                    sender_id="training_user",
                    sender_name="训练集用户",
                    message=instruction,
                    group_id=group_id,
                    timestamp=timestamp,
                    platform="qq_training",
                    source_type="alpaca_training",
                    metadata={"source_label": source_label, "pair_index": index},
                )
            if len(output) >= min_text_length:
                yield self._build_message(
                    source_id=f"train:{pair_id}:output",
                    sender_id=bot_uid,
                    sender_name=bot_name,
                    message=output,
                    group_id=group_id,
                    timestamp=timestamp + 1,
                    platform="qq_training",
                    is_bot=True,
                    source_type="alpaca_training",
                    metadata={"source_label": source_label, "pair_index": index},
                )

    def _iter_text_export(
        self,
        path: Path,
        *,
        group_id: str,
        min_text_length: int,
    ) -> Iterator[QQChatMessage]:
        lines = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
        yield from self._iter_text_blocks(lines, group_id=group_id, source_label=str(path), min_text_length=min_text_length)

    def _iter_text_blocks(
        self,
        lines: list[str],
        *,
        group_id: str,
        source_label: str,
        min_text_length: int,
    ) -> Iterator[QQChatMessage]:
        current: dict[str, Any] | None = None
        for line in lines:
            header = _parse_text_header(line)
            if header:
                if current:
                    message = self._message_from_text_block(current, group_id=group_id, source_label=source_label, min_text_length=min_text_length)
                    if message:
                        yield message
                current = {"timestamp": header[0], "sender": header[1], "lines": []}
                continue
            if current is not None:
                current["lines"].append(line)
        if current:
            message = self._message_from_text_block(current, group_id=group_id, source_label=source_label, min_text_length=min_text_length)
            if message:
                yield message

    def _message_from_text_block(
        self,
        block: Mapping[str, Any],
        *,
        group_id: str,
        source_label: str,
        min_text_length: int,
    ) -> Optional[QQChatMessage]:
        text = _clean_text("\n".join(str(line) for line in block.get("lines", [])))
        if len(text) < min_text_length:
            return None
        sender = str(block.get("sender") or "unknown").strip()
        timestamp = int(block.get("timestamp") or time.time())
        sender_id = _sender_id_from_text(sender)
        return self._build_message(
            source_id=f"txt:{source_label}:{timestamp}:{sender}:{text[:64]}",
            sender_id=sender_id,
            sender_name=_sender_name_from_text(sender),
            message=text,
            group_id=group_id,
            timestamp=timestamp,
            platform="qq_text",
            source_type="qq_text",
            metadata={"source_label": source_label},
        )

    def _message_from_qce(
        self,
        raw: Any,
        *,
        group_id: str,
        self_uid: str,
        min_text_length: int,
    ) -> Optional[QQChatMessage]:
        if not isinstance(raw, Mapping):
            return None
        if raw.get("system") or raw.get("recalled"):
            return None
        msg_type = str(raw.get("type") or "").lower()
        if msg_type and msg_type not in {"text", "reply"}:
            return None

        message = _extract_qce_text(raw.get("content"))
        message = _clean_text(message)
        if len(message) < min_text_length:
            return None
        if message.startswith(("/", ".")):
            return None

        sender = raw.get("sender") if isinstance(raw.get("sender"), Mapping) else {}
        sender_id = str(sender.get("uid") or sender.get("uin") or "unknown")
        sender_name = str(
            sender.get("groupCard")
            or sender.get("name")
            or sender.get("nickname")
            or sender_id
        )
        timestamp = _to_timestamp(raw.get("timestamp") or raw.get("time"), default=time.time())
        source_id = str(raw.get("id") or raw.get("msgId") or raw.get("seq") or "")
        reply_to = _extract_qce_reply_to(raw.get("content"))
        return self._build_message(
            source_id=source_id or f"{sender_id}:{timestamp}:{message[:64]}",
            sender_id=sender_id,
            sender_name=sender_name,
            message=message,
            group_id=group_id,
            timestamp=int(timestamp),
            platform="qq",
            reply_to=reply_to,
            is_bot=bool(self_uid and sender_id == self_uid),
            source_type="qce",
            metadata={
                "qce_type": raw.get("type"),
                "qce_seq": raw.get("seq"),
            },
        )

    def _build_message(
        self,
        *,
        source_id: str,
        sender_id: str,
        sender_name: str,
        message: str,
        group_id: str,
        timestamp: int,
        platform: str,
        reply_to: Optional[str] = None,
        is_bot: bool = False,
        source_type: str = "qce",
        metadata: Optional[dict[str, Any]] = None,
    ) -> QQChatMessage:
        msg = QQChatMessage(
            source_id=str(source_id or ""),
            sender_id=str(sender_id or ""),
            sender_name=str(sender_name or sender_id or "unknown"),
            message=str(message or ""),
            group_id=str(group_id or "global"),
            timestamp=int(timestamp or time.time()),
            platform=platform,
            reply_to=reply_to,
            is_bot=is_bot,
            source_type=source_type,
            metadata=metadata or {},
        )
        msg.message_id = _stable_message_id(msg)
        return msg

    @staticmethod
    def _group_id(source: QQChatSource, default_group_id: str = "") -> str:
        explicit = str(default_group_id or "").strip()
        if explicit:
            return explicit
        info = _chat_info(source.manifest)
        return str(info.get("uin") or info.get("id") or info.get("name") or "global")


def qq_chat_import_destinations() -> dict[str, str]:
    return {
        "raw_messages": "raw_messages",
        "learning_queue": "raw_messages.processed=false",
    }


def _empty_summary(source: QQChatSource, *, default_group_id: str) -> dict[str, Any]:
    chat_info = _chat_info(source.manifest)
    return {
        "version": QQ_HISTORY_EXPORT_VERSION,
        "source": QQ_HISTORY_SOURCE,
        "source_format": source.source_format,
        "source_paths": source.source_paths,
        "chat_info": chat_info,
        "group_id": str(default_group_id or chat_info.get("name") or "global"),
        "counts": {
            "messages": 0,
            "bot_messages": 0,
            "unique_senders": 0,
            "content_chars": 0,
            "estimated_tokens": 0,
        },
        "time_range": {"start": None, "end": None},
        "senders": [],
        "samples": {"messages": []},
        "truncated": False,
        "destinations": qq_chat_import_destinations(),
    }


def _add_summary_message(summary: dict[str, Any], message: QQChatMessage) -> None:
    counts = summary["counts"]
    counts["messages"] += 1
    counts["bot_messages"] += 1 if message.is_bot else 0
    counts["content_chars"] += len(message.message)
    counts["estimated_tokens"] = max(1, counts["content_chars"] // 4) if counts["content_chars"] else 0
    if len(summary["samples"]["messages"]) < 5:
        summary["samples"]["messages"].append(message.sample())

    start = summary["time_range"]["start"]
    end = summary["time_range"]["end"]
    summary["time_range"]["start"] = message.timestamp if start is None else min(start, message.timestamp)
    summary["time_range"]["end"] = message.timestamp if end is None else max(end, message.timestamp)

    sender_counts = summary.setdefault("_sender_counts", {})
    sender_key = (message.sender_id, message.sender_name)
    sender_counts[sender_key] = sender_counts.get(sender_key, 0) + 1
    top = sorted(sender_counts.items(), key=lambda item: item[1], reverse=True)[:10]
    summary["senders"] = [
        {"sender_id": sender_id, "sender_name": sender_name, "message_count": count}
        for (sender_id, sender_name), count in top
    ]
    counts["unique_senders"] = len(sender_counts)
    summary.pop("_sender_counts", None)
    summary["_sender_counts"] = sender_counts


def _chat_info(manifest: Mapping[str, Any]) -> dict[str, Any]:
    info = manifest.get("chatInfo") if isinstance(manifest, Mapping) else {}
    return dict(info) if isinstance(info, Mapping) else {}


def _extract_qce_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, Mapping):
        return ""

    elements = content.get("elements")
    if isinstance(elements, list):
        parts: list[str] = []
        for element in elements:
            if not isinstance(element, Mapping):
                continue
            elem_type = str(element.get("type") or "")
            data = element.get("data") if isinstance(element.get("data"), Mapping) else {}
            if elem_type == "text" and data.get("text") is not None:
                parts.append(str(data.get("text")))
            elif elem_type in {"at", "mention"}:
                name = data.get("name") or data.get("uin") or data.get("uid")
                if name:
                    parts.append(f"@{name}")
        text = "".join(parts).strip()
        if text:
            return text

    if content.get("text") is not None:
        return str(content.get("text") or "")
    if content.get("html") is not None:
        return _html_to_text(str(content.get("html") or ""))
    return ""


def _extract_qce_reply_to(content: Any) -> Optional[str]:
    if not isinstance(content, Mapping):
        return None
    elements = content.get("elements")
    if not isinstance(elements, list):
        return None
    for element in elements:
        if not isinstance(element, Mapping) or element.get("type") != "reply":
            continue
        data = element.get("data") if isinstance(element.get("data"), Mapping) else {}
        value = data.get("referencedMessageId") or data.get("messageId")
        if value:
            return str(value)
    return None


_PLACEHOLDER_RE = re.compile(r"\[(?:图片|表情|文件|语音|视频|回复消息)[^\]]*\]")
_URL_RE = re.compile(r"https?://\S+")


def _clean_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = _PLACEHOLDER_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _stable_message_id(message: QQChatMessage) -> str:
    base = "|".join(
        [
            message.source_type,
            message.group_id,
            message.source_id,
            message.sender_id,
            str(message.timestamp),
            message.message,
        ]
    )
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return f"{QQ_HISTORY_MESSAGE_PREFIX}:{digest}"


def _read_json_file(path: Path) -> Any:
    return _json_decode(path.read_text(encoding="utf-8-sig"))


def _json_decode(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return None
    return json.loads(str(value))


def _payload_format(payload: Any) -> str:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return "json_text"
    if isinstance(payload, list) and _looks_like_training_items(payload):
        return "alpaca_training_json"
    if isinstance(payload, list):
        return "qce_json"
    if isinstance(payload, Mapping):
        if payload.get("source") == QQ_HISTORY_SOURCE:
            return "qq_history_package"
        if isinstance(payload.get("chatInfo"), Mapping):
            return "qce_json"
        if _looks_like_training_items([payload]):
            return "alpaca_training_json"
    return "json"


def _looks_like_training_items(items: list[Any]) -> bool:
    return bool(items) and all(
        isinstance(item, Mapping) and ("instruction" in item or "output" in item)
        for item in items[:5]
    )


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


_TEXT_HEADER_RE = re.compile(
    r"^(?P<date>\d{4}[-/]\d{1,2}[-/]\d{1,2})\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s+"
    r"(?P<sender>.+?)\s*$"
)


def _parse_text_header(line: str) -> Optional[tuple[int, str]]:
    match = _TEXT_HEADER_RE.match(str(line or "").strip())
    if not match:
        return None
    dt_text = f"{match.group('date').replace('/', '-')} {match.group('time')}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return int(datetime.strptime(dt_text, fmt).replace(tzinfo=timezone.utc).timestamp()), match.group("sender")
        except ValueError:
            continue
    return None


def _sender_id_from_text(sender: str) -> str:
    match = re.search(r"\(([^()]+)\)\s*$", sender)
    return str(match.group(1) if match else sender).strip() or "unknown"


def _sender_name_from_text(sender: str) -> str:
    return re.sub(r"\s*\([^()]+\)\s*$", "", sender).strip() or sender or "unknown"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return html.unescape("".join(parser.parts))


def _preview_text(value: str, *, limit: int = 120) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}..."


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


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
