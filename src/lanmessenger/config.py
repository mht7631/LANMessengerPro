from __future__ import annotations
import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LANMessengerPro"
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DIR / "messenger.db"
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_RECEIVE_DIR = APP_DIR / "Received"

DEFAULTS = {
    "display_name": "My Computer",
    "theme": "light",
    "receive_dir": str(DEFAULT_RECEIVE_DIR),
    "start_minimized": False,
    "trusted_peers": {},
}

def load_config() -> dict:
    data = DEFAULTS.copy()
    try:
        if CONFIG_PATH.exists():
            data.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
    return data

def save_config(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
