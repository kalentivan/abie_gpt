import os
import sqlite3
import sys
from pathlib import Path

path = Path(os.getenv("SQLITE_PATH", "/data/abie_gpt.db"))
try:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=2) as db:
        db.execute("SELECT 1")
except Exception as exc:
    print(exc)
    sys.exit(1)
