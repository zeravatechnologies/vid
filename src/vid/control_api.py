"""Local channel between the core and the Vid window.

Listens on localhost only and answers only with the token from
`paths.token_file()`, which the core writes once with owner-only access.
The window reads and confirms; it never changes protection directly.
"""

from __future__ import annotations

import hmac
import os
import secrets
import sys
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from vid import __version__, paths
from vid.config import Config
from vid.metrics import Metrics
from vid.observe import Observer

# What is protected in this build, stated as plainly as what is not
# (plan: the UI states what is NOT protected as visibly as what is).
PROTECTION = {
    "phase": "1 (free edition: sees, does not stop)",
    "mode": "observe",
    "protected": [
        "Hidden and encoded text is read before your agent sees it: 42 kinds "
        "of disguise (invisible characters, look-alike letters, Base64 and "
        "other encodings, text inside JSON/XML/Markdown, control tokens).",
        "The model's reply is watched on the way out for secrets that leak "
        "(API keys, tokens, private keys), shown here, masked.",
        "What was hidden, and where it came from, is shown to you here.",
    ],
    "not_protected": [
        "Vid shows, it does not stop: the model still receives the original "
        "message. Stopping is Perun, the paid edition.",
        "It does not read the MEANING of a message (no language reading); that is Perun.",
        "It does not hold or decide actions; that is Perun.",
        "Coverage is by design, not measured; Keel will measure it.",
    ],
}


def ensure_token(path: Path | None = None) -> str:
    path = path or paths.token_file()
    if path.is_file():
        return path.read_text("utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    if sys.platform == "win32":
        pass  # %LOCALAPPDATA% is per-user already; ACL hardening comes with the Windows service
    return token


def build_control_app(config: Config, metrics: Metrics, token: str, observer: Observer | None = None) -> Starlette:
    def authorized(request: Request) -> bool:
        given = request.headers.get("authorization", "")
        return hmac.compare_digest(given, f"Bearer {token}")

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def status(request: Request) -> JSONResponse:
        if not authorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        upstreams = {}
        for name in ("openai", "anthropic"):
            u = config.upstream(name)
            upstreams[name] = {"base_url": u.base_url, "vid_key_set": bool(u.api_key)}
        return JSONResponse({
            "version": __version__,
            "config_file": str(config.source) if config.source else None,
            "listen": f"http://{config.host}:{config.port}",
            "upstreams": upstreams,
            "protection": PROTECTION,
            "traffic": metrics.summary(),
            "seen": observer.summary() if observer else None,
            "constants": config.constants_view(),
        })

    return Starlette(routes=[
        Route("/health", health, methods=["GET"]),
        Route("/status", status, methods=["GET"]),
    ])
