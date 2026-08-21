from __future__ import annotations

import ipaddress
import re
from pathlib import PurePath
from typing import Any
from urllib.parse import urlparse

from .config import Settings


class ValidationError(ValueError):
    pass


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FORMAT = re.compile(r"^[A-Za-z0-9._+-]{1,24}$")
_FILENAME_BAD = re.compile(r"[^A-Za-z0-9._()\[\] -]+")


def validate_url(value: Any, settings: Settings) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("URL is required")
    value = value.strip()
    if len(value) > 4096 or _CONTROL.search(value):
        raise ValidationError("Invalid URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationError("Only http:// and https:// URLs are allowed")
    if settings.allow_private_urls:
        return value

    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValidationError("Private/local URLs are not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return value
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        raise ValidationError("Private/local URLs are not allowed")
    return value


def _selector(value: Any, default: str | None) -> str | None:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValidationError("Format selector must be a string or null")
    value = value.strip()
    if not value:
        return default
    if len(value) > 512 or _CONTROL.search(value):
        raise ValidationError("Invalid format selector")
    return value


def _number(value: Any, name: str, *, default: float | int | None = None, minimum: float = 0) -> Any:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # Keep legacy HH:MM:SS strings for start_time/end_time, not for numeric live fields.
        raise ValidationError(f"{name} must be a number")
    if value < minimum:
        raise ValidationError(f"{name} must be >= {minimum}")
    return value


def validate_time_value(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError(f"{name} is invalid")
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValidationError(f"{name} must be >= 0")
        return value
    if not isinstance(value, str) or len(value) > 32 or _CONTROL.search(value):
        raise ValidationError(f"{name} is invalid")
    parts = value.split(":")
    try:
        nums = [float(part) for part in parts]
    except ValueError as exc:
        raise ValidationError(f"{name} is invalid") from exc
    if len(nums) not in {1, 2, 3} or any(part < 0 for part in nums):
        raise ValidationError(f"{name} is invalid")
    return value


def sanitize_output_filename(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("output_filename must be a string")
    value = value.strip()
    if not value:
        return None
    value = PurePath(value).name
    value = _FILENAME_BAD.sub("_", value).strip(" .")
    if not value or value in {".", ".."}:
        raise ValidationError("Invalid output_filename")
    return value[:120]


def normalize_task_payload(task_type: str, data: Any, settings: Settings) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError("JSON object is required")

    url = validate_url(data.get("url"), settings)
    video_format = _selector(data.get("video_format"), "bestvideo")
    audio_default = "bestaudio"
    audio_format = _selector(data.get("audio_format"), audio_default)
    if isinstance(data.get("audio_format"), str) and data["audio_format"].strip().lower() in {"none", "null"}:
        audio_format = data["audio_format"].strip().lower()

    output_format = data.get("output_format")
    if output_format is not None:
        if not isinstance(output_format, str) or not _FORMAT.fullmatch(output_format.strip()):
            raise ValidationError("Invalid output_format")
        output_format = output_format.strip().lower()

    start_time = validate_time_value(data.get("start_time"), "start_time")
    end_time = validate_time_value(data.get("end_time"), "end_time")
    start = _number(data.get("start"), "start", default=0, minimum=0)
    duration = _number(data.get("duration"), "duration", default=None, minimum=0)
    if duration == 0:
        raise ValidationError("duration must be > 0")

    payload: dict[str, Any] = {
        "video_format": video_format,
        "audio_format": audio_format,
        "force_keyframes": bool(data.get("force_keyframes", False)),
        "start": start,
    }
    for key, value in (
        ("start_time", start_time),
        ("end_time", end_time),
        ("duration", duration),
        ("output_format", output_format),
        ("output_filename", sanitize_output_filename(data.get("output_filename"))),
    ):
        if value is not None:
            payload[key] = value

    # Old Task.to_dict included these default fields even when irrelevant to the endpoint.
    # Keeping them preserves /status response shape for legacy clients.
    payload.setdefault("video_format", "bestvideo")
    payload.setdefault("audio_format", "bestaudio")
    payload.setdefault("force_keyframes", False)
    payload.setdefault("start", 0)
    payload["url"] = url
    return payload
