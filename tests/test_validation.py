from dataclasses import replace

import pytest

from yt_dlp_host.config import settings
from yt_dlp_host.validation import ValidationError, normalize_task_payload, sanitize_output_filename, validate_url


def test_blocks_local_urls_by_default():
    with pytest.raises(ValidationError):
        validate_url("http://127.0.0.1:8080/private", settings)
    with pytest.raises(ValidationError):
        validate_url("http://localhost/private", settings)


def test_allows_public_http_urls():
    assert validate_url("https://www.youtube.com/watch?v=x", settings).startswith("https://")


def test_filename_is_reduced_to_safe_basename():
    assert sanitize_output_filename("../../hello: world.mp3") == "hello_ world.mp3"


def test_legacy_defaults_are_preserved():
    data = normalize_task_payload("get_video", {"url": "https://example.com/video"}, settings)
    assert data["video_format"] == "bestvideo"
    assert data["audio_format"] == "bestaudio"
    assert data["force_keyframes"] is False
    assert data["start"] == 0
