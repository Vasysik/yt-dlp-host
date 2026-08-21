from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .db import Database

log = logging.getLogger(__name__)
MIGRATION_KEY = "legacy_json_import_v1"


def _load_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"Legacy JSON file must contain an object: {path}")
    return value


def migrate_legacy_json(db: Database) -> tuple[int, int]:
    if db.get_metadata(MIGRATION_KEY) == "done":
        return 0, 0

    keys = _load_object(db.settings.legacy_keys_file)
    tasks = _load_object(db.settings.legacy_tasks_file)

    imported_keys = 0
    imported_tasks = 0
    for name, info in keys.items():
        if not isinstance(info, dict) or not info.get("key"):
            continue
        db.import_key(
            name=name,
            secret=str(info["key"]),
            permissions=list(info.get("permissions", [])),
            quota_bytes=int(info.get("memory_quota", db.settings.default_quota_bytes)),
            last_access=info.get("last_access"),
        )
        imported_keys += 1

    for task_id, data in tasks.items():
        if not isinstance(data, dict):
            continue
        db.import_task(task_id, data)
        imported_tasks += 1

    db.set_metadata(MIGRATION_KEY, "done")
    if imported_keys or imported_tasks:
        log.info("Imported legacy JSON state: %s keys, %s tasks", imported_keys, imported_tasks)
    return imported_keys, imported_tasks
