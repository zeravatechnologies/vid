"""Phase A proxy: passes every call through unchanged, streaming included.

Each call gets an observation id where it enters (the PSE guard reference Sec 1,
Sec 3). Later phases insert the input layer, the readings and decide()
between `receive` and `forward` below; nothing else in this file changes.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import uuid

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

from vid import __version__
from vid.config import Config
from vid.metrics import Metrics, Sample
from vid.observe import Observer
from vid.proxy.adapters import HOP_BY_HOP, adapter_for

log = logging.getLogger("vid.proxy")

# Response headers that must not be copied back to the agent.
_RESPONSE_DROP = HOP_BY_HOP | {"content-encoding"}

# How much of a reply Vid keeps to watch for leaks (the rest streams untouched).
_REPLY_WATCH_CAP = 4 * 1024 * 1024


def build_app(config: Config, metrics: Metrics | None = None, client: httpx.AsyncClient | None = None,
              observer: Observer | None = None) -> Starlette:
    metrics = metrics or Metrics()
    observer = observer or Observer()
    timeout = httpx.Timeout(connect=config.connect_timeout, read=config.read_timeout, write=None, pool=None)
    owned_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def root(_: Request) -> Response:
        return PlainTextResponse(f"Vid {__version__} is running. Point your agent's base URL here.\n")

    async def proxy(request: Request) -> Response:
        t0 = time.perf_counter()
        observation_id = uuid.uuid4().hex
        adapter = adapter_for(request.url.path)
        if adapter is None:
            return JSONResponse({"error": "Vid: unknown API path. Use /v1/... (OpenAI-compatible) or /anthropic/... (Anthropic)."}, status_code=404)

        upstream = config.upstream(adapter.name)
        body = await request.body()
        observer.observe(body, adapter.name)
        stream = _wants_stream(body)
        outgoing = http.build_request(
            request.method,
            adapter.upstream_url(upstream, request.url.path, request.url.query),
            headers=adapter.request_headers(request.headers.items(), upstream),
            content=body,
        )
        t_sent = time.perf_counter()
        try:
            upstream_response = await http.send(outgoing, stream=True)
        except httpx.HTTPError as e:
            log.warning("obs=%s upstream %s unreachable: %s", observation_id, adapter.name, e)
            metrics.record(Sample(adapter.name, 502, stream, (t_sent - t0) * 1000, 0.0, (time.perf_counter() - t0) * 1000))
            return Response(
                adapter.error_body(f"Vid could not reach the {adapter.name} upstream at {upstream.base_url}: {type(e).__name__}", "vid_upstream_unreachable"),
                status_code=502,
                media_type="application/json",
            )
        t_first = time.perf_counter()
        headers = {k: v for k, v in upstream_response.headers.items() if k.lower() not in _RESPONSE_DROP}

        # Watch the reply too (free edition shows leaks on the way out). Collect
        # a bounded copy while relaying every chunk untouched; analyse at the end.
        collected = bytearray()
        watch = upstream_response.status_code < 300

        async def relay():
            try:
                async for chunk in upstream_response.aiter_raw():
                    if watch and len(collected) < _REPLY_WATCH_CAP:
                        collected.extend(chunk[: _REPLY_WATCH_CAP - len(collected)])
                    yield chunk
            finally:
                t_end = time.perf_counter()
                metrics.record(Sample(adapter.name, upstream_response.status_code, stream,
                                      (t_sent - t0) * 1000, (t_first - t_sent) * 1000, (t_end - t0) * 1000))
                if watch:
                    try:
                        observer.observe_reply(adapter.reply_text(bytes(collected), stream), adapter.name)
                    except Exception as e:  # watching must never break the stream
                        log.warning("obs=%s reply watch failed: %s", observation_id, e)
                log.info("obs=%s %s %s -> %s", observation_id, request.method, request.url.path, upstream_response.status_code)

        return StreamingResponse(
            relay(),
            status_code=upstream_response.status_code,
            headers=headers,
            background=BackgroundTask(upstream_response.aclose),
        )

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette):
        yield
        if owned_client:
            await http.aclose()

    app = Starlette(
        routes=[
            Route("/", root, methods=["GET"]),
            Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        ],
        lifespan=lifespan,
    )
    app.state.metrics = metrics
    app.state.observer = observer
    return app


def _wants_stream(body: bytes) -> bool:
    """True when the call asks for a streamed reply (both formats use "stream": true)."""
    try:
        data = json.loads(body) if body else None
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(data, dict) and data.get("stream") is True
