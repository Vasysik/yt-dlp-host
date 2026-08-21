from __future__ import annotations

from dataclasses import replace

from yt_dlp_host.config import settings


def make_app(tmp_path, monkeypatch, **changes):
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
        **changes,
    )
    cfg.ensure_directories()
    monkeypatch.setattr(app_module, "settings", cfg)
    return app_module.create_app()


def test_missing_key_shape_is_backward_compatible(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    response = app.test_client().post(
        "/get_video", json={"url": "https://example.com/video"}
    )
    assert response.status_code == 401
    assert response.get_json() == {"error": "No API key provided"}


def test_existing_task_endpoint_creates_shared_queue_task(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    db = app.extensions["yt_dlp_host_db"]
    secret = db.create_key("alice", ["get_info"])

    response = app.test_client().post(
        "/get_info",
        headers={"X-API-Key": secret},
        json={"url": "https://example.com/video"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "waiting"
    assert isinstance(body["task_id"], str) and body["task_id"]
    assert db.task(body["task_id"])["task_type"] == "get_info"


def test_status_stays_public_by_default(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    db = app.extensions["yt_dlp_host_db"]
    secret = db.create_key("alice", ["get_info"])
    created = app.test_client().post(
        "/get_info",
        headers={"X-API-Key": secret},
        json={"url": "https://example.com/video"},
    )
    task_id = created.get_json()["task_id"]

    response = app.test_client().get(f"/status/{task_id}")
    assert response.status_code == 200
    assert response.get_json()["status"] == "waiting"


def test_status_can_require_owner_key_without_new_api_surface(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch, legacy_public_status=False)
    db = app.extensions["yt_dlp_host_db"]
    alice = db.create_key("alice", ["get_info"])
    bob = db.create_key("bob", ["get_info"])
    created = app.test_client().post(
        "/get_info",
        headers={"X-API-Key": alice},
        json={"url": "https://example.com/video"},
    )
    task_id = created.get_json()["task_id"]

    missing = app.test_client().get(f"/status/{task_id}")
    assert missing.status_code == 401

    other = app.test_client().get(
        f"/status/{task_id}", headers={"X-API-Key": bob}
    )
    assert other.status_code == 404

    own = app.test_client().get(
        f"/status/{task_id}", headers={"X-API-Key": alice}
    )
    assert own.status_code == 200
    assert own.get_json()["status"] == "waiting"


def test_health_reports_backend_and_ytdlp_version(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    response = app.test_client().get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["storage_backend"] == "sqlite"
    assert isinstance(payload["yt_dlp_version"], str)
    assert payload["yt_dlp_version"]


def test_v2_routes_are_not_exposed(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    client = app.test_client()
    assert client.get("/api/v2/health").status_code == 404
    assert client.post("/api/v2/tasks", json={}).status_code == 404
