"""One adapter per API format: where calls go and how the key is attached.

Phase A only passes calls through. Later phases read and assemble calls here,
per format (the PSE guard reference Sec 12, envelope integrity).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from vid.config import Upstream

# Headers that belong to one hop and must not be forwarded (RFC 9110 7.6.1),
# plus those httpx recomputes itself.
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "trailers", "transfer-encoding", "upgrade", "host",
    "content-length", "accept-encoding",
})


@dataclass(frozen=True)
class Adapter:
    name: str          # also the upstream's name in config
    prefix: str        # local path prefix the agent calls

    def upstream_url(self, upstream: Upstream, path: str, query: str) -> str:
        rest = path[len(self.prefix):]
        return f"{upstream.base_url}{rest}" + (f"?{query}" if query else "")

    def request_headers(self, incoming: list[tuple[str, str]], upstream: Upstream) -> list[tuple[str, str]]:
        out = [(k, v) for k, v in incoming if k.lower() not in HOP_BY_HOP]
        # Plain bytes from the model, so Vid can read what it forwards.
        out.append(("accept-encoding", "identity"))
        if upstream.api_key:
            out = self.attach_key(out, upstream.api_key)
        return out

    def attach_key(self, headers: list[tuple[str, str]], key: str) -> list[tuple[str, str]]:
        raise NotImplementedError

    def error_body(self, message: str, kind: str) -> bytes:
        raise NotImplementedError

    def reply_text(self, body: bytes, stream: bool) -> str:
        """The assistant text in a response, so Vid can watch what leaves.
        Best-effort and format-specific; returns '' when it cannot read it."""
        raise NotImplementedError


def _sse_data(body: bytes) -> list[dict]:
    """The JSON objects on 'data:' lines of a server-sent-events stream."""
    out = []
    for line in body.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload in ("", "[DONE]"):
            continue
        try:
            out.append(json.loads(payload))
        except ValueError:
            pass
    return out


class OpenAIAdapter(Adapter):
    def attach_key(self, headers, key):
        return [(k, v) for k, v in headers if k.lower() != "authorization"] + [("authorization", f"Bearer {key}")]

    def error_body(self, message, kind):
        return json.dumps({"error": {"message": message, "type": kind, "code": kind}}).encode()

    def reply_text(self, body, stream):
        if stream:
            parts = []
            for obj in _sse_data(body):
                for ch in obj.get("choices", []):
                    delta = ch.get("delta") or {}
                    if isinstance(delta.get("content"), str):
                        parts.append(delta["content"])
            return "".join(parts)
        try:
            data = json.loads(body)
        except ValueError:
            return ""
        parts = []
        for ch in data.get("choices", []) if isinstance(data, dict) else []:
            msg = ch.get("message") or {}
            c = msg.get("content")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                parts += [p.get("text", "") for p in c if isinstance(p, dict)]
        return "".join(parts)


class AnthropicAdapter(Adapter):
    def attach_key(self, headers, key):
        drop = {"authorization", "x-api-key"}
        return [(k, v) for k, v in headers if k.lower() not in drop] + [("x-api-key", key)]

    def error_body(self, message, kind):
        return json.dumps({"type": "error", "error": {"type": kind, "message": message}}).encode()

    def reply_text(self, body, stream):
        if stream:
            parts = []
            for obj in _sse_data(body):
                if obj.get("type") == "content_block_delta":
                    delta = obj.get("delta") or {}
                    if isinstance(delta.get("text"), str):
                        parts.append(delta["text"])
            return "".join(parts)
        try:
            data = json.loads(body)
        except ValueError:
            return ""
        content = data.get("content") if isinstance(data, dict) else None
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return ""


ADAPTERS: tuple[Adapter, ...] = (
    AnthropicAdapter("anthropic", "/anthropic"),
    OpenAIAdapter("openai", "/v1"),
)


def adapter_for(path: str) -> Adapter | None:
    for a in ADAPTERS:
        if path == a.prefix or path.startswith(a.prefix + "/"):
            return a
    return None
