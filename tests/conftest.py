from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from fake_upstream import Recorder, build_fake
from vid.config import Config
from vid.control_api import build_control_app
from vid.metrics import Metrics
from vid.observe import Observer
from vid.proxy.app import build_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LiveServer:
    def __init__(self, app):
        self.port = free_port()
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="on"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError("server did not start")
            time.sleep(0.02)
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def fake():
    recorder = Recorder()
    with LiveServer(build_fake(recorder)) as srv:
        srv.recorder = recorder
        yield srv


def make_guard(fake_url: str, **upstream_over):
    over = {"upstream": {
        "openai": {"base_url": f"{fake_url}/v1", **upstream_over.get("openai", {})},
        "anthropic": {"base_url": fake_url, **upstream_over.get("anthropic", {})},
    }}
    config = Config.from_dict(over)
    metrics = Metrics()
    observer = Observer()
    srv = LiveServer(build_app(config, metrics, observer=observer))
    srv.observer = observer
    return config, metrics, srv


@pytest.fixture
def guard(fake, monkeypatch):
    monkeypatch.delenv("VID_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VID_ANTHROPIC_API_KEY", raising=False)
    config, metrics, srv = make_guard(fake.url)
    with srv:
        srv.config, srv.metrics = config, metrics
        yield srv
