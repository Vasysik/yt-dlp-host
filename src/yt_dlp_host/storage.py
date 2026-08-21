from __future__ import annotations

import copy
import fcntl
import json
import os
import secrets
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

from .config import Settings
from .db import Database, QuotaExceeded, utc_now
from .models import ADMIN_PERMISSIONS, TaskStatus


@runtime_checkable
class StateBackend(Protocol):
    """State operations used by the HTTP API and downloader worker."""

    settings: Settings

    def initialize(self) -> None: ...
    def get_metadata(self, key: str) -> str | None: ...
    def set_metadata(self, key: str, value: str) -> None: ...
    def bootstrap_admin(self) -> tuple[str, bool]: ...
    def create_key(self, name: str, permissions: list[str], quota_bytes: int | None = None) -> str: ...
    def import_key(self, name: str, secret: str, permissions: list[str], quota_bytes: int, last_access: str | None) -> None: ...
    def delete_key(self, name: str) -> bool: ...
    def key_by_secret(self, secret: str | None) -> dict[str, Any] | None: ...
    def key_by_name(self, name: str) -> dict[str, Any] | None: ...
    def list_keys(self) -> list[dict[str, Any]]: ...
    def touch_key(self, name: str) -> None: ...
    def check_rate_limit(self, key_name: str) -> bool: ...
    def create_task(self, task_id: str, key_name: str, task_type: str, url: str, payload: dict[str, Any]) -> None: ...
    def import_task(self, task_id: str, data: dict[str, Any]) -> None: ...
    def task(self, task_id: str) -> dict[str, Any] | None: ...
    def legacy_task(self, task_id: str) -> dict[str, Any] | None: ...
    def claim_next_task(self, worker_id: str) -> dict[str, Any] | None: ...
    def extend_lease(self, task_id: str, worker_id: str) -> None: ...
    def complete_task(self, task_id: str, file_path: str | None, actual_bytes: int = 0) -> None: ...
    def fail_task(self, task_id: str, error: str) -> None: ...
    def quota_headroom(self, key_name: str, task_id: str | None = None) -> int: ...
    def resize_quota_reservation(self, task_id: str, key_name: str, requested_bytes: int) -> None: ...
    def finalize_quota(self, task_id: str, key_name: str, actual_bytes: int) -> None: ...
    def release_quota(self, task_id: str) -> None: ...
    def legacy_memory_usage(self, key_name: str) -> list[dict[str, Any]]: ...
    def expired_tasks(self) -> list[str]: ...
    def delete_task(self, task_id: str) -> None: ...


class JsonDatabase:
    """Legacy JSON state backend with process-safe locking and atomic file writes.

    `api_keys.json` and `tasks.json` remain in the original public format. Extra
    bookkeeping required by the modern worker (leases, rolling rate events and
    quota reservation state) lives in a hidden sidecar JSON file.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys_path = settings.legacy_keys_file
        self.tasks_path = settings.legacy_tasks_file
        self.state_path = settings.json_state_file
        self.lock_path = self.state_path.with_suffix(self.state_path.suffix + ".lock")

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "metadata": {},
            "rate_events": {},
            "task_meta": {},
            "quota_reservations": {},
        }

    @contextmanager
    def _lock(self, *, exclusive: bool) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _load_object(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as fh:
                value = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON state file: {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSON state file must contain an object: {path}")
        return value

    @staticmethod
    def _atomic_write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        with temp.open("w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False, indent=4)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)

    def _load_state(self) -> dict[str, Any]:
        raw = self._load_object(self.state_path)
        state = self._default_state()
        for key in state:
            value = raw.get(key, {})
            if isinstance(value, dict):
                state[key] = value
        return state

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _import_legacy_usage(self, keys: dict[str, Any], state: dict[str, Any]) -> bool:
        reservations = state["quota_reservations"]
        if reservations:
            return False
        changed = False
        for key_name, info in keys.items():
            if not isinstance(info, dict):
                continue
            usage = info.get("memory_usage", [])
            if not isinstance(usage, list):
                continue
            for index, entry in enumerate(usage):
                if not isinstance(entry, dict):
                    continue
                try:
                    size = max(0, int(entry.get("size", 0)))
                except (TypeError, ValueError):
                    continue
                dt = self._parse_iso(entry.get("timestamp"))
                created_at = dt.timestamp() if dt else time.time()
                task_id = str(entry.get("task_id") or f"legacy-{index}")
                reservation_id = task_id
                if reservation_id in reservations:
                    reservation_id = f"legacy:{key_name}:{index}:{task_id}"
                reservations[reservation_id] = {
                    "task_id": task_id,
                    "key_name": key_name,
                    "size_bytes": size,
                    "created_at": created_at,
                    "finalized": True,
                }
                changed = True
        return changed

    def _cleanup_quota(self, state: dict[str, Any]) -> None:
        cutoff = time.time() - self.settings.quota_window_minutes * 60
        reservations = state["quota_reservations"]
        for reservation_id, entry in list(reservations.items()):
            if not isinstance(entry, dict):
                reservations.pop(reservation_id, None)
                continue
            if bool(entry.get("finalized")) and float(entry.get("created_at", 0)) < cutoff:
                reservations.pop(reservation_id, None)

    def _sync_memory_usage(self, keys: dict[str, Any], state: dict[str, Any]) -> None:
        self._cleanup_quota(state)
        now = time.time()
        per_key: dict[str, list[dict[str, Any]]] = {name: [] for name in keys}
        for reservation_id, entry in state["quota_reservations"].items():
            if not isinstance(entry, dict):
                continue
            key_name = str(entry.get("key_name", ""))
            if key_name not in per_key:
                continue
            finalized = bool(entry.get("finalized"))
            stamp = float(entry.get("created_at", now)) if finalized else now
            per_key[key_name].append(
                {
                    "size": int(entry.get("size_bytes", 0)),
                    "timestamp": datetime.fromtimestamp(stamp, UTC).isoformat(),
                    "task_id": str(entry.get("task_id", reservation_id)),
                }
            )
        for key_name, info in keys.items():
            if isinstance(info, dict):
                info["memory_usage"] = per_key.get(key_name, [])

    def initialize(self) -> None:
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            tasks = self._load_object(self.tasks_path)
            state = self._load_state()
            changed_state = self._import_legacy_usage(keys, state)
            now = utc_now()
            for task_id in tasks:
                if task_id not in state["task_meta"]:
                    state["task_meta"][task_id] = {
                        "created_at": now,
                        "updated_at": now,
                        "actual_bytes": 0,
                        "attempts": 0,
                        "lease_owner": None,
                        "lease_expires_at": None,
                    }
                    changed_state = True
            if not self.keys_path.exists():
                self._atomic_write(self.keys_path, keys)
            if not self.tasks_path.exists():
                self._atomic_write(self.tasks_path, tasks)
            if changed_state or not self.state_path.exists():
                self._sync_memory_usage(keys, state)
                self._atomic_write(self.keys_path, keys)
                self._atomic_write(self.state_path, state)

    # Metadata exists only in the hidden sidecar. It is intentionally not
    # exposed in the legacy JSON files.
    def get_metadata(self, key: str) -> str | None:
        with self._lock(exclusive=False):
            value = self._load_state()["metadata"].get(key)
        return None if value is None else str(value)

    def set_metadata(self, key: str, value: str) -> None:
        with self._lock(exclusive=True):
            state = self._load_state()
            state["metadata"][key] = value
            self._atomic_write(self.state_path, state)

    # --- API keys -----------------------------------------------------
    def count_keys(self) -> int:
        with self._lock(exclusive=False):
            return len(self._load_object(self.keys_path))

    def bootstrap_admin(self) -> tuple[str, bool]:
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            admin = keys.get("admin")
            if isinstance(admin, dict) and admin.get("key"):
                return str(admin["key"]), False
            secret = self.settings.admin_api_key or secrets.token_urlsafe(32)
            now = utc_now()
            keys["admin"] = {
                "key": secret,
                "permissions": sorted(ADMIN_PERMISSIONS),
                "memory_quota": self.settings.default_quota_bytes,
                "memory_usage": [],
                "last_access": now,
            }
            self._atomic_write(self.keys_path, keys)
            return secret, True

    def create_key(self, name: str, permissions: list[str], quota_bytes: int | None = None) -> str:
        secret = secrets.token_urlsafe(32)
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            keys[name] = {
                "key": secret,
                "permissions": list(permissions),
                "memory_quota": int(quota_bytes or self.settings.default_quota_bytes),
                "memory_usage": [],
                "last_access": utc_now(),
            }
            self._atomic_write(self.keys_path, keys)
        return secret

    def import_key(self, name: str, secret: str, permissions: list[str], quota_bytes: int, last_access: str | None) -> None:
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            if name in keys:
                return
            keys[name] = {
                "key": secret,
                "permissions": list(permissions),
                "memory_quota": int(quota_bytes),
                "memory_usage": [],
                "last_access": last_access,
            }
            self._atomic_write(self.keys_path, keys)

    def delete_key(self, name: str) -> bool:
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            if name not in keys:
                return False
            del keys[name]
            state = self._load_state()
            state["rate_events"].pop(name, None)
            for reservation_id, entry in list(state["quota_reservations"].items()):
                if isinstance(entry, dict) and entry.get("key_name") == name:
                    state["quota_reservations"].pop(reservation_id, None)
            self._sync_memory_usage(keys, state)
            self._atomic_write(self.keys_path, keys)
            self._atomic_write(self.state_path, state)
            return True

    @staticmethod
    def _decode_key(name: str, info: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": name,
            "key": str(info.get("key", "")),
            "permissions": list(info.get("permissions", [])),
            "memory_quota": int(info.get("memory_quota", 0)),
            "last_access": info.get("last_access"),
        }

    def key_by_secret(self, secret: str | None) -> dict[str, Any] | None:
        if not secret:
            return None
        with self._lock(exclusive=False):
            keys = self._load_object(self.keys_path)
        for name, info in keys.items():
            if isinstance(info, dict) and info.get("key") == secret:
                return self._decode_key(name, info)
        return None

    def key_by_name(self, name: str) -> dict[str, Any] | None:
        with self._lock(exclusive=False):
            info = self._load_object(self.keys_path).get(name)
        return self._decode_key(name, info) if isinstance(info, dict) else None

    def list_keys(self) -> list[dict[str, Any]]:
        with self._lock(exclusive=False):
            keys = self._load_object(self.keys_path)
        return [self._decode_key(name, info) for name, info in sorted(keys.items()) if isinstance(info, dict)]

    def touch_key(self, name: str) -> None:
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            info = keys.get(name)
            if isinstance(info, dict):
                info["last_access"] = utc_now()
                self._atomic_write(self.keys_path, keys)

    def check_rate_limit(self, key_name: str) -> bool:
        cutoff = time.time() - self.settings.request_window_minutes * 60
        with self._lock(exclusive=True):
            state = self._load_state()
            for name, raw_events in list(state["rate_events"].items()):
                cleaned: list[float] = []
                if isinstance(raw_events, list):
                    for value in raw_events:
                        try:
                            timestamp = float(value)
                        except (TypeError, ValueError):
                            continue
                        if timestamp >= cutoff:
                            cleaned.append(timestamp)
                if cleaned:
                    state["rate_events"][name] = cleaned
                else:
                    state["rate_events"].pop(name, None)
            events = list(state["rate_events"].get(key_name, []))
            if len(events) >= self.settings.request_limit:
                state["rate_events"][key_name] = events
                self._atomic_write(self.state_path, state)
                return False
            events.append(time.time())
            state["rate_events"][key_name] = events
            self._atomic_write(self.state_path, state)
            return True

    # --- tasks --------------------------------------------------------
    def create_task(self, task_id: str, key_name: str, task_type: str, url: str, payload: dict[str, Any]) -> None:
        now = utc_now()
        legacy = {
            "key_name": key_name,
            "status": TaskStatus.WAITING.value,
            "task_type": task_type,
            "url": url,
        }
        legacy.update(copy.deepcopy(payload))
        with self._lock(exclusive=True):
            tasks = self._load_object(self.tasks_path)
            state = self._load_state()
            if task_id in tasks:
                raise ValueError(f"Task already exists: {task_id}")
            tasks[task_id] = legacy
            state["task_meta"][task_id] = {
                "created_at": now,
                "updated_at": now,
                "actual_bytes": 0,
                "attempts": 0,
                "lease_owner": None,
                "lease_expires_at": None,
            }
            self._atomic_write(self.tasks_path, tasks)
            self._atomic_write(self.state_path, state)

    def import_task(self, task_id: str, data: dict[str, Any]) -> None:
        now = utc_now()
        legacy = copy.deepcopy(data)
        if legacy.get("status") == TaskStatus.PROCESSING.value:
            legacy["status"] = TaskStatus.WAITING.value
        with self._lock(exclusive=True):
            tasks = self._load_object(self.tasks_path)
            if task_id in tasks:
                return
            state = self._load_state()
            tasks[task_id] = legacy
            state["task_meta"][task_id] = {
                "created_at": now,
                "updated_at": now,
                "actual_bytes": 0,
                "attempts": 0,
                "lease_owner": None,
                "lease_expires_at": None,
            }
            self._atomic_write(self.tasks_path, tasks)
            self._atomic_write(self.state_path, state)

    def _decode_task(self, task_id: str, legacy: dict[str, Any], meta: dict[str, Any] | None) -> dict[str, Any]:
        known = {"key_name", "status", "task_type", "url", "completed_time", "error", "file"}
        payload = {key: copy.deepcopy(value) for key, value in legacy.items() if key not in known}
        meta = meta or {}
        created = str(meta.get("created_at") or utc_now())
        return {
            "task_id": task_id,
            "key_name": legacy.get("key_name", "admin"),
            "status": legacy.get("status", TaskStatus.ERROR.value),
            "task_type": legacy.get("task_type", "get_info"),
            "url": legacy.get("url", ""),
            "payload": payload,
            "created_at": created,
            "updated_at": str(meta.get("updated_at") or created),
            "completed_time": legacy.get("completed_time"),
            "error": legacy.get("error"),
            "file": legacy.get("file"),
            "actual_bytes": int(meta.get("actual_bytes", 0) or 0),
            "attempts": int(meta.get("attempts", 0) or 0),
            "lease_owner": meta.get("lease_owner"),
            "lease_expires_at": meta.get("lease_expires_at"),
        }

    def task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock(exclusive=False):
            tasks = self._load_object(self.tasks_path)
            legacy = tasks.get(task_id)
            if not isinstance(legacy, dict):
                return None
            meta = self._load_state()["task_meta"].get(task_id)
            return self._decode_task(task_id, legacy, meta if isinstance(meta, dict) else None)

    def legacy_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock(exclusive=False):
            legacy = self._load_object(self.tasks_path).get(task_id)
        return copy.deepcopy(legacy) if isinstance(legacy, dict) else None

    def claim_next_task(self, worker_id: str) -> dict[str, Any] | None:
        now_ts = time.time()
        now_iso = utc_now()
        with self._lock(exclusive=True):
            tasks = self._load_object(self.tasks_path)
            state = self._load_state()
            meta_by_task = state["task_meta"]

            # Leases are kept in the sidecar so tasks.json remains compatible
            # with the old server. A legacy `processing` task without a lease is
            # considered abandoned and is made available again.
            changed = False
            for task_id, legacy in tasks.items():
                if not isinstance(legacy, dict) or legacy.get("status") != TaskStatus.PROCESSING.value:
                    continue
                meta = meta_by_task.get(task_id)
                if not isinstance(meta, dict):
                    meta = {}
                    meta_by_task[task_id] = meta
                lease = meta.get("lease_expires_at")
                if lease is None or float(lease) < now_ts:
                    legacy["status"] = TaskStatus.WAITING.value
                    meta["lease_owner"] = None
                    meta["lease_expires_at"] = None
                    meta["updated_at"] = now_iso
                    changed = True

            candidates: list[tuple[str, str]] = []
            for task_id, legacy in tasks.items():
                if isinstance(legacy, dict) and legacy.get("status") == TaskStatus.WAITING.value:
                    meta = meta_by_task.get(task_id)
                    created = meta.get("created_at", "") if isinstance(meta, dict) else ""
                    candidates.append((str(created), task_id))
            if not candidates:
                if changed:
                    self._atomic_write(self.tasks_path, tasks)
                    self._atomic_write(self.state_path, state)
                return None

            _, task_id = min(candidates)
            legacy = tasks[task_id]
            assert isinstance(legacy, dict)
            meta = meta_by_task.setdefault(task_id, {})
            legacy["status"] = TaskStatus.PROCESSING.value
            meta["created_at"] = meta.get("created_at") or now_iso
            meta["updated_at"] = now_iso
            meta["attempts"] = int(meta.get("attempts", 0) or 0) + 1
            meta["lease_owner"] = worker_id
            meta["lease_expires_at"] = now_ts + self.settings.worker_lease_seconds
            self._atomic_write(self.tasks_path, tasks)
            self._atomic_write(self.state_path, state)
            return self._decode_task(task_id, legacy, meta)

    def extend_lease(self, task_id: str, worker_id: str) -> None:
        with self._lock(exclusive=True):
            tasks = self._load_object(self.tasks_path)
            legacy = tasks.get(task_id)
            if not isinstance(legacy, dict) or legacy.get("status") != TaskStatus.PROCESSING.value:
                return
            state = self._load_state()
            meta = state["task_meta"].get(task_id)
            if not isinstance(meta, dict) or meta.get("lease_owner") != worker_id:
                return
            meta["lease_expires_at"] = time.time() + self.settings.worker_lease_seconds
            meta["updated_at"] = utc_now()
            self._atomic_write(self.state_path, state)

    def complete_task(self, task_id: str, file_path: str | None, actual_bytes: int = 0) -> None:
        now = utc_now()
        with self._lock(exclusive=True):
            tasks = self._load_object(self.tasks_path)
            legacy = tasks.get(task_id)
            if not isinstance(legacy, dict):
                return
            state = self._load_state()
            meta = state["task_meta"].setdefault(task_id, {})
            legacy["status"] = TaskStatus.COMPLETED.value
            legacy["completed_time"] = now
            legacy.pop("error", None)
            if file_path is None:
                legacy.pop("file", None)
            else:
                legacy["file"] = file_path
            meta["updated_at"] = now
            meta["actual_bytes"] = int(actual_bytes)
            meta["lease_owner"] = None
            meta["lease_expires_at"] = None
            self._atomic_write(self.tasks_path, tasks)
            self._atomic_write(self.state_path, state)

    def fail_task(self, task_id: str, error: str) -> None:
        now = utc_now()
        with self._lock(exclusive=True):
            tasks = self._load_object(self.tasks_path)
            state = self._load_state()
            legacy = tasks.get(task_id)
            if isinstance(legacy, dict):
                legacy["status"] = TaskStatus.ERROR.value
                legacy["completed_time"] = now
                legacy["error"] = error[:4000]
            meta = state["task_meta"].setdefault(task_id, {})
            meta["updated_at"] = now
            meta["lease_owner"] = None
            meta["lease_expires_at"] = None
            state["quota_reservations"].pop(task_id, None)
            keys = self._load_object(self.keys_path)
            self._sync_memory_usage(keys, state)
            self._atomic_write(self.tasks_path, tasks)
            self._atomic_write(self.keys_path, keys)
            self._atomic_write(self.state_path, state)

    # --- rolling quota -----------------------------------------------
    def quota_headroom(self, key_name: str, task_id: str | None = None) -> int:
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            key = keys.get(key_name)
            if not isinstance(key, dict):
                raise QuotaExceeded("Invalid API key")
            state = self._load_state()
            self._cleanup_quota(state)
            user_total = 0
            global_total = 0
            for reservation_id, entry in state["quota_reservations"].items():
                if reservation_id == task_id or not isinstance(entry, dict):
                    continue
                size = int(entry.get("size_bytes", 0))
                global_total += size
                if entry.get("key_name") == key_name:
                    user_total += size
            self._sync_memory_usage(keys, state)
            self._atomic_write(self.keys_path, keys)
            self._atomic_write(self.state_path, state)
            return max(
                0,
                min(
                    int(key.get("memory_quota", self.settings.default_quota_bytes)) - user_total,
                    self.settings.server_quota_bytes - global_total,
                ),
            )

    def resize_quota_reservation(self, task_id: str, key_name: str, requested_bytes: int) -> None:
        requested = max(0, int(requested_bytes))
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            key = keys.get(key_name)
            if not isinstance(key, dict):
                raise QuotaExceeded("Invalid API key")
            state = self._load_state()
            self._cleanup_quota(state)
            reservations = state["quota_reservations"]
            existing = reservations.get(task_id)
            old = int(existing.get("size_bytes", 0)) if isinstance(existing, dict) else 0
            if requested <= old:
                return

            user_total = 0
            global_total = 0
            for reservation_id, entry in reservations.items():
                if reservation_id == task_id or not isinstance(entry, dict):
                    continue
                size = int(entry.get("size_bytes", 0))
                global_total += size
                if entry.get("key_name") == key_name:
                    user_total += size
            quota = int(key.get("memory_quota", self.settings.default_quota_bytes))
            if user_total + requested > quota:
                raise QuotaExceeded(
                    f"User quota exceeded. Current: {user_total / 1024**3:.2f}GB, "
                    f"Requested: {requested / 1024**3:.2f}GB, Quota: {quota / 1024**3:.2f}GB"
                )
            if global_total + requested > self.settings.server_quota_bytes:
                raise QuotaExceeded(
                    "Server memory limit exceeded. "
                    f"Current: {global_total / 1024**3:.2f}GB, "
                    f"Requested: {requested / 1024**3:.2f}GB, "
                    f"Available: {max(0, self.settings.server_quota_bytes - global_total) / 1024**3:.2f}GB"
                )
            reservations[task_id] = {
                "task_id": task_id,
                "key_name": key_name,
                "size_bytes": requested,
                "created_at": float(existing.get("created_at", time.time())) if isinstance(existing, dict) else time.time(),
                "finalized": False,
            }
            self._sync_memory_usage(keys, state)
            self._atomic_write(self.keys_path, keys)
            self._atomic_write(self.state_path, state)

    def finalize_quota(self, task_id: str, key_name: str, actual_bytes: int) -> None:
        self.resize_quota_reservation(task_id, key_name, actual_bytes)
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            state = self._load_state()
            reservation = state["quota_reservations"].get(task_id)
            if isinstance(reservation, dict):
                reservation["size_bytes"] = int(actual_bytes)
                reservation["created_at"] = time.time()
                reservation["finalized"] = True
                reservation["task_id"] = task_id
            self._sync_memory_usage(keys, state)
            self._atomic_write(self.keys_path, keys)
            self._atomic_write(self.state_path, state)

    def release_quota(self, task_id: str) -> None:
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            state = self._load_state()
            state["quota_reservations"].pop(task_id, None)
            self._sync_memory_usage(keys, state)
            self._atomic_write(self.keys_path, keys)
            self._atomic_write(self.state_path, state)

    def legacy_memory_usage(self, key_name: str) -> list[dict[str, Any]]:
        with self._lock(exclusive=True):
            keys = self._load_object(self.keys_path)
            state = self._load_state()
            self._sync_memory_usage(keys, state)
            self._atomic_write(self.keys_path, keys)
            self._atomic_write(self.state_path, state)
            info = keys.get(key_name)
            if not isinstance(info, dict):
                return []
            usage = info.get("memory_usage", [])
            return copy.deepcopy(usage) if isinstance(usage, list) else []

    # --- cleanup ------------------------------------------------------
    def expired_tasks(self) -> list[str]:
        cutoff = datetime.now(UTC) - timedelta(minutes=self.settings.cleanup_minutes)
        expired: list[str] = []
        with self._lock(exclusive=False):
            tasks = self._load_object(self.tasks_path)
        for task_id, legacy in tasks.items():
            if not isinstance(legacy, dict) or legacy.get("status") not in {
                TaskStatus.COMPLETED.value,
                TaskStatus.ERROR.value,
            }:
                continue
            completed = self._parse_iso(legacy.get("completed_time"))
            if completed is not None and completed < cutoff:
                expired.append(task_id)
        return expired

    def delete_task(self, task_id: str) -> None:
        with self._lock(exclusive=True):
            tasks = self._load_object(self.tasks_path)
            keys = self._load_object(self.keys_path)
            state = self._load_state()
            tasks.pop(task_id, None)
            state["task_meta"].pop(task_id, None)
            state["quota_reservations"].pop(task_id, None)
            self._sync_memory_usage(keys, state)
            self._atomic_write(self.tasks_path, tasks)
            self._atomic_write(self.keys_path, keys)
            self._atomic_write(self.state_path, state)


def create_database(settings: Settings) -> StateBackend:
    if settings.storage_backend == "json":
        return JsonDatabase(settings)
    return Database(settings)
