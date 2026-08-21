#!/usr/bin/env python3
import logging

from yt_dlp_host.config import settings
from yt_dlp_host.db import Database
from yt_dlp_host.migration import migrate_legacy_json

logging.basicConfig(level=logging.INFO)
if settings.storage_backend != "sqlite":
    raise SystemExit("Legacy migration is only needed with STORAGE_BACKEND=sqlite; JSON mode uses the files directly")
db = Database(settings)
db.initialize()
keys, tasks = migrate_legacy_json(db)
print(f"Imported {keys} keys and {tasks} tasks")
