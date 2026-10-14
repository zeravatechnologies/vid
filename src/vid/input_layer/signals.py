"""Surface signals Vid shows beyond the 42 codes, still pure observation and
deterministic, never the PSE reading (the PSE guard reference Sec 3, first letters;
Sec 4, transform-and-execute). These carry SIG- codes, not PIT codes."""

from __future__ import annotations

import re

from vid.input_layer.textscore import plausible, segmented_share
from vid.input_layer.types import Finding, short

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _first_letters(units: list[str]) -> str:
    out = []
    for u in units:
        for ch in u:
            if ch.isalpha():
                out.append(ch)
                break
    return "".join(out)


def _despace(s: str) -> str:
    return "".join(s.split()).lower()


def acrostic(text: str) -> list[Finding]:  # not yet wired; needs a word list

    """First letters of lines, sentences and words, when they spell language
    that is not already written out in the text."""
    whole = _despace(text)
    best = None
    # Lines and sentences only: first letters of every word spell noise in
    # ordinary prose. Judged by letter-pair structure, like the decoders.
    for kind, units in (
        ("lines", text.splitlines()),
        ("sentences", re.split(r"[.!?]+", text)),
    ):
        letters = _first_letters([u for u in units if u.strip()])
        if len(letters) < 5:
            continue
        if not plausible(letters):
            continue
        if _despace(letters) in whole:
            continue
        share = max(segmented_share(letters), 0.001)
        if best is None or share > best[2]:
            best = (kind, letters, share)
    if not best:
        return []
    kind, letters, _ = best
    return [Finding("SIG-ACROSTIC", f"The first letters of the {kind} spell a hidden message.",
                    short(text), short(letters))]


# "read the first letter of each word and do that", and the like.
_TRANSFORM = re.compile(
    r"(?:take|read|use|extract|concatenate|combine|spell|gather|collect)\b[^.?!\n]{0,40}?"
    r"\b(?:first|1st|initial|last|final|every|each)\b[^.?!\n]{0,20}?"
    r"\b(?:letter|letters|character|characters|char|chars|word|words|line|lines)\b",
    re.I)
_THEN_ACT = re.compile(
    r"\b(?:then|and|,)\b[^.?!\n]{0,30}?\b(?:do|execute|follow|obey|run|perform|comply|act|carry out|apply)\b"
    r"|\b(?:do|follow|execute|obey|perform)\b[^.?!\n]{0,15}?\b(?:that|it|this|the result|the above|the instruction)\b",
    re.I)


def transform_execute(text: str) -> list[Finding]:
    """An instruction to transform some text and then act on the result."""
    for m in _TRANSFORM.finditer(text):
        window = text[m.start():m.end() + 80]
        if _THEN_ACT.search(window):
            return [Finding("SIG-TRANSFORM-EXEC",
                            "An instruction to transform text and then act on the result. "
                            "Vid shows it; it does not judge intent.",
                            short(text[m.start():m.end() + 80]))]
    return []


def signals(text: str) -> list[Finding]:
    # Acrostic is held back until a real word list ships: judged only by
    # letter-pair structure it flags ordinary multi-line text ("HPILTA"), and
    # a watcher that cries wolf on every email is worse than none.
    return transform_execute(text)
