"""Where Vid keeps its configuration and data on each system."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def config_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Vid"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "vid"


def data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Vid"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "vid"


def config_file() -> Path:
    return Path(os.environ.get("VID_CONFIG", config_dir() / "vid.toml"))


def token_file() -> Path:
    return data_dir() / "control.token"
