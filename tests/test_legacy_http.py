from __future__ import annotations

# These are contract tests. They require Flask, installed by requirements.txt.

def test_legacy_missing_key_shape(tmp_path, monkeypatch):
    from yt_dlp_host.app import create_app

    app = create_app()
    client = app.test_client()
    response = client.post("/get_video", json={"url": "https://example.com/video"})
    assert response.status_code == 401
    assert response.get_json() == {"error": "No API key provided"}


def test_health(tmp_path):
    from yt_dlp_host.app import create_app

    app = create_app()
    client = app.test_client()
    response = client.get("/api/v2/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert isinstance(payload["yt_dlp_version"], str)
    assert payload["yt_dlp_version"]
