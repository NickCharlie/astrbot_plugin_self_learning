"""
社交图谱分享服务 - 生成/校验只读分享链接
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional, Tuple

from astrbot.api import logger

try:
    import fcntl  # type: ignore
except Exception:
    fcntl = None

try:
    import msvcrt  # type: ignore
except Exception:
    msvcrt = None


class GraphShareService:
    """管理社交图谱分享 token 的本地存储与校验。"""

    MIN_EXPIRES_HOURS = 1
    MAX_EXPIRES_HOURS = 720

    _file_lock = threading.Lock()
    _token_pattern = re.compile(r"^[A-Za-z0-9_-]{20,}$")
    _store_filename = "social_graph_shares.json"

    def __init__(self, container):
        self.container = container
        self._store_path = self._resolve_store_path()
        self._lock_path = f"{self._store_path}.lock"

    def _resolve_store_path(self) -> str:
        plugin_config = getattr(self.container, "plugin_config", None)
        data_dir = getattr(plugin_config, "data_dir", None) if plugin_config else None

        if not data_dir:
            plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            data_dir = os.path.join(plugin_root, "data")

        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, self._store_filename)

    @staticmethod
    def _now_ts() -> int:
        return int(time.time())

    @staticmethod
    def _to_iso(ts: int) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

    def _default_store(self) -> Dict[str, Any]:
        return {"version": 1, "shares": {}}

    @contextmanager
    def _advisory_file_lock(self):
        """
        进程级建议锁（best effort）。
        在多线程锁之外，尽量降低多进程并发读写 JSON 的冲突风险。
        """
        lock_file = None
        try:
            lock_file = open(self._lock_path, "a+b")
            lock_file.seek(0)
            lock_file.write(b"0")
            lock_file.flush()
            lock_file.seek(0)

            if msvcrt is not None:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            elif fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

            yield
        finally:
            if lock_file is not None:
                try:
                    if msvcrt is not None:
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    elif fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                lock_file.close()

    def _load_store(self) -> Dict[str, Any]:
        if not os.path.exists(self._store_path):
            return self._default_store()

        try:
            with open(self._store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return self._default_store()
                shares = data.get("shares", {})
                if not isinstance(shares, dict):
                    data["shares"] = {}
                return data
        except Exception as e:
            logger.warning(f"[GraphShare] 读取分享存储失败，使用空存储: {e}")
            return self._default_store()

    def _save_store(self, data: Dict[str, Any]) -> None:
        temp_path = f"{self._store_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, self._store_path)

    def _cleanup_expired(self, data: Dict[str, Any]) -> bool:
        now = self._now_ts()
        changed = False

        shares = data.get("shares", {})
        for _, share in shares.items():
            if not isinstance(share, dict):
                continue
            if share.get("revoked", False):
                continue
            expires_at = int(share.get("expires_at", 0) or 0)
            if expires_at and expires_at <= now:
                share["revoked"] = True
                share["revoked_reason"] = "expired"
                share["revoked_at"] = self._to_iso(now)
                changed = True

        return changed

    def is_valid_token_format(self, token: str) -> bool:
        return bool(token and self._token_pattern.match(token))

    def create_share(
        self,
        group_id: str,
        expires_hours: int = 168,
        created_by: str = "admin",
    ) -> Dict[str, Any]:
        expires_hours = max(
            self.MIN_EXPIRES_HOURS,
            min(self.MAX_EXPIRES_HOURS, int(expires_hours)),
        )
        now = self._now_ts()
        expires_at = now + (expires_hours * 3600)

        with self._file_lock:
            with self._advisory_file_lock():
                store = self._load_store()
                if self._cleanup_expired(store):
                    self._save_store(store)

                shares = store.setdefault("shares", {})
                token = secrets.token_urlsafe(32)
                while token in shares:
                    token = secrets.token_urlsafe(32)

                share = {
                    "token": token,
                    "group_id": group_id,
                    "created_at": self._to_iso(now),
                    "created_by": created_by,
                    "expires_at": expires_at,
                    "expires_at_iso": self._to_iso(expires_at),
                    "expires_hours": expires_hours,
                    "revoked": False,
                    "revoked_reason": "",
                    "view_count": 0,
                    "last_viewed_at": None,
                }
                shares[token] = share
                self._save_store(store)

        return share

    def get_share(
        self, token: str, increment_view: bool = False
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self.is_valid_token_format(token):
            return None, "invalid_token"

        with self._file_lock:
            with self._advisory_file_lock():
                store = self._load_store()
                shares = store.get("shares", {})
                share = shares.get(token)
                if not isinstance(share, dict):
                    return None, "not_found"

                if share.get("revoked", False):
                    return None, "revoked"

                now = self._now_ts()
                expires_at = int(share.get("expires_at", 0) or 0)
                if expires_at and expires_at <= now:
                    share["revoked"] = True
                    share["revoked_reason"] = "expired"
                    share["revoked_at"] = self._to_iso(now)
                    self._save_store(store)
                    return None, "expired"

                if increment_view:
                    share["view_count"] = int(share.get("view_count", 0) or 0) + 1
                    share["last_viewed_at"] = self._to_iso(now)
                    self._save_store(store)

                return dict(share), "ok"

    def revoke_share(self, token: str, reason: str = "manual") -> Tuple[bool, str]:
        if not self.is_valid_token_format(token):
            return False, "invalid_token"

        with self._file_lock:
            with self._advisory_file_lock():
                store = self._load_store()
                shares = store.get("shares", {})
                share = shares.get(token)
                if not isinstance(share, dict):
                    return False, "not_found"

                if share.get("revoked", False):
                    return True, "already_revoked"

                share["revoked"] = True
                share["revoked_reason"] = reason
                share["revoked_at"] = self._to_iso(self._now_ts())
                self._save_store(store)
                return True, "revoked"
