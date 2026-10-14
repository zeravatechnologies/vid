"""What the input layer returns. Plain data, so the proxy, the window and the
web page all read the same result."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from vid.input_layer.codes import ALL_NAMES, BASIC_LAYER, GROUP


@dataclass
class Finding:
    code: str                  # PIT code
    detail: str                # one plain sentence for a person
    excerpt: str = ""          # what was received (shortened)
    revealed: str = ""         # what it says once undone
    chain: list[str] = field(default_factory=list)   # for layered decoding
    count: int = 1

    @property
    def name(self) -> str:
        return ALL_NAMES.get(self.code, self.code)

    @property
    def group(self) -> str:
        return GROUP.get(self.code, "signal")

    def as_dict(self) -> dict:
        d = asdict(self)
        d["name"], d["group"] = self.name, self.group
        return d


@dataclass
class Analysis:
    raw: str                   # the payload as received (kept, Sec 3)
    readable: str              # what it says once everything is undone
    findings: list[Finding]
    provenance: str = "external"

    @property
    def hidden(self) -> bool:
        """True when something was concealed. Flattening a structure is
        ordinary reading, not concealment, so it alone does not count."""
        return any(f.group != "structure" for f in self.findings)

    def codes(self) -> list[str]:
        return sorted({f.code for f in self.findings})

    def as_dict(self) -> dict:
        return {"provenance": self.provenance, "readable": self.readable, "hidden": self.hidden,
                "codes": self.codes(), "findings": [f.as_dict() for f in self.findings]}


def short(s: str, n: int = 120) -> str:
    s = s.replace("\n", "⏎")
    return s if len(s) <= n else s[: n - 1] + "…"
