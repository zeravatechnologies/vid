"""Runs the proxy and the control channel in one process."""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from vid.config import Config
from vid.control_api import build_control_app, ensure_token
from vid.metrics import Metrics
from vid.observe import Observer
from vid.proxy.app import build_app


def _server(app, host: str, port: int) -> uvicorn.Server:
    cfg = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False, lifespan="on")
    server = uvicorn.Server(cfg)
    server.install_signal_handlers = lambda: None  # one handler for both, below
    return server


async def serve(config: Config) -> None:
    metrics = Metrics()
    observer = Observer()
    token = ensure_token()
    proxy = _server(build_app(config, metrics, observer=observer), config.host, config.port)
    control = _server(build_control_app(config, metrics, token, observer), "127.0.0.1", config.control_port)
    logging.getLogger("vid").info("Vid listening on http://%s:%d (control on 127.0.0.1:%d)", config.host, config.port, config.control_port)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    try:
        import signal
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
    except (NotImplementedError, AttributeError):
        pass  # Windows: Ctrl+C raises KeyboardInterrupt, the service manager stops the process

    tasks = [asyncio.create_task(proxy.serve()), asyncio.create_task(control.serve())]
    waiter = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait([*tasks, waiter], return_when=asyncio.FIRST_COMPLETED)
    proxy.should_exit = control.should_exit = True
    await asyncio.gather(*tasks, return_exceptions=True)
    waiter.cancel()
