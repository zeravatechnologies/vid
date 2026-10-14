"""Configuration: packaged defaults, overridden by the user's file.

Every number Vid uses comes from here, never from code (the PSE guard reference).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from vid import paths


class _NotSet:
    """A constant that has no value yet. Shown as "not set", never guessed."""

    def __repr__(self) -> str:
        return "not set"

    def __bool__(self) -> bool:
        return False


NOT_SET = _NotSet()


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@dataclass(frozen=True)
class Upstream:
    name: str
    base_url: str
    api_key: str


class Config:
    def __init__(self, data: dict[str, Any], source: Path | None = None):
        self.data = data
        self.source = source

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        defaults = tomllib.loads(resources.files("vid").joinpath("defaults.toml").read_text("utf-8"))
        path = path or paths.config_file()
        if path.is_file():
            with path.open("rb") as fh:
                return cls(_merge(defaults, tomllib.load(fh)), path)
        return cls(defaults, None)

    @classmethod
    def from_dict(cls, over: dict[str, Any]) -> "Config":
        """Defaults overridden by `over`; for tests and embedding."""
        defaults = tomllib.loads(resources.files("vid").joinpath("defaults.toml").read_text("utf-8"))
        return cls(_merge(defaults, over), None)

    # -- server --------------------------------------------------------------
    @property
    def host(self) -> str:
        return self.data["server"]["host"]

    @property
    def port(self) -> int:
        return int(self.data["server"]["port"])

    @property
    def control_port(self) -> int:
        return int(self.data["server"]["control_port"])

    # -- upstreams -----------------------------------------------------------
    def upstream(self, name: str) -> Upstream:
        u = self.data["upstream"][name]
        key = os.environ.get(f"VID_{name.upper()}_API_KEY") or u.get("api_key", "")
        return Upstream(name, u["base_url"].rstrip("/"), key)

    @property
    def connect_timeout(self) -> float:
        return float(self.data["upstream"]["timeouts"]["connect_s"])

    @property
    def read_timeout(self) -> float | None:
        v = float(self.data["upstream"]["timeouts"]["read_s"])
        return v if v > 0 else None

    # -- constants (REFERENCE Sec 14) ------------------------------------------
    def constant(self, name: str) -> Any:
        c = self.data.get("constants", {})
        if name in c.get("not_set", {}).get("names", []) and name not in c:
            return NOT_SET
        if name not in c:
            raise KeyError(f"unknown constant {name!r}")
        return c[name]

    def constants_view(self) -> dict[str, Any]:
        """Every constant with its value, or "not set": what the UI shows."""
        c = {k: v for k, v in self.data.get("constants", {}).items() if k != "not_set"}
        for n in self.data.get("constants", {}).get("not_set", {}).get("names", []):
            c.setdefault(n, "not set")
        return c
