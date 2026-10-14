"""Reads what passes through and keeps a running record for the operator.

Vid reads every interlocutor message (the PSE guard reference Sec 9) and, since the
free edition only watches, it also reads the model's REPLY to show secrets
that leak out. The model still receives the original and nothing is blocked
(free edition, decision 13 Oct 2026). Presentation is to the operator only
(Sec 4). This observes; it stops nothing — stopping is Perun.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass

from vid.input_layer import ALL_NAMES, analyze


def _messages(body: bytes) -> list[tuple[str, str]]:
    """(role, text) for each interlocutor turn in a request, both API formats.
    The system's own turns are skipped; the role is kept as provenance."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    out: list[tuple[str, str]] = []
    for m in data.get("messages", []):
        if not isinstance(m, dict):
            continue
        role = m.get("role", "user")
        if role in ("system", "assistant"):
            continue
        for text in _content_text(m.get("content")):
            out.append((role, text))
    for key in ("input", "prompt"):
        if isinstance(data.get(key), str):
            out.append(("input", data[key]))
    return out


def _content_text(content) -> list[str]:
    if isinstance(content, str):
        return [content]
    out = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    out.append(part["text"])
                elif isinstance(part.get("content"), (str, list)):
                    out.extend(_content_text(part["content"]))
    return out


# Secret shapes to watch for in the model's reply. Conservative, to keep the
# false-positive rate near zero (a watcher that cries wolf is worse than none).
_SECRETS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}")),
    ("OpenAI key", re.compile(r"sk-(?!ant-)[A-Za-z0-9_-]{20,}")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
)


def _mask(s: str) -> str:
    """Show enough to recognise a secret, never the whole thing."""
    s = s.splitlines()[0]
    return s if len(s) <= 10 else s[:6] + "…" + s[-2:]


def scan_reply(text: str) -> list[tuple[str, str]]:
    """[(kind, masked sample)] for secret-shaped strings in the reply."""
    out = []
    for kind, pat in _SECRETS:
        for m in pat.finditer(text):
            out.append((kind, _mask(m.group(0))))
    return out


@dataclass
class Sighting:
    at: float
    adapter: str
    source: str          # provenance: the role the text came from
    codes: list[str]
    sample: str

    def as_dict(self) -> dict:
        return {"at": round(self.at, 3), "adapter": self.adapter, "source": self.source,
                "codes": [{"code": c, "name": ALL_NAMES.get(c, c)} for c in self.codes],
                "sample": self.sample}


@dataclass
class ReplyLeak:
    at: float
    adapter: str
    leaks: list[tuple[str, str]]   # (kind, masked)

    def as_dict(self) -> dict:
        return {"at": round(self.at, 3), "adapter": self.adapter,
                "leaks": [{"kind": k, "sample": s} for k, s in self.leaks]}


class Observer:
    """Reads requests and replies off the proxy thread-safely; the proxy never
    waits on it."""

    def __init__(self, keep: int = 200):
        self._lock = threading.Lock()
        self._recent: deque[Sighting] = deque(maxlen=keep)
        self._recent_leaks: deque[ReplyLeak] = deque(maxlen=keep)
        self.messages_read = 0
        self.with_hidden = 0
        self.code_counts: Counter[str] = Counter()
        self.replies_read = 0
        self.replies_with_leak = 0
        self.leak_counts: Counter[str] = Counter()

    def observe(self, body: bytes, adapter: str) -> None:
        for source, text in _messages(body):
            if not text.strip():
                continue
            result = analyze(text, provenance="external")
            with self._lock:
                self.messages_read += 1
                if result.hidden:
                    self.with_hidden += 1
                    self.code_counts.update(result.codes())
                    self._recent.append(Sighting(time.time(), adapter, source, result.codes(), result.readable[:200]))

    def observe_reply(self, reply_text: str, adapter: str) -> None:
        if not reply_text.strip():
            return
        leaks = scan_reply(reply_text)
        with self._lock:
            self.replies_read += 1
            if leaks:
                self.replies_with_leak += 1
                self.leak_counts.update(k for k, _ in leaks)
                self._recent_leaks.append(ReplyLeak(time.time(), adapter, leaks))

    def summary(self) -> dict:
        with self._lock:
            return {
                "messages_read": self.messages_read,
                "messages_with_hidden_content": self.with_hidden,
                "by_code": [{"code": c, "name": ALL_NAMES.get(c, c), "count": n}
                            for c, n in self.code_counts.most_common()],
                "recent": [s.as_dict() for s in list(self._recent)[-20:]],
                "replies": {
                    "read": self.replies_read,
                    "with_leak": self.replies_with_leak,
                    "by_kind": [{"kind": k, "count": n} for k, n in self.leak_counts.most_common()],
                    "recent": [r.as_dict() for r in list(self._recent_leaks)[-20:]],
                },
            }
