"""Phase A exit criterion: an agent works through Vid with no visible
difference, streaming included (plan, Faza A)."""

from __future__ import annotations

import time

import anthropic
import httpx
import openai
import pytest

from conftest import LiveServer, make_guard
from fake_upstream import PIECES, STREAM_DELAY_S

TEXT = "".join(PIECES)
MSG = [{"role": "user", "content": "hi"}]


# -- OpenAI-compatible --------------------------------------------------------

def test_openai_sdk_through_perun(guard):
    client = openai.OpenAI(base_url=f"{guard.url}/v1", api_key="agent-key")
    r = client.chat.completions.create(model="fake-1", messages=MSG)
    assert r.choices[0].message.content == TEXT


def test_openai_sdk_streams_through_perun(guard):
    client = openai.OpenAI(base_url=f"{guard.url}/v1", api_key="agent-key")
    t0 = time.perf_counter()
    arrivals, parts = [], []
    for chunk in client.chat.completions.create(model="fake-1", messages=MSG, stream=True):
        if chunk.choices and chunk.choices[0].delta.content:
            arrivals.append(time.perf_counter() - t0)
            parts.append(chunk.choices[0].delta.content)
    assert "".join(parts) == TEXT
    # Relayed, not buffered: the first piece arrives long before the last.
    assert arrivals[0] < STREAM_DELAY_S
    assert arrivals[-1] - arrivals[0] > STREAM_DELAY_S * (len(PIECES) - 2)


def test_models_list_passes(guard):
    client = openai.OpenAI(base_url=f"{guard.url}/v1", api_key="agent-key")
    assert [m.id for m in client.models.list()] == ["fake-1"]


# -- Anthropic ------------------------------------------------------------------

def test_anthropic_sdk_through_perun(guard):
    client = anthropic.Anthropic(base_url=f"{guard.url}/anthropic", api_key="agent-key")
    r = client.messages.create(model="fake-1", max_tokens=16, messages=MSG)
    assert r.content[0].text == TEXT


def test_anthropic_sdk_streams_through_perun(guard):
    client = anthropic.Anthropic(base_url=f"{guard.url}/anthropic", api_key="agent-key")
    t0 = time.perf_counter()
    arrivals, parts = [], []
    with client.messages.stream(model="fake-1", max_tokens=16, messages=MSG) as s:
        for piece in s.text_stream:
            arrivals.append(time.perf_counter() - t0)
            parts.append(piece)
    assert "".join(parts) == TEXT
    assert arrivals[0] < STREAM_DELAY_S * 1.5
    assert arrivals[-1] - arrivals[0] > STREAM_DELAY_S * (len(PIECES) - 2)


# -- No visible difference --------------------------------------------------------

@pytest.mark.parametrize("path,body", [
    ("/v1/chat/completions", {"model": "fake-1", "messages": MSG}),
    ("/v1/chat/completions", {"model": "fake-1", "messages": MSG, "stream": True}),
    ("/v1/chat/completions", {"model": "fail-500", "messages": MSG}),
])
def test_same_bytes_direct_and_through_perun(fake, guard, path, body):
    direct = httpx.post(f"{fake.url}{path}", json=body)
    through = httpx.post(f"{guard.url}{path}", json=body)
    assert through.status_code == direct.status_code
    assert through.content == direct.content
    assert through.headers["content-type"] == direct.headers["content-type"]


def test_anthropic_same_bytes(fake, guard):
    body = {"model": "fake-1", "max_tokens": 16, "messages": MSG, "stream": True}
    direct = httpx.post(f"{fake.url}/v1/messages", json=body)
    through = httpx.post(f"{guard.url}/anthropic/v1/messages", json=body)
    assert through.status_code == direct.status_code
    assert through.content == direct.content


# -- Keys -----------------------------------------------------------------------

def test_agent_key_passes_when_vid_has_none(fake, guard):
    openai.OpenAI(base_url=f"{guard.url}/v1", api_key="agent-key").chat.completions.create(model="fake-1", messages=MSG)
    assert fake.recorder.last()["headers"]["authorization"] == "Bearer agent-key"
    assert fake.recorder.last()["headers"]["accept-encoding"] == "identity"


def test_vid_key_replaces_agent_key(fake, monkeypatch):
    monkeypatch.delenv("VID_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VID_ANTHROPIC_API_KEY", raising=False)
    _, _, srv = make_guard(fake.url, openai={"api_key": "vid-openai"}, anthropic={"api_key": "vid-anthropic"})
    with srv:
        openai.OpenAI(base_url=f"{srv.url}/v1", api_key="agent-key").chat.completions.create(model="fake-1", messages=MSG)
        assert fake.recorder.last()["headers"]["authorization"] == "Bearer vid-openai"
        anthropic.Anthropic(base_url=f"{srv.url}/anthropic", api_key="agent-key").messages.create(model="fake-1", max_tokens=8, messages=MSG)
        h = fake.recorder.last()["headers"]
        assert h["x-api-key"] == "vid-anthropic"
        assert "authorization" not in h


def test_env_key_wins_over_config(fake, monkeypatch):
    monkeypatch.setenv("VID_OPENAI_API_KEY", "from-env")
    _, _, srv = make_guard(fake.url, openai={"api_key": "from-config"})
    with srv:
        httpx.post(f"{srv.url}/v1/chat/completions", json={"model": "fake-1", "messages": MSG})
        assert fake.recorder.last()["headers"]["authorization"] == "Bearer from-env"


# -- Failures -------------------------------------------------------------------------

def test_unreachable_upstream_gives_api_shaped_502(monkeypatch):
    monkeypatch.delenv("VID_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VID_ANTHROPIC_API_KEY", raising=False)
    _, metrics, srv = make_guard("http://127.0.0.1:9")  # discard port: nothing listens
    with srv:
        r = httpx.post(f"{srv.url}/v1/chat/completions", json={"model": "x", "messages": MSG})
        assert r.status_code == 502
        assert r.json()["error"]["type"] == "vid_upstream_unreachable"
        a = httpx.post(f"{srv.url}/anthropic/v1/messages", json={"model": "x", "max_tokens": 1, "messages": MSG})
        assert a.status_code == 502 and a.json()["type"] == "error"
        assert metrics.summary()["upstream_errors"] == 2


def test_unknown_path_is_404(guard):
    assert httpx.post(f"{guard.url}/other/thing", json={}).status_code == 404


def test_root_says_running(guard):
    assert "Vid" in httpx.get(f"{guard.url}/").text


# -- Latency is measured from phase A on ----------------------------------------------

def test_overhead_is_recorded(guard):
    for _ in range(5):
        httpx.post(f"{guard.url}/v1/chat/completions", json={"model": "fake-1", "messages": MSG})
    s = guard.metrics.summary()
    assert s["requests"] == 5
    assert s["overhead_ms"]["median"] is not None and s["overhead_ms"]["median"] < 50


# -- Phase 1: Vid reads hidden text but forwards the original (decision 13 Oct) --

def test_proxy_reads_hidden_text_but_forwards_original(fake, guard):
    import base64
    hidden = "read this " + base64.b64encode(b"the quick brown fox").decode()
    body = {"model": "fake-1", "messages": [{"role": "user", "content": hidden}]}
    httpx.post(f"{guard.url}/v1/chat/completions", json=body)
    # The model received the original, unchanged.
    assert fake.recorder.last()["body"] == httpx.Request("POST", "http://x", json=body).content
    # Vid saw what was hidden.
    seen = guard.observer.summary()
    assert seen["messages_with_hidden_content"] == 1
    assert any(c["code"] == "PIT-E-07" for c in seen["by_code"])
    assert "the quick brown fox" in seen["recent"][-1]["sample"]


def test_proxy_does_not_flag_clean_text(fake, guard):
    body = {"model": "fake-1", "messages": [{"role": "user", "content": "Please summarise the report."}]}
    httpx.post(f"{guard.url}/v1/chat/completions", json=body)
    seen = guard.observer.summary()
    assert seen["messages_read"] == 1 and seen["messages_with_hidden_content"] == 0


# -- Phase 2: Vid watches the reply for leaks (observation only) --

def test_reply_leak_seen_openai_nonstream(fake, guard):
    body = {"model": "leak-key", "messages": [{"role": "user", "content": "key?"}]}
    httpx.post(f"{guard.url}/v1/chat/completions", json=body)
    import time as _t
    for _ in range(50):
        s = guard.observer.summary()["replies"]
        if s["read"]:
            break
        _t.sleep(0.05)
    assert s["with_leak"] == 1
    assert any(k["kind"] == "Anthropic key" for k in s["by_kind"])
    # The secret is masked, never stored whole.
    sample = s["recent"][-1]["leaks"][0]["sample"]
    assert "…" in sample and "A" * 28 not in sample


def test_reply_leak_seen_openai_stream(fake, guard):
    body = {"model": "leak-key", "messages": [{"role": "user", "content": "key?"}], "stream": True}
    with httpx.stream("POST", f"{guard.url}/v1/chat/completions", json=body) as r:
        for _ in r.iter_bytes():
            pass
    import time as _t
    for _ in range(50):
        s = guard.observer.summary()["replies"]
        if s["read"]:
            break
        _t.sleep(0.05)
    assert s["with_leak"] == 1


def test_reply_leak_seen_anthropic_stream(fake, guard):
    body = {"model": "leak-key", "max_tokens": 32, "messages": [{"role": "user", "content": "key?"}], "stream": True}
    with httpx.stream("POST", f"{guard.url}/anthropic/v1/messages", json=body) as r:
        for _ in r.iter_bytes():
            pass
    import time as _t
    for _ in range(50):
        s = guard.observer.summary()["replies"]
        if s["read"]:
            break
        _t.sleep(0.05)
    assert s["with_leak"] == 1


def test_clean_reply_has_no_leak(fake, guard):
    body = {"model": "fake-1", "messages": [{"role": "user", "content": "hi"}]}
    httpx.post(f"{guard.url}/v1/chat/completions", json=body)
    import time as _t
    for _ in range(50):
        s = guard.observer.summary()["replies"]
        if s["read"]:
            break
        _t.sleep(0.05)
    assert s["read"] == 1 and s["with_leak"] == 0


def test_provenance_recorded_on_request_sighting(fake, guard):
    import base64
    hidden = "look " + base64.b64encode(b"the quick brown fox").decode()
    body = {"model": "fake-1", "messages": [{"role": "tool", "content": hidden}]}
    httpx.post(f"{guard.url}/v1/chat/completions", json=body)
    rec = guard.observer.summary()["recent"]
    assert rec and rec[-1]["source"] == "tool"
