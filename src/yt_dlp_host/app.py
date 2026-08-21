from __future__ import annotations

import json
import logging
import secrets
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from flask import Flask, jsonify, request, send_file
from yt_dlp.version import __version__ as yt_dlp_version

from . import __version__
from .config import settings
from .migration import migrate_legacy_json
from .storage import create_database
from .models import TaskType
from .validation import ValidationError, normalize_task_payload

log = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False
    app.config["MAX_CONTENT_LENGTH"] = settings.max_request_bytes

    db = create_database(settings)
    db.initialize()
    if settings.storage_backend == "sqlite":
        migrate_legacy_json(db)
    admin_secret, created = db.bootstrap_admin()
    if created:
        if settings.admin_api_key:
            log.info("Created admin API key from ADMIN_API_KEY")
        else:
            # This is intentionally emitted once so a fresh deployment is usable.
            log.warning("Generated initial admin API key: %s", admin_secret)

    app.extensions["yt_dlp_host_db"] = db

    def authenticate(*, permission: str | None = None, rate_limit: bool = True):
        def decorator(func: F) -> F:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any):
                api_key = request.headers.get("X-API-Key")
                if not api_key:
                    return jsonify({"error": "No API key provided"}), 401
                key = db.key_by_secret(api_key)
                if not key:
                    return jsonify({"error": "Invalid API key"}), 401
                if rate_limit and not db.check_rate_limit(key["name"]):
                    message = (
                        f"Rate limit exceeded. Max {settings.request_limit} per "
                        f"{settings.request_window_minutes} min"
                    )
                    return jsonify({"error": message}), 429
                if permission and permission not in key["permissions"]:
                    return jsonify({"error": "Insufficient permissions"}), 403
                db.touch_key(key["name"])
                request.environ["yt_dlp_host.key_name"] = key["name"]
                return func(*args, **kwargs)

            return wrapper  # type: ignore[return-value]

        return decorator

    def task_endpoint(task_type: TaskType):
        @authenticate(permission=task_type.value)
        def endpoint():
            try:
                payload = normalize_task_payload(task_type.value, request.get_json(silent=True), settings)
            except ValidationError as exc:
                # Preserve the original missing-URL error shape.
                if str(exc) == "URL is required":
                    return {"status": "error", "message": "URL is required"}, 400
                return jsonify({"status": "error", "message": str(exc)}), 400

            task_id = secrets.token_urlsafe(12)
            key_name = str(request.environ["yt_dlp_host.key_name"])
            url = payload.pop("url")
            db.create_task(task_id, key_name, task_type.value, url, payload)
            return jsonify({"status": "waiting", "task_id": task_id})

        endpoint.__name__ = f"task_{task_type.value}"
        return endpoint

    app.add_url_rule("/get_video", view_func=task_endpoint(TaskType.GET_VIDEO), methods=["POST"])
    app.add_url_rule("/get_audio", view_func=task_endpoint(TaskType.GET_AUDIO), methods=["POST"])
    app.add_url_rule("/get_info", view_func=task_endpoint(TaskType.GET_INFO), methods=["POST"])
    app.add_url_rule("/get_live_video", view_func=task_endpoint(TaskType.GET_LIVE_VIDEO), methods=["POST"])
    app.add_url_rule("/get_live_audio", view_func=task_endpoint(TaskType.GET_LIVE_AUDIO), methods=["POST"])

    @app.get("/status/<task_id>")
    def task_status(task_id: str):
        stored = db.task(task_id)
        if stored is None:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        if not settings.legacy_public_status:
            api_key = request.headers.get("X-API-Key")
            key = db.key_by_secret(api_key)
            if not key:
                return jsonify({"error": "Invalid API key"}), 401
            if stored["key_name"] != key["name"]:
                return jsonify({"status": "error", "message": "Task not found"}), 404
        return jsonify(db.legacy_task(task_id))

    def _resolve_task_file(filename: str) -> Path | None:
        parts = Path(filename).parts
        if len(parts) < 2 or parts[0] in {".", ".."}:
            return None
        task_id = parts[0]
        if db.task(task_id) is None:
            return None
        task_dir = (settings.download_dir / task_id).resolve()
        candidate = (settings.download_dir / filename).resolve()
        try:
            candidate.relative_to(task_dir)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    @app.get("/files/<path:filename>")
    def task_file(filename: str):
        if not settings.legacy_public_files:
            parts = Path(filename).parts
            task_id = parts[0] if parts else ""
            stored = db.task(task_id) if task_id else None
            api_key = request.headers.get("X-API-Key")
            key = db.key_by_secret(api_key)
            if not key:
                return jsonify({"error": "Invalid API key"}), 401
            if not stored or stored["key_name"] != key["name"]:
                return jsonify({"error": "File not found"}), 404
        path = _resolve_task_file(filename)
        if path is None:
            return jsonify({"error": "File not found"}), 404
        if path.name == "info.json":
            return _info_response(path)
        raw = request.args.get("raw", "false").lower() == "true"
        response = send_file(path, as_attachment=raw, download_name=path.name, conditional=True)
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Cache-Control"] = "public, max-age=3600"
        # Preserve old behavior: raw=true is served inline despite the historical name.
        if raw:
            response.headers["Content-Disposition"] = f'inline; filename="{path.name}"'
        return response

    def _info_response(path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return jsonify({"error": "Invalid info file"}), 500
        if not request.args:
            return jsonify(data)
        result: dict[str, Any] = {}
        if "qualities" in request.args:
            result["qualities"] = extract_qualities(data)
        for key in request.args:
            if key != "qualities" and key in data:
                result[key] = data[key]
        if result:
            return jsonify(result)
        return jsonify({"error": "No matching parameters"}), 404

    @app.post("/create_key")
    @authenticate(permission="create_key")
    def create_key():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Name and permissions required"}), 400
        name = data.get("name")
        permissions = data.get("permissions")
        if not isinstance(name, str) or not name.strip() or not isinstance(permissions, list) or not permissions:
            return jsonify({"error": "Name and permissions required"}), 400
        if any(not isinstance(p, str) or not p for p in permissions):
            return jsonify({"error": "Name and permissions required"}), 400
        key = db.create_key(name.strip(), permissions)
        return jsonify({"message": "API key created", "name": name.strip(), "key": key}), 201

    @app.delete("/delete_key/<name>")
    @authenticate(permission="delete_key")
    def delete_key(name: str):
        if db.delete_key(name):
            return jsonify({"message": "API key deleted", "name": name}), 200
        return jsonify({"error": "Key not found"}), 404

    @app.get("/get_key/<name>")
    @authenticate(permission="get_key")
    def get_key(name: str):
        key = db.key_by_name(name)
        if key:
            return jsonify({"name": name, "key": key["key"]}), 200
        return jsonify({"error": "Key not found"}), 404

    @app.get("/get_keys")
    @authenticate(permission="get_keys")
    def get_keys():
        result: dict[str, Any] = {}
        for key in db.list_keys():
            result[key["name"]] = {
                "key": key["key"],
                "permissions": key["permissions"],
                "memory_quota": key["memory_quota"],
                "memory_usage": db.legacy_memory_usage(key["name"]),
                "last_access": key["last_access"],
            }
        return jsonify(result), 200

    @app.post("/check_permissions")
    def check_permissions():
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return jsonify({"error": "No API key provided"}), 401
        key = db.key_by_secret(api_key)
        if not key:
            return jsonify({"error": "Invalid API key"}), 401
        data = request.get_json(silent=True) or {}
        required = data.get("permissions", []) if isinstance(data, dict) else []
        if not isinstance(required, list):
            return jsonify({"message": "Insufficient permissions"}), 403
        if set(required).issubset(set(key["permissions"])):
            return jsonify({"message": "Permissions granted"}), 200
        return jsonify({"message": "Insufficient permissions"}), 403

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "version": __version__,
                "yt_dlp_version": yt_dlp_version,
                "storage_backend": settings.storage_backend,
            }
        )

    return app


def extract_qualities(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    qualities: dict[str, dict[str, Any]] = {"audio": {}, "video": {}}
    for fmt in data.get("formats", []):
        if not isinstance(fmt, dict) or fmt.get("format_note") in {"unknown", "storyboard"}:
            continue
        format_id = str(fmt.get("format_id", ""))
        if not format_id:
            continue
        if fmt.get("acodec") != "none" and fmt.get("vcodec") == "none" and fmt.get("abr"):
            qualities["audio"][format_id] = {
                "abr": int(fmt.get("abr") or 0),
                "acodec": fmt.get("acodec") or "unknown",
                "audio_channels": int(fmt.get("audio_channels") or 0),
                "language": fmt.get("language"),
                "filesize": int(fmt.get("filesize") or fmt.get("filesize_approx") or 0),
            }
        elif fmt.get("vcodec") != "none" and fmt.get("height") and fmt.get("fps"):
            qualities["video"][format_id] = {
                "height": int(fmt.get("height") or 0),
                "width": int(fmt.get("width") or 0),
                "fps": int(fmt.get("fps") or 0),
                "vcodec": fmt.get("vcodec") or "unknown",
                "format_note": fmt.get("format_note", "unknown"),
                "dynamic_range": fmt.get("dynamic_range", "unknown"),
                "filesize": int(fmt.get("filesize") or fmt.get("filesize_approx") or 0),
            }
    qualities["video"] = dict(
        sorted(qualities["video"].items(), key=lambda item: (item[1]["height"], item[1]["fps"]))
    )
    qualities["audio"] = dict(
        sorted(qualities["audio"].items(), key=lambda item: item[1]["abr"])
    )
    return qualities
