from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from .config import Settings
from .db import QuotaExceeded
from .storage import StateBackend
from .models import TaskType

log = logging.getLogger(__name__)


class DownloadEngine:
    def __init__(self, settings: Settings, db: StateBackend):
        self.settings = settings
        self.db = db

    @staticmethod
    def _time_to_seconds(value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        text = str(value)
        parts = text.split(":")
        try:
            nums = [float(part) for part in parts]
        except ValueError:
            return 0.0
        if len(nums) == 1:
            return nums[0]
        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        if len(nums) == 3:
            return nums[0] * 3600 + nums[1] * 60 + nums[2]
        return 0.0

    def _task_dir(self, task_id: str) -> Path:
        path = (self.settings.download_dir / task_id).resolve()
        path.relative_to(self.settings.download_dir)
        return path

    def _base_options(self) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": self.settings.log_level not in {"DEBUG"},
            "no_warnings": False,
            "noplaylist": self.settings.noplaylist,
            "socket_timeout": self.settings.socket_timeout_seconds,
            "retries": self.settings.retries,
            "fragment_retries": self.settings.fragment_retries,
            "concurrent_fragment_downloads": self.settings.concurrent_fragments,
            "continuedl": True,
            "overwrites": True,
        }
        if self.settings.cookies_file:
            if not self.settings.cookies_file.is_file():
                raise RuntimeError(f"Cookie file does not exist: {self.settings.cookies_file}")
            opts["cookiefile"] = str(self.settings.cookies_file)
        if self.settings.proxy:
            opts["proxy"] = self.settings.proxy
        if self.settings.impersonate:
            opts["impersonate"] = self.settings.impersonate
        if self.settings.extractor_args:
            opts["extractor_args"] = self.settings.extractor_args
        return opts

    def process(self, task: dict[str, Any]) -> None:
        task_id = task["task_id"]
        try:
            if task["task_type"] == TaskType.GET_INFO.value:
                self._download_info(task)
            else:
                self._download_media(task)
        except Exception as exc:
            log.exception("Task %s failed", task_id)
            self.db.fail_task(task_id, str(exc))
            self._remove_partial(task_id)

    def _download_info(self, task: dict[str, Any]) -> None:
        import yt_dlp

        task_id = task["task_id"]
        target = self._task_dir(task_id)
        target.mkdir(parents=True, exist_ok=True)
        opts = self._base_options()
        opts.update({"skip_download": True, "extract_flat": False})
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(task["url"], download=False)
            sanitized = ydl.sanitize_info(info)
        info_path = target / "info.json"
        temp_path = target / ".info.json.tmp"
        with temp_path.open("w", encoding="utf-8") as fh:
            json.dump(sanitized, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        temp_path.replace(info_path)
        self.db.complete_task(task_id, f"/files/{task_id}/info.json", info_path.stat().st_size)

    def _download_media(self, task: dict[str, Any]) -> None:
        import yt_dlp
        from yt_dlp.utils import download_range_func

        task_id = task["task_id"]
        payload = task["payload"]
        target = self._task_dir(task_id)
        target.mkdir(parents=True, exist_ok=True)

        is_video = task["task_type"] in {TaskType.GET_VIDEO.value, TaskType.GET_LIVE_VIDEO.value}
        is_live = task["task_type"] in {TaskType.GET_LIVE_VIDEO.value, TaskType.GET_LIVE_AUDIO.value}
        audio_format = payload.get("audio_format", "bestaudio")
        output_format = payload.get("output_format")

        if is_video:
            video_format = payload.get("video_format", "bestvideo")
            if audio_format is None or str(audio_format).lower() in {"none", "null"}:
                format_option = f"{video_format}/bestvideo"
            else:
                format_option = f"{video_format}+{audio_format}/best"
            default_stem = "live_video" if is_live else "video"
        else:
            format_option = f"{audio_format or 'bestaudio'}/bestaudio"
            default_stem = "live_audio" if is_live else "audio"

        custom_name = payload.get("output_filename")
        if custom_name:
            custom_path = Path(custom_name)
            stem = custom_path.stem or default_stem
        else:
            stem = default_stem

        opts = self._base_options()
        opts.update(
            {
                "format": format_option,
                "outtmpl": str(target / f"{stem}.%(ext)s"),
            }
        )

        if output_format:
            if is_video:
                # merge_output_format only influences multi-format merges; the remuxer also
                # guarantees a single already-combined source is emitted in the requested container.
                opts["merge_output_format"] = output_format
                opts["postprocessors"] = [
                    {"key": "FFmpegVideoRemuxer", "preferedformat": output_format}
                ]
            else:
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": output_format}
                ]

        has_download_range = False

        # VOD ranges are expressed relative to the media timeline.
        if payload.get("start_time") is not None or payload.get("end_time") is not None:
            has_download_range = True
            start = self._time_to_seconds(payload.get("start_time", 0))
            end = self._time_to_seconds(payload.get("end_time")) if payload.get("end_time") is not None else float("inf")
            if end <= start:
                raise ValueError("end_time must be greater than start_time")
            opts["download_ranges"] = download_range_func(None, [(start, end)])
            opts["force_keyframes_at_cuts"] = bool(payload.get("force_keyframes", False))

        # For live streams `start` is the relative offset requested by the legacy API.
        # Do not convert it to Unix epoch time (the old implementation did, which was incorrect).
        if is_live and payload.get("duration") is not None:
            has_download_range = True
            start = float(payload.get("start", 0))
            end = start + float(payload["duration"])
            opts["download_ranges"] = download_range_func(None, [(start, end)])
            opts["force_keyframes_at_cuts"] = bool(payload.get("force_keyframes", False))

        reservation_lock = Lock()
        per_file: dict[str, int] = {}
        headroom = self.db.quota_headroom(task["key_name"], task_id)
        if headroom <= 0:
            raise QuotaExceeded("No quota available for this download")
        # FFmpeg section downloads have upstream paths where progress hooks are absent. For
        # those jobs reserve all currently available headroom up front; this is conservative
        # (range jobs for one key may serialize), but it prevents concurrent quota oversubscription.
        reserved = (
            headroom
            if has_download_range
            else min(headroom, self.settings.initial_quota_reservation_bytes)
        )
        self.db.resize_quota_reservation(task_id, task["key_name"], reserved)
        # This is effective for normal downloads when yt-dlp knows the size up front.
        # Range/FFmpeg paths are additionally guarded by the on-disk monitor below.
        opts["max_filesize"] = headroom

        monitor_stop = Event()
        monitor_errors: list[BaseException] = []

        def reserve(wanted: int) -> None:
            nonlocal reserved
            wanted = int(wanted)
            with reservation_lock:
                if wanted <= reserved:
                    return
                self.db.resize_quota_reservation(task_id, task["key_name"], wanted)
                reserved = wanted

        def quota_progress(progress: dict[str, Any]) -> None:
            if monitor_errors:
                raise monitor_errors[0]
            filename = str(progress.get("filename") or progress.get("tmpfilename") or "stream")
            observed = max(
                int(progress.get("downloaded_bytes") or 0),
                int(progress.get("total_bytes") or 0),
                int(progress.get("total_bytes_estimate") or 0),
            )
            with reservation_lock:
                if observed > per_file.get(filename, 0):
                    per_file[filename] = observed
                wanted = int(sum(per_file.values()) * self.settings.quota_size_buffer)
            reserve(wanted)

        def disk_quota_monitor() -> None:
            # yt-dlp currently has execution paths (notably FFmpeg section downloads) where
            # progress hooks may be sparse or absent. Observe the task directory as an
            # independent source of truth so concurrent jobs cannot all assume the bytes are free.
            while not monitor_stop.wait(self.settings.quota_monitor_seconds):
                try:
                    size = sum(
                        path.stat().st_size
                        for path in target.rglob("*")
                        if path.is_file()
                    )
                    reserve(int(size * self.settings.quota_size_buffer))
                except BaseException as exc:  # propagate into the downloader thread on its next hook/end
                    monitor_errors.append(exc)
                    return

        opts["progress_hooks"] = [quota_progress]
        monitor = Thread(target=disk_quota_monitor, name=f"quota-{task_id}", daemon=True)
        monitor.start()

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(task["url"], download=True)
                requested = info.get("requested_downloads") or [] if isinstance(info, dict) else []
                candidates: list[Path] = []
                for item in requested:
                    path = item.get("filepath") if isinstance(item, dict) else None
                    if path:
                        candidates.append(Path(path))
                if isinstance(info, dict):
                    prepared = ydl.prepare_filename(info)
                    if prepared:
                        candidates.append(Path(prepared))
        finally:
            monitor_stop.set()
            monitor.join(timeout=max(1.0, self.settings.quota_monitor_seconds * 4))

        if monitor_errors:
            raise monitor_errors[0]

        final_file = self._find_final_file(target, candidates)
        actual = final_file.stat().st_size
        self.db.finalize_quota(task_id, task["key_name"], actual)
        relative = final_file.relative_to(self.settings.download_dir).as_posix()
        self.db.complete_task(task_id, f"/files/{relative}", actual)

    @staticmethod
    def _find_final_file(target: Path, candidates: list[Path]) -> Path:
        ignored_suffixes = {".part", ".ytdl", ".temp"}
        existing: list[Path] = []
        for candidate in candidates:
            if candidate.is_file() and candidate.parent.resolve() == target.resolve():
                existing.append(candidate)
        for path in target.iterdir():
            if path.is_file() and path.name != "info.json" and path.suffix not in ignored_suffixes:
                existing.append(path)
        # Postprocessors often produce a new extension. Pick the newest/largest stable file deterministically.
        unique = {path.resolve(): path for path in existing}
        if not unique:
            raise RuntimeError("yt-dlp completed but no output file was found")
        return max(unique.values(), key=lambda path: (path.stat().st_mtime_ns, path.stat().st_size, path.name))

    def _remove_partial(self, task_id: str) -> None:
        self.db.release_quota(task_id)
        path = self._task_dir(task_id)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
