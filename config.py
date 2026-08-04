"""Persistent user settings and logging, stored under %LOCALAPPDATA%\\WingetUpgradeManager."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from pathlib import Path

APP_DIR_NAME = "WingetUpgradeManager"

DEFAULTS = {
    "appearance": "dark",  # "system" | "light" | "dark"
    "skipped_ids": [],  # package IDs deselected by the user, remembered across scans
}

logger = logging.getLogger(__name__)


def config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    directory = Path(base) / APP_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def config_path() -> Path:
    return config_dir() / "config.json"


def log_path() -> Path:
    return config_dir() / "app.log"


def load_config() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {**DEFAULTS, **data}
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read config, using defaults: %s", exc)
    return {key: (list(value) if isinstance(value, list) else value) for key, value in DEFAULTS.items()}


def save_config(config: dict) -> None:
    try:
        config_path().write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("Could not save config: %s", exc)


def setup_logging() -> None:
    """Log to a small rotating file so failed upgrades can be diagnosed."""
    handler = logging.handlers.RotatingFileHandler(
        log_path(), maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])
