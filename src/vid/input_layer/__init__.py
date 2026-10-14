"""The input layer, "DL1" (the PSE guard reference Sec 3): makes input readable.

    analyze(text, provenance="external") -> Analysis

Deterministic and dependency-free (it also runs in the browser). In the free
Vid it only observes: the model still receives the original (decision of
13 Oct 2026); what was found is shown to the operator.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from importlib import resources

from vid.input_layer import control_tokens, decoders, normalize, signals as signal_mod, structure
from vid.input_layer.codes import ALL_NAMES, ATTRIBUTION, BASIC_LAYER
from vid.input_layer.types import Analysis, Finding, short

__all__ = ["analyze", "Analysis", "Finding", "BASIC_LAYER", "ALL_NAMES", "ATTRIBUTION", "settings"]


@lru_cache(maxsize=1)
def _default_settings() -> dict:
    data = tomllib.loads(resources.files("vid").joinpath("defaults.toml").read_text("utf-8"))
    return dict(data["input_layer"])


def settings(over: dict | None = None) -> dict:
    s = dict(_default_settings())
    if over:
        s.update(over)
    return s


def _process(text: str, s: dict, depth: int, chain: list[str], findings: list[Finding], own: bool) -> str:
    text, f = normalize.normalize(text, s)
    findings.extend(f)
    if not own:
        text, f = control_tokens.remove(text)
        findings.extend(f)
    text, f = structure.flatten(text)
    findings.extend(f)
    if depth >= s["max_depth"]:
        return text
    for code, excerpt, decoded in decoders.decode_once(text):
        inner: list[Finding] = []
        plain = _process(decoded, s, depth + 1, chain + [code], inner, own)
        findings.append(Finding(code, _DECODE_DETAIL.get(code, "Encoded text decoded."), short(excerpt), short(plain)))
        findings.extend(inner)
        if inner and any(i.group == "decoder" for i in inner):
            layers = [code] + [i.code for i in inner if i.group == "decoder"]
            findings.append(Finding("PIT-E-57", f"Text encoded in {len(layers)} layers, undone one after another ({' → '.join(BASIC_LAYER[c] for c in layers)}).",
                                    short(excerpt), short(plain), chain=layers))
        text = text.replace(excerpt, plain, 1)
    return text


_DECODE_DETAIL = {
    "PIT-E-01": "Numbers standing for letters (A=1 … Z=26) decoded.",
    "PIT-E-06": "Baconian cipher (groups of A and B) decoded.",
    "PIT-E-07": "Base64 decoded.",
    "PIT-E-08": "Binary decoded.",
    "PIT-E-21": "Hexadecimal decoded.",
    "PIT-E-22": "HTML entities decoded.",
    "PIT-E-30": "Morse code decoded.",
    "PIT-E-31": "NATO phonetic alphabet decoded.",
    "PIT-E-33": "Rail-fence cipher found by search and decoded.",
    "PIT-E-36": "Reversed text turned around.",
    "PIT-E-44": "Tap code decoded.",
    "PIT-E-46": "URL encoding decoded.",
    "PIT-E-55": "Base32, Base58 or Base85 decoded.",
    "PIT-E-56": "Character codes (U+…, &#…;, numbers) turned into letters.",
    "PIT-E-58": "Compressed data unpacked.",
    "PIT-E-62": "Text in a legacy character set (UTF-7, quoted-printable, wrong charset) decoded.",
}


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in findings:
        key = (f.code, f.excerpt, f.revealed)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def analyze(text: str, provenance: str = "external", over: dict | None = None) -> Analysis:
    """Undo what hides text. `provenance`: system | operator | principal | external | model.
    Control tokens are removed from everything that is not the system's own."""
    s = settings(over)
    raw = text
    findings: list[Finding] = []
    readable = _process(text[: s["max_chars"]], s, 0, [], findings, own=(provenance == "system"))
    readable = readable.strip()
    # Surface signals read the undone text; they observe, they do not judge.
    findings.extend(signal_mod.signals(readable))
    return Analysis(raw=raw, readable=readable, findings=_dedupe(findings), provenance=provenance)
