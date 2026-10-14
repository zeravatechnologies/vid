from __future__ import annotations

import os
import stat
import sys

import httpx
import pytest

from conftest import LiveServer
from vid.config import NOT_SET, Config
from vid.control_api import build_control_app, ensure_token
from vid.metrics import Metrics


def test_token_created_once_owner_only(tmp_path):
    p = tmp_path / "control.token"
    t1 = ensure_token(p)
    assert ensure_token(p) == t1 and len(t1) >= 32
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_control_api_requires_token_and_states_what_is_not_protected():
    config = Config.from_dict({})
    with LiveServer(build_control_app(config, Metrics(), "secret")) as srv:
        assert httpx.get(f"{srv.url}/health").json() == {"ok": True}
        assert httpx.get(f"{srv.url}/status").status_code == 401
        assert httpx.get(f"{srv.url}/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
        s = httpx.get(f"{srv.url}/status", headers={"Authorization": "Bearer secret"}).json()
        assert s["protection"]["mode"] == "observe"
        assert s["protection"]["not_protected"] and s["protection"]["protected"]
        assert s["constants"]["K_C"] == "not set"
        assert s["upstreams"]["openai"]["vid_key_set"] is False


def test_constants_from_reference():
    c = Config.from_dict({})
    assert c.constant("RUN_N") == 3
    assert c.constant("THETA_BAND") == [25, 35]
    assert c.constant("K_N") is NOT_SET
    with pytest.raises(KeyError):
        c.constant("NO_SUCH_THING")


def test_user_file_overrides_defaults(tmp_path):
    f = tmp_path / "vid.toml"
    f.write_text('[server]\nport = 9999\n[upstream.openai]\nbase_url = "http://127.0.0.1:8080/v1/"\n', "utf-8")
    c = Config.load(f)
    assert c.port == 9999 and c.control_port == 8788
    assert c.upstream("openai").base_url == "http://127.0.0.1:8080/v1"
    assert c.source == f
