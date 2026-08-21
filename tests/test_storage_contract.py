from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from yt_dlp_host.config import settings
from yt_dlp_host.db import QuotaExceeded
from yt_dlp_host.storage import JsonDatabase, create_database


def make_backend(tmp_path: Path, backend: str, **changes):
    cfg = replace(
        settings,
        storage_backend=backend,
        database_path=tmp_path / "db.sqlite3",
        download_dir=tmp_path / "downloads",
        legacy_keys_file=tmp_path / "jsons" / "api_keys.json",
        legacy_tasks_file=tmp_path / "jsons" / "tasks.json",
        json_state_file=tmp_path / "jsons" / ".yt-dlp-host-state.json",
        **changes,
    )
    cfg.ensure_directories()
    db = create_database(cfg)
    db.initialize()
    return db, cfg


@pytest.mark.parametrize("backend", ["sqlite", "json"])
def test_state_backend_task_claim_contract(tmp_path, backend):
    db, _ = make_backend(tmp_path, backend)
    db.create_key("alice", ["get_video"])
    db.create_task("t1", "alice", "get_video", "https://example.com/video", {"video_format": "bestvideo"})

    first = db.claim_next_task("worker-1")
    second = db.claim_next_task("worker-2")

    assert first is not None
    assert first["task_id"] == "t1"
    assert first["status"] == "processing"
    assert second is None
    assert db.task("t1")["attempts"] == 1


@pytest.mark.parametrize("backend", ["sqlite", "json"])
def test_state_backend_rate_limit_contract(tmp_path, backend):
    db, _ = make_backend(tmp_path, backend, request_limit=2)
    db.create_key("alice", ["get_video"])
    assert db.check_rate_limit("alice") is True
    assert db.check_rate_limit("alice") is True
    assert db.check_rate_limit("alice") is False


@pytest.mark.parametrize("backend", ["sqlite", "json"])
def test_state_backend_quota_contract(tmp_path, backend):
    db, _ = make_backend(tmp_path, backend, default_quota_bytes=100, server_quota_bytes=150)
    db.create_key("alice", ["get_video"], quota_bytes=100)
    db.create_key("bob", ["get_video"], quota_bytes=100)

    db.resize_quota_reservation("a", "alice", 80)
    with pytest.raises(QuotaExceeded):
        db.resize_quota_reservation("a2", "alice", 30)
    with pytest.raises(QuotaExceeded):
        db.resize_quota_reservation("b", "bob", 80)

    db.finalize_quota("a", "alice", 60)
    usage = db.legacy_memory_usage("alice")
    assert len(usage) == 1
    assert usage[0]["size"] == 60
    assert usage[0]["task_id"] == "a"


@pytest.mark.parametrize("backend", ["sqlite", "json"])
def test_state_backend_complete_task_contract(tmp_path, backend):
    db, _ = make_backend(tmp_path, backend)
    db.create_key("alice", ["get_info"])
    db.create_task("info1", "alice", "get_info", "https://example.com/video", {})
    db.claim_next_task("worker")
    db.complete_task("info1", "/files/info1/info.json", 123)

    task = db.task("info1")
    legacy = db.legacy_task("info1")
    assert task["status"] == "completed"
    assert task["file"] == "/files/info1/info.json"
    assert task["actual_bytes"] == 123
    assert legacy["status"] == "completed"
    assert legacy["file"] == "/files/info1/info.json"
    assert "completed_time" in legacy


def test_json_backend_uses_existing_legacy_files_directly(tmp_path):
    json_dir = tmp_path / "jsons"
    json_dir.mkdir()
    keys_path = json_dir / "api_keys.json"
    tasks_path = json_dir / "tasks.json"
    keys_path.write_text(
        json.dumps(
            {
                "alice": {
                    "key": "legacy-secret",
                    "permissions": ["get_video"],
                    "memory_quota": 1234,
                    "memory_usage": [],
                    "last_access": None,
                }
            }
        ),
        encoding="utf-8",
    )
    tasks_path.write_text(
        json.dumps(
            {
                "legacy-task": {
                    "key_name": "alice",
                    "status": "waiting",
                    "task_type": "get_video",
                    "url": "https://example.com/video",
                    "video_format": "bestvideo",
                    "audio_format": "bestaudio",
                    "force_keyframes": False,
                    "start": 0,
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = replace(
        settings,
        storage_backend="json",
        database_path=tmp_path / "must-not-be-created.sqlite3",
        download_dir=tmp_path / "downloads",
        legacy_keys_file=keys_path,
        legacy_tasks_file=tasks_path,
        json_state_file=json_dir / ".yt-dlp-host-state.json",
    )
    cfg.ensure_directories()
    db = create_database(cfg)
    assert isinstance(db, JsonDatabase)
    db.initialize()

    assert db.key_by_secret("legacy-secret")["name"] == "alice"
    claimed = db.claim_next_task("worker")
    assert claimed["task_id"] == "legacy-task"
    assert not cfg.database_path.exists()


def test_json_backend_keeps_public_files_in_legacy_shape(tmp_path):
    db, cfg = make_backend(tmp_path, "json")
    db.create_key("alice", ["get_video"])
    db.create_task(
        "t1",
        "alice",
        "get_video",
        "https://example.com/video",
        {
            "video_format": "bestvideo",
            "audio_format": "bestaudio",
            "force_keyframes": False,
            "start": 0,
            "output_filename": "clip",
        },
    )
    db.claim_next_task("worker")

    keys = json.loads(cfg.legacy_keys_file.read_text(encoding="utf-8"))
    tasks = json.loads(cfg.legacy_tasks_file.read_text(encoding="utf-8"))

    assert set(keys["alice"]) == {
        "key",
        "permissions",
        "memory_quota",
        "memory_usage",
        "last_access",
    }
    assert tasks["t1"]["status"] == "processing"
    assert tasks["t1"]["task_type"] == "get_video"
    assert tasks["t1"]["output_filename"] == "clip"
    assert "created_at" not in tasks["t1"]
    assert "attempts" not in tasks["t1"]
    assert "lease_owner" not in tasks["t1"]
    assert cfg.json_state_file.exists()
