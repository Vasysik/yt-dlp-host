from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from yt_dlp_host.config import settings
from yt_dlp_host.db import Database, QuotaExceeded


def make_db(tmp_path: Path, **changes):
    cfg = replace(
        settings,
        database_path=tmp_path / "db.sqlite3",
        download_dir=tmp_path / "downloads",
        legacy_keys_file=tmp_path / "keys.json",
        legacy_tasks_file=tmp_path / "tasks.json",
        **changes,
    )
    cfg.ensure_directories()
    db = Database(cfg)
    db.initialize()
    return db


def test_task_claim_is_atomic_state_transition(tmp_path):
    db = make_db(tmp_path)
    db.create_key("alice", ["get_video"])
    db.create_task("t1", "alice", "get_video", "https://example.com", {"video_format": "bestvideo"})
    first = db.claim_next_task("w1")
    second = db.claim_next_task("w2")
    assert first and first["task_id"] == "t1"
    assert second is None
    assert db.task("t1")["status"] == "processing"


def test_rate_limiter_is_real_rolling_request_window(tmp_path):
    db = make_db(tmp_path, request_limit=2)
    db.create_key("alice", ["get_video"])
    assert db.check_rate_limit("alice") is True
    assert db.check_rate_limit("alice") is True
    assert db.check_rate_limit("alice") is False


def test_quota_resize_is_transactional(tmp_path):
    db = make_db(tmp_path, default_quota_bytes=100, server_quota_bytes=150)
    db.create_key("alice", ["get_video"], quota_bytes=100)
    db.create_key("bob", ["get_video"], quota_bytes=100)
    db.resize_quota_reservation("a", "alice", 80)
    with pytest.raises(QuotaExceeded):
        db.resize_quota_reservation("a2", "alice", 30)
    with pytest.raises(QuotaExceeded):
        db.resize_quota_reservation("b", "bob", 80)


def test_active_quota_does_not_expire_with_window(tmp_path, monkeypatch):
    db = make_db(tmp_path, default_quota_bytes=100, server_quota_bytes=150, quota_window_minutes=10)
    db.create_key("alice", ["get_video"], quota_bytes=100)
    db.resize_quota_reservation("a", "alice", 80)
    # Simulate an old active reservation. Active downloads must still count.
    with db.connect() as conn:
        conn.execute("UPDATE quota_reservations SET created_at=0, finalized=0 WHERE task_id='a'")
    with pytest.raises(QuotaExceeded):
        db.resize_quota_reservation("b", "alice", 30)


def test_finalized_quota_expires_after_window(tmp_path):
    db = make_db(tmp_path, default_quota_bytes=100, server_quota_bytes=150, quota_window_minutes=10)
    db.create_key("alice", ["get_video"], quota_bytes=100)
    db.resize_quota_reservation("a", "alice", 80)
    db.finalize_quota("a", "alice", 80)
    with db.connect() as conn:
        conn.execute("UPDATE quota_reservations SET created_at=0, finalized=1 WHERE task_id='a'")
    db.resize_quota_reservation("b", "alice", 100)


def test_quota_headroom_excludes_current_task(tmp_path):
    db = make_db(tmp_path, default_quota_bytes=100, server_quota_bytes=150)
    db.create_key("alice", ["get_video"], quota_bytes=100)
    db.resize_quota_reservation("a", "alice", 40)
    assert db.quota_headroom("alice") == 60
    assert db.quota_headroom("alice", "a") == 100


def test_imported_processing_task_is_requeued(tmp_path):
    db = make_db(tmp_path)
    db.import_task(
        "legacy-processing",
        {
            "key_name": "admin",
            "status": "processing",
            "task_type": "get_video",
            "url": "https://example.com/video",
        },
    )
    assert db.task("legacy-processing")["status"] == "waiting"
