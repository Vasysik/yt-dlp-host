from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("DOWNLOAD_DIR", str(ROOT / ".test-downloads"))
os.environ.setdefault("DATABASE_PATH", str(ROOT / ".test-data" / "test.sqlite3"))
