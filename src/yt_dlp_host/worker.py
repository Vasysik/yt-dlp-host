from __future__ import annotations

import logging
import os
import shutil
import signal
import socket
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from .config import settings
from .db import Database
from .downloader import DownloadEngine
from .migration import migrate_legacy_json

log = logging.getLogger(__name__)


class Worker:
    def __init__(self) -> None:
        self.db = Database(settings)
        self.db.initialize()
        migrate_legacy_json(self.db)
        self.engine = DownloadEngine(settings, self.db)
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=settings.max_workers, thread_name_prefix="download")
        self.active: dict[Future[None], str] = {}
        self.last_heartbeat = 0.0
        self.last_cleanup = 0.0

    def stop(self, *_args: object) -> None:
        self.stop_event.set()

    def run(self) -> None:
        log.info("Worker %s started with %d slots", self.worker_id, settings.max_workers)
        while not self.stop_event.is_set():
            self._collect_finished()
            self._heartbeat()
            self._cleanup()
            while len(self.active) < settings.max_workers:
                task = self.db.claim_next_task(self.worker_id)
                if task is None:
                    break
                future = self.executor.submit(self.engine.process, task)
                self.active[future] = task["task_id"]
            self.stop_event.wait(settings.worker_poll_seconds)

        log.info("Worker %s stopping; waiting for active downloads", self.worker_id)
        self.executor.shutdown(wait=True, cancel_futures=False)

    def _collect_finished(self) -> None:
        for future, task_id in list(self.active.items()):
            if not future.done():
                continue
            self.active.pop(future, None)
            try:
                future.result()
            except Exception:
                # DownloadEngine normally records failures itself; this catches worker bugs.
                log.exception("Unhandled worker failure for task %s", task_id)
                self.db.fail_task(task_id, "Unhandled worker failure")

    def _heartbeat(self) -> None:
        now = time.monotonic()
        interval = max(10.0, settings.worker_lease_seconds / 3)
        if now - self.last_heartbeat < interval:
            return
        for task_id in self.active.values():
            self.db.extend_lease(task_id, self.worker_id)
        self.last_heartbeat = now

    def _cleanup(self) -> None:
        now = time.monotonic()
        if now - self.last_cleanup < 30:
            return
        for task_id in self.db.expired_tasks():
            task_dir = settings.download_dir / task_id
            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)
            self.db.delete_task(task_id)
        self.last_cleanup = now


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    worker = Worker()
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    worker.run()


if __name__ == "__main__":
    main()
