from __future__ import annotations

import sqlite3
import os
from pathlib import Path


LOCAL_STORE_DB_FILE = "npc_visual.sqlite3"
LOCAL_STORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS visual_npc_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    script TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_program_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "XiamiToolbox"
    return Path.home() / ".xiami_toolbox"


def local_store_path() -> Path:
    config_dir = get_program_dir() / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / LOCAL_STORE_DB_FILE


def connect_local_store(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else local_store_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(LOCAL_STORE_SCHEMA)
    conn.commit()
    return conn


__all__ = ["connect_local_store", "local_store_path"]
