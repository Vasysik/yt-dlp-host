from __future__ import annotations

from dataclasses import replace

from yt_dlp_host.config import settings


def make_app(tmp_path, monkeypatch):
    import yt_dlp_host.app as app_module

    cfg = replace(
        settings,
        storage_backend="sqlite",
        database_path=tmp_path / "db.sqlite3",
        download_dir=tmp_path / "downloads",
        legacy_keys_file=tmp_path / "jsons" / "api_keys.json",
        legacy_tasks_file=tmp_path / "jsons" / "tasks.json",
        json_state_file=tmp_path / "jsons" / ".yt-dlp-host-state.json",
        admin_api_key="test-admin-secret",
        request_limit=100,
    )
    cfg.ensure_directories()
    monkeypatch.setattr(app_module, "settings", cfg)
    return app_module.create_app()


def test_v2_missing_key_uses_structured_error(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    response = app.test_client().get("/api/v2/tasks/does-not-exist")
    assert response.status_code == 401
    assert response.get_json() == {
        "error": {"code": "unauthorized", "message": "No API key provided"}
    }


def test_v2_invalid_key_uses_structured_error(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    response = app.test_client().get(
        "/api/v2/tasks/does-not-exist", headers={"X-API-Key": "wrong"}
    )
    assert response.status_code == 401
    assert response.get_json() == {
        "error": {"code": "unauthorized", "message": "Invalid API key"}
    }


def test_v2_create_and_owner_status(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    db = app.extensions["yt_dlp_host_db"]
    alice_secret = db.create_key("alice", ["get_info"])
    bob_secret = db.create_key("bob", ["get_info"])
    client = app.test_client()

    created = client.post(
        "/api/v2/tasks",
        headers={"X-API-Key": alice_secret},
        json={"type": "get_info", "url": "https://example.com/video"},
    )
    assert created.status_code == 202
    task_id = created.get_json()["id"]

    own = client.get(f"/api/v2/tasks/{task_id}", headers={"X-API-Key": alice_secret})
    assert own.status_code == 200
    assert own.get_json()["id"] == task_id
    assert own.get_json()["status"] == "waiting"

    other = client.get(f"/api/v2/tasks/{task_id}", headers={"X-API-Key": bob_secret})
    assert other.status_code == 404
    assert other.get_json() == {
        "error": {"code": "not_found", "message": "Task not found"}
    }


def test_health_reports_backend(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    response = app.test_client().get("/api/v2/health")
    assert response.status_code == 200
    assert response.get_json()["storage_backend"] == "sqlite"
