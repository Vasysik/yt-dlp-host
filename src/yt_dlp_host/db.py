from __future__ import annotations

import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .config import Settings
from .models import ADMIN_PERMISSIONS, TaskStatus


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class QuotaExceeded(RuntimeError):
    pass


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.database_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS api_keys (
                    name TEXT PRIMARY KEY,
                    secret TEXT NOT NULL UNIQUE,
                    permissions_json TEXT NOT NULL,
                    quota_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_access TEXT
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    key_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    url TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_time TEXT,
                    error TEXT,
                    file_path TEXT,
                    actual_bytes INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status_created
                    ON tasks(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_tasks_key
                    ON tasks(key_name);
                CREATE INDEX IF NOT EXISTS idx_tasks_lease
                    ON tasks(status, lease_expires_at);

                CREATE TABLE IF NOT EXISTS rate_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_name TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rate_key_time
                    ON rate_events(key_name, created_at);

                CREATE TABLE IF NOT EXISTS quota_reservations (
                    task_id TEXT PRIMARY KEY,
                    key_name TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    finalized INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_quota_key_time
                    ON quota_reservations(key_name, created_at);
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(quota_reservations)")}
            if "finalized" not in columns:
                conn.execute("ALTER TABLE quota_reservations ADD COLUMN finalized INTEGER NOT NULL DEFAULT 0")

    def get_metadata(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_metadata(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO metadata(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    # --- API keys ---------------------------------------------------------
    def count_keys(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0])

    def bootstrap_admin(self) -> tuple[str, bool]:
        """Ensure an admin key exists. Returns (secret, was_created)."""
        with self.transaction(immediate=True) as conn:
            existing = conn.execute("SELECT secret FROM api_keys WHERE name='admin'").fetchone()
            if existing:
                return str(existing["secret"]), False
            secret = self.settings.admin_api_key or secrets.token_urlsafe(32)
            now = utc_now()
            conn.execute(
                "INSERT INTO api_keys(name, secret, permissions_json, quota_bytes, created_at, last_access) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("admin", secret, _json(sorted(ADMIN_PERMISSIONS)), self.settings.default_quota_bytes, now, now),
            )
            return secret, True

    def create_key(self, name: str, permissions: list[str], quota_bytes: int | None = None) -> str:
        secret = secrets.token_urlsafe(32)
        quota = quota_bytes or self.settings.default_quota_bytes
        now = utc_now()
        # Legacy behavior overwrote duplicate names. Preserve that behavior.
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO api_keys(name, secret, permissions_json, quota_bytes, created_at, last_access)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    secret=excluded.secret,
                    permissions_json=excluded.permissions_json,
                    quota_bytes=excluded.quota_bytes,
                    last_access=excluded.last_access
                """,
                (name, secret, _json(permissions), quota, now, now),
            )
        return secret

    def import_key(
        self,
        name: str,
        secret: str,
        permissions: list[str],
        quota_bytes: int,
        last_access: str | None,
    ) -> None:
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO api_keys(name, secret, permissions_json, quota_bytes, created_at, last_access)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, secret, _json(permissions), quota_bytes, utc_now(), last_access),
            )

    def delete_key(self, name: str) -> bool:
        with self.transaction(immediate=True) as conn:
            cur = conn.execute("DELETE FROM api_keys WHERE name = ?", (name,))
            return cur.rowcount > 0

    def key_by_secret(self, secret: str | None) -> dict[str, Any] | None:
        if not secret:
            return None
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE secret = ?", (secret,)).fetchone()
        return self._decode_key(row) if row else None

    def key_by_name(self, name: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE name = ?", (name,)).fetchone()
        return self._decode_key(row) if row else None

    def list_keys(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM api_keys ORDER BY name").fetchall()
        return [self._decode_key(row) for row in rows]

    @staticmethod
    def _decode_key(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "name": row["name"],
            "key": row["secret"],
            "permissions": json.loads(row["permissions_json"]),
            "memory_quota": int(row["quota_bytes"]),
            "last_access": row["last_access"],
        }

    def touch_key(self, name: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE api_keys SET last_access=? WHERE name=?", (utc_now(), name))

    def check_rate_limit(self, key_name: str) -> bool:
        cutoff = time.time() - self.settings.request_window_minutes * 60
        with self.transaction(immediate=True) as conn:
            conn.execute("DELETE FROM rate_events WHERE created_at < ?", (cutoff,))
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM rate_events WHERE key_name=? AND created_at>=?",
                    (key_name, cutoff),
                ).fetchone()[0]
            )
            if count >= self.settings.request_limit:
                return False
            conn.execute(
                "INSERT INTO rate_events(key_name, created_at) VALUES (?, ?)",
                (key_name, time.time()),
            )
            return True

    # --- tasks ------------------------------------------------------------
    def create_task(
        self,
        task_id: str,
        key_name: str,
        task_type: str,
        url: str,
        payload: dict[str, Any],
    ) -> None:
        now = utc_now()
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO tasks(task_id, key_name, status, task_type, url, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, key_name, TaskStatus.WAITING.value, task_type, url, _json(payload), now, now),
            )

    def import_task(self, task_id: str, data: dict[str, Any]) -> None:
        known = {
            "key_name", "status", "task_type", "url", "completed_time", "error", "file"
        }
        payload = {k: v for k, v in data.items() if k not in known}
        now = utc_now()
        imported_status = data.get("status", TaskStatus.ERROR.value)
        if imported_status == TaskStatus.PROCESSING.value:
            imported_status = TaskStatus.WAITING.value
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO tasks(
                    task_id, key_name, status, task_type, url, payload_json,
                    created_at, updated_at, completed_time, error, file_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    data.get("key_name", "admin"),
                    imported_status,
                    data.get("task_type", "get_info"),
                    data.get("url", ""),
                    _json(payload),
                    now,
                    now,
                    data.get("completed_time"),
                    data.get("error"),
                    data.get("file"),
                ),
            )

    def task(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._decode_task(row) if row else None

    def _decode_task(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        return {
            "task_id": row["task_id"],
            "key_name": row["key_name"],
            "status": row["status"],
            "task_type": row["task_type"],
            "url": row["url"],
            "payload": payload,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_time": row["completed_time"],
            "error": row["error"],
            "file": row["file_path"],
            "actual_bytes": int(row["actual_bytes"] or 0),
            "attempts": int(row["attempts"] or 0),
            "lease_owner": row["lease_owner"],
            "lease_expires_at": row["lease_expires_at"],
        }

    def legacy_task(self, task_id: str) -> dict[str, Any] | None:
        task = self.task(task_id)
        if not task:
            return None
        result: dict[str, Any] = {
            "key_name": task["key_name"],
            "status": task["status"],
            "task_type": task["task_type"],
            "url": task["url"],
        }
        result.update(task["payload"])
        if task["completed_time"] is not None:
            result["completed_time"] = task["completed_time"]
        if task["error"] is not None:
            result["error"] = task["error"]
        if task["file"] is not None:
            result["file"] = task["file"]
        return result

    def claim_next_task(self, worker_id: str) -> dict[str, Any] | None:
        now_ts = time.time()
        lease_until = now_ts + self.settings.worker_lease_seconds
        now_iso = utc_now()
        with self.transaction(immediate=True) as conn:
            # A crashed worker's task becomes available again after its lease expires.
            conn.execute(
                """
                UPDATE tasks SET status=?, lease_owner=NULL, lease_expires_at=NULL, updated_at=?
                WHERE status=? AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
                """,
                (TaskStatus.WAITING.value, now_iso, TaskStatus.PROCESSING.value, now_ts),
            )
            row = conn.execute(
                "SELECT task_id FROM tasks WHERE status=? ORDER BY created_at LIMIT 1",
                (TaskStatus.WAITING.value,),
            ).fetchone()
            if row is None:
                return None
            task_id = str(row["task_id"])
            cur = conn.execute(
                """
                UPDATE tasks SET status=?, lease_owner=?, lease_expires_at=?, attempts=attempts+1, updated_at=?
                WHERE task_id=? AND status=?
                """,
                (
                    TaskStatus.PROCESSING.value,
                    worker_id,
                    lease_until,
                    now_iso,
                    task_id,
                    TaskStatus.WAITING.value,
                ),
            )
            if cur.rowcount != 1:
                return None
            claimed = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._decode_task(claimed)

    def extend_lease(self, task_id: str, worker_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE tasks SET lease_expires_at=?, updated_at=?
                WHERE task_id=? AND status=? AND lease_owner=?
                """,
                (
                    time.time() + self.settings.worker_lease_seconds,
                    utc_now(),
                    task_id,
                    TaskStatus.PROCESSING.value,
                    worker_id,
                ),
            )

    def complete_task(self, task_id: str, file_path: str | None, actual_bytes: int = 0) -> None:
        now = utc_now()
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                UPDATE tasks SET status=?, completed_time=?, updated_at=?, error=NULL,
                    file_path=?, actual_bytes=?, lease_owner=NULL, lease_expires_at=NULL
                WHERE task_id=?
                """,
                (TaskStatus.COMPLETED.value, now, now, file_path, actual_bytes, task_id),
            )

    def fail_task(self, task_id: str, error: str) -> None:
        now = utc_now()
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                UPDATE tasks SET status=?, completed_time=?, updated_at=?, error=?,
                    lease_owner=NULL, lease_expires_at=NULL
                WHERE task_id=?
                """,
                (TaskStatus.ERROR.value, now, now, error[:4000], task_id),
            )
            conn.execute("DELETE FROM quota_reservations WHERE task_id=?", (task_id,))

    # --- rolling quota ----------------------------------------------------
    def _cleanup_quota(self, conn: sqlite3.Connection) -> float:
        cutoff = time.time() - self.settings.quota_window_minutes * 60
        conn.execute(
            "DELETE FROM quota_reservations WHERE finalized=1 AND created_at < ?",
            (cutoff,),
        )
        return cutoff

    def quota_headroom(self, key_name: str, task_id: str | None = None) -> int:
        """Return bytes this task may reserve right now under user + server rolling quotas."""
        with self.transaction(immediate=True) as conn:
            cutoff = self._cleanup_quota(conn)
            key = conn.execute("SELECT quota_bytes FROM api_keys WHERE name=?", (key_name,)).fetchone()
            if key is None:
                raise QuotaExceeded("Invalid API key")
            task_filter = " AND task_id<>?" if task_id else ""
            user_args: tuple[Any, ...] = (key_name, cutoff, task_id) if task_id else (key_name, cutoff)
            global_args: tuple[Any, ...] = (cutoff, task_id) if task_id else (cutoff,)
            user_total = int(
                conn.execute(
                    "SELECT COALESCE(SUM(size_bytes),0) FROM quota_reservations "
                    "WHERE key_name=? AND (finalized=0 OR created_at>=?)" + task_filter,
                    user_args,
                ).fetchone()[0]
            )
            global_total = int(
                conn.execute(
                    "SELECT COALESCE(SUM(size_bytes),0) FROM quota_reservations "
                    "WHERE (finalized=0 OR created_at>=?)" + task_filter,
                    global_args,
                ).fetchone()[0]
            )
            return max(
                0,
                min(
                    int(key["quota_bytes"]) - user_total,
                    self.settings.server_quota_bytes - global_total,
                ),
            )

    def resize_quota_reservation(self, task_id: str, key_name: str, requested_bytes: int) -> None:
        requested = max(0, int(requested_bytes))
        with self.transaction(immediate=True) as conn:
            cutoff = self._cleanup_quota(conn)
            key = conn.execute("SELECT quota_bytes FROM api_keys WHERE name=?", (key_name,)).fetchone()
            if key is None:
                raise QuotaExceeded("Invalid API key")
            existing = conn.execute(
                "SELECT size_bytes FROM quota_reservations WHERE task_id=?", (task_id,)
            ).fetchone()
            old = int(existing["size_bytes"]) if existing else 0
            if requested <= old:
                return

            user_total = int(
                conn.execute(
                    "SELECT COALESCE(SUM(size_bytes),0) FROM quota_reservations "
                    "WHERE key_name=? AND (finalized=0 OR created_at>=?) AND task_id<>?",
                    (key_name, cutoff, task_id),
                ).fetchone()[0]
            )
            global_total = int(
                conn.execute(
                    "SELECT COALESCE(SUM(size_bytes),0) FROM quota_reservations "
                    "WHERE (finalized=0 OR created_at>=?) AND task_id<>?",
                    (cutoff, task_id),
                ).fetchone()[0]
            )
            quota = int(key["quota_bytes"])
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
            conn.execute(
                """
                INSERT INTO quota_reservations(task_id, key_name, size_bytes, created_at, finalized)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(task_id) DO UPDATE SET
                    size_bytes=excluded.size_bytes, finalized=0
                """,
                (task_id, key_name, requested, time.time()),
            )

    def finalize_quota(self, task_id: str, key_name: str, actual_bytes: int) -> None:
        # Resize transactionally to the final size. If it cannot fit, caller removes the file.
        self.resize_quota_reservation(task_id, key_name, actual_bytes)
        with self.connect() as conn:
            conn.execute(
                "UPDATE quota_reservations SET size_bytes=?, created_at=?, finalized=1 WHERE task_id=?",
                (int(actual_bytes), time.time(), task_id),
            )

    def release_quota(self, task_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM quota_reservations WHERE task_id=?", (task_id,))

    def legacy_memory_usage(self, key_name: str) -> list[dict[str, Any]]:
        cutoff = time.time() - self.settings.quota_window_minutes * 60
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT task_id, size_bytes, created_at FROM quota_reservations
                WHERE key_name=? AND (finalized=0 OR created_at>=?) ORDER BY created_at
                """,
                (key_name, cutoff),
            ).fetchall()
        return [
            {
                "size": int(row["size_bytes"]),
                "timestamp": datetime.fromtimestamp(row["created_at"], UTC).isoformat(),
                "task_id": row["task_id"],
            }
            for row in rows
        ]

    # --- cleanup ----------------------------------------------------------
    def expired_tasks(self) -> list[str]:
        cutoff = datetime.now(UTC) - timedelta(minutes=self.settings.cleanup_minutes)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT task_id FROM tasks
                WHERE status IN (?, ?) AND completed_time IS NOT NULL AND completed_time < ?
                """,
                (TaskStatus.COMPLETED.value, TaskStatus.ERROR.value, cutoff.isoformat()),
            ).fetchall()
        return [str(row["task_id"]) for row in rows]

    def delete_task(self, task_id: str) -> None:
        with self.transaction(immediate=True) as conn:
            conn.execute("DELETE FROM quota_reservations WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
