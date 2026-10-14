"""Decoders: the 17 decoder codes of the basic layer (the PSE guard reference Sec 3,
Sec 15). Decoding is repeated until text is reached or a fixed depth is hit
(`input_layer.max_depth` in config); the repetition is E-57.

A decoding counts only when what comes out reads like language
(textscore.plausible) and reads better than what went in. That keeps
identifiers, hashes, keys and product numbers out (Sec 3, COST).
"""

from __future__ import annotations

import base64
import binascii
import bz2
import html
import re
import urllib.parse
import zlib
from typing import Callable

from vid.input_layer.textscore import known_share, plausible, printable_text, score, segmented_share

try:  # lzma is optional in some Python builds (e.g. in the browser)
    import lzma
except ImportError:  # pragma: no cover
    lzma = None

Decoded = tuple[str, str]   # (decoded text, what was decoded: the excerpt)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _bytes_to_text(b: bytes) -> str | None:
    return _decompress(b) or printable_text(b)


def _decompress(b: bytes) -> str | None:
    for magic, fn in ((b"\x1f\x8b", lambda x: zlib.decompress(x, 16 + zlib.MAX_WBITS)),
                      (b"BZh", bz2.decompress),
                      (b"\xfd7zXZ", lzma.decompress if lzma else None)):
        if fn and b.startswith(magic):
            try:
                return printable_text(fn(b))
            except Exception:
                return None
    if len(b) > 2 and b[0] == 0x78 and b[1] in (0x01, 0x5E, 0x9C, 0xDA):
        try:
            return printable_text(zlib.decompress(b))
        except zlib.error:
            return None
    return None


def _is_compressed(b: bytes) -> bool:
    return b.startswith((b"\x1f\x8b", b"BZh", b"\xfd7zXZ")) or (len(b) > 2 and b[0] == 0x78 and b[1] in (0x01, 0x5E, 0x9C, 0xDA))


def _better(decoded: str, original: str) -> bool:
    return plausible(decoded) and score(decoded) > score(original) + 0.15


# ---------------------------------------------------------------------------
# E-07 Base64, E-55 other bases, E-58 compression
# ---------------------------------------------------------------------------
_B64 = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{12,}={0,2}(?![A-Za-z0-9+/=_-])")
_B32 = re.compile(r"(?<![A-Z2-7=])[A-Z2-7]{16,}={0,6}(?![A-Z2-7=])")
_A85 = re.compile(r"<~(.+?)~>", re.S)
_B58 = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{12,}(?![1-9A-HJ-NP-Za-km-z])")
_B58_ALPHA = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base64_dec(text: str) -> list[tuple[str, str, str]]:
    """[(code, excerpt, decoded)] for Base64 (E-07) and compressed payloads (E-58)."""
    out = []
    for m in _B64.finditer(text):
        tok = m.group(0)
        try:
            raw = base64.b64decode(tok + "=" * (-len(tok) % 4), altchars=b"-_" if ("-" in tok or "_" in tok) else None, validate=True)
        except (binascii.Error, ValueError):
            continue
        if _is_compressed(raw):
            s = _decompress(raw)
            if s:
                out.append(("PIT-E-58", tok, s))
            continue
        s = printable_text(raw)
        if s and (plausible(s) or _B64.search(s) or _looks_encoded(s)):
            out.append(("PIT-E-07", tok, s))
    return out


def _looks_encoded(s: str) -> bool:
    """Decoded output that is itself another encoding (for layered payloads)."""
    s = s.strip()
    return bool(re.fullmatch(r"(?:%[0-9A-Fa-f]{2})+.*|[0-9A-Fa-f\s]{16,}|[01\s]{16,}|[.\-/ ]{8,}|&#?\w+;.*|<~.+~>", s, re.S))


def other_bases(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in _B32.finditer(text):
        tok = m.group(0)
        try:
            raw = base64.b32decode(tok + "=" * (-len(tok) % 8))
        except (binascii.Error, ValueError):
            continue
        s = _bytes_to_text(raw)
        if s and (plausible(s) or _looks_encoded(s)):
            out.append(("PIT-E-55", tok, s))
    for m in _A85.finditer(text):
        try:
            raw = base64.a85decode(m.group(0), adobe=True)
        except (ValueError, binascii.Error):
            continue
        s = _bytes_to_text(raw)
        if s:
            out.append(("PIT-E-55", m.group(0), s))
    for m in _B58.finditer(text):
        tok = m.group(0)
        n = 0
        for c in tok:
            n = n * 58 + _B58_ALPHA.index(c)
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        s = printable_text(raw)
        if s and plausible(s) and not _B64_plausible(tok):
            out.append(("PIT-E-55", tok, s))
    return out


def _B64_plausible(tok: str) -> bool:
    try:
        s = printable_text(base64.b64decode(tok + "=" * (-len(tok) % 4), validate=True))
    except (binascii.Error, ValueError):
        return False
    return bool(s and plausible(s))


# ---------------------------------------------------------------------------
# E-08 binary, E-21 hex, E-56 numeric code points, E-01 A1Z26
# ---------------------------------------------------------------------------
_BIN = re.compile(r"(?<![01])(?:[01]{7,8}[\s,]*){4,}(?![01])")
_HEX = re.compile(r"(?:(?:\\x|0x)?[0-9A-Fa-f]{2}[\s,:]*){6,}")
_CODEPOINTS = re.compile(r"(?:(?:U\+|\\u)[0-9A-Fa-f]{2,6};?[\s,]*){4,}")
_NUMBERS = re.compile(r"(?<![\d.])(?:\d{1,3}[\s,\-]+){3,}\d{1,3}(?![\d.])")


def binary(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in _BIN.finditer(text):
        groups = re.findall(r"[01]{7,8}", m.group(0))
        s = printable_text(bytes(int(g, 2) for g in groups))
        if s and (plausible(s) or _looks_encoded(s)):
            out.append(("PIT-E-08", m.group(0).strip(), s))
    return out


def hexadecimal(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in _HEX.finditer(text):
        digits = re.sub(r"\\x|0x|[\s,:]", "", m.group(0))
        if len(digits) % 2 or len(digits) < 12:
            continue
        try:
            raw = bytes.fromhex(digits)
        except ValueError:
            continue
        s = _bytes_to_text(raw)
        if s and (plausible(s) or _looks_encoded(s)):
            out.append(("PIT-E-58" if _is_compressed(raw) else "PIT-E-21", m.group(0).strip(), s))
    return out


def codepoints(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in _CODEPOINTS.finditer(text):
        tok = m.group(0)
        if not re.search(r"U\+|\\u", tok):
            continue  # &#...; belongs to HTML entities (E-22)
        vals = []
        for v in re.findall(r"(?:U\+|\\u)([0-9A-Fa-f]{2,6})", tok):
            try:
                vals.append(int(v, 16))
            except ValueError:
                pass
        try:
            s = "".join(chr(v) for v in vals)
        except (ValueError, OverflowError):
            continue
        if plausible(s):
            out.append(("PIT-E-56", tok.strip(), s))
    for m in _NUMBERS.finditer(text):
        vals = [int(v) for v in re.findall(r"\d+", m.group(0))]
        if all(32 <= v <= 126 for v in vals):
            s = "".join(map(chr, vals))
            if plausible(s):
                out.append(("PIT-E-56", m.group(0), s))
        elif all(1 <= v <= 26 for v in vals):
            continue  # A1Z26 handles these
    return out


def a1z26(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r"(?<![\d.])(?:(?:[1-9]|1\d|2[0-6])(?:[\s,\-]+|\s*/\s*)){3,}(?:[1-9]|1\d|2[0-6])(?![\d.])", text):
        words = re.split(r"\s*/\s*|\s{2,}", m.group(0).strip())
        s = " ".join("".join(chr(96 + int(v)) for v in re.findall(r"\d+", w)) for w in words)
        if plausible(s):
            out.append(("PIT-E-01", m.group(0).strip(), s))
    return out


# ---------------------------------------------------------------------------
# E-30 Morse, E-31 NATO, E-06 Baconian, E-44 tap code
# ---------------------------------------------------------------------------
_MORSE = dict(zip(".- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. --- .--. --.- .-. ... - ..- ...- .-- -..- -.-- --.. "
                  "----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----.".split(), "abcdefghijklmnopqrstuvwxyz0123456789"))
_NATO = {w: w[0] for w in "alfa alpha bravo charlie delta echo foxtrot golf hotel india juliett juliet kilo lima mike november "
         "oscar papa quebec romeo sierra tango uniform victor whiskey whisky xray x-ray yankee zulu".split()}


def morse(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r"(?:[.\-·•−–_]{1,6}(?:\s+|\s*/\s*|\|)){4,}[.\-·•−–_]{1,6}", text):
        tok = m.group(0).translate(str.maketrans("·•−–_", "..---"))
        words = re.split(r"\s*/\s*|\s{3,}|\|", tok.strip())
        s = " ".join("".join(_MORSE.get(c, "?") for c in w.split()) for w in words)
        if "?" not in s and plausible(s):
            out.append(("PIT-E-30", m.group(0).strip(), s))
    return out


def nato(text: str) -> list[tuple[str, str, str]]:
    out = []
    pat = r"\b(?:(?:" + "|".join(sorted(_NATO, key=len, reverse=True)) + r")[\s,/-]+){3,}(?:" + "|".join(sorted(_NATO, key=len, reverse=True)) + r")\b"
    for m in re.finditer(pat, text, re.I):
        groups = re.split(r"\s*/\s*|\s{2,}", m.group(0))
        s = " ".join("".join(_NATO[w.lower()] for w in re.findall(r"[A-Za-z-]+", g) if w.lower() in _NATO) for g in groups)
        if plausible(s):
            out.append(("PIT-E-31", m.group(0), s))
    return out


def _bacon_table(full: bool) -> dict[str, str]:
    letters = "abcdefghijklmnopqrstuvwxyz" if full else "abcdefghiklmnopqrstuwxyz"
    t = {format(i, "05b").replace("0", "a").replace("1", "b"): ch for i, ch in enumerate(letters)}
    return t


def baconian(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r"(?:[ABab]{5}\s*){4,}", text):
        tok = re.sub(r"\s", "", m.group(0)).lower()
        if len(tok) % 5:
            continue
        best = None
        for full in (False, True):
            table = _bacon_table(full)
            cand = "".join(table.get(tok[i:i + 5], "?") for i in range(0, len(tok), 5))
            if "?" not in cand and plausible(cand) and (best is None or segmented_share(cand) > segmented_share(best)):
                best = cand
        if best:
            out.append(("PIT-E-06", m.group(0).strip(), best))
    return out


_POLYBIUS = "abcdefghiklmnopqrstuvwxyz"   # 5x5, C stands for K


def tap_code(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r"(?:\.{1,5} \.{1,5}(?:\s{2,}|\s*/\s*|$|\s(?=\.)))(?:\.{1,5} \.{1,5}(?:\s{2,}|\s*/\s*|\s(?=\.)|$)){3,}", text):
        pairs = re.findall(r"(\.{1,5}) (\.{1,5})", m.group(0))
        s = "".join(_POLYBIUS[(len(a) - 1) * 5 + len(b) - 1] for a, b in pairs)
        if plausible(s):
            out.append(("PIT-E-44", m.group(0).strip(), s))
    for m in re.finditer(r"(?:\b[1-5][1-5]\b[\s,]*){4,}", text):
        pairs = re.findall(r"\b([1-5])([1-5])\b", m.group(0))
        s = "".join(_POLYBIUS[(int(a) - 1) * 5 + int(b) - 1] for a, b in pairs)
        if plausible(s):
            out.append(("PIT-E-44", m.group(0).strip(), s))
    return out


# ---------------------------------------------------------------------------
# E-46 URL encoding, E-22 HTML entities, E-62 legacy charsets
# ---------------------------------------------------------------------------
def url_encoding(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r"(?:[^\s%]*%[0-9A-Fa-f]{2})+[^\s%]*", text):
        tok = m.group(0)
        escapes = re.findall(r"%([0-9A-Fa-f]{2})", tok)
        # Escaping ordinary letters and digits is never needed: that is concealment.
        unneeded = sum(1 for e in escapes if chr(int(e, 16)).isalnum())
        if unneeded < 3:
            continue
        s = urllib.parse.unquote(tok)
        if s != tok and (plausible(s) or _looks_encoded(s)):
            out.append(("PIT-E-46", tok, s))
    return out


def html_entities(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r"(?:[^\s&]*&(?:#\d{2,7}|#x[0-9A-Fa-f]{2,6}|[A-Za-z]{2,10});)+[^\s&]*", text):
        tok = m.group(0)
        numeric_letters = sum(1 for v in re.findall(r"&#(x?)([0-9A-Fa-f]+);", tok)
                              if chr(int(v[1], 16 if v[0] else 10)).isalnum()) if re.search(r"&#", tok) else 0
        if numeric_letters < 3:
            continue
        s = html.unescape(tok)
        if s != tok and (plausible(s) or _looks_encoded(s)):
            out.append(("PIT-E-22", tok, s))
    return out


_MOJIBAKE = re.compile(r"[ÃÂÐÑÄÅ][\x80-\xbf\u0152-\u2122]")


def legacy_charset(text: str) -> list[tuple[str, str, str]]:
    out = []
    # UTF-7: decode the whole string at once ("+AO8-" runs are one char each).
    if re.search(r"\+[A-Za-z0-9+/]{2,}-", text) and text.isascii():
        try:
            s = text.encode("ascii").decode("utf-7")
        except UnicodeError:
            s = None
        if s and s != text and any(not ch.isascii() for ch in s) and plausible(s):
            out.append(("PIT-E-62", text, s))
    # Text decoded with the wrong charset (UTF-8 bytes read as Latin-1/CP1252)
    if _MOJIBAKE.search(text):
        for enc in ("cp1252", "latin-1"):
            try:
                s = text.encode(enc).decode("utf-8")
            except UnicodeError:
                continue
            if s != text:
                out.append(("PIT-E-62", text, s))
                break
    # Quoted-printable runs
    for m in re.finditer(r"(?:=[0-9A-F]{2}){4,}", text):
        try:
            s = printable_text(binascii.a2b_qp(m.group(0)))
        except binascii.Error:
            continue
        if s and plausible(s):
            out.append(("PIT-E-62", m.group(0), s))
    return out


# ---------------------------------------------------------------------------
# E-36 reverse, E-33 rail fence (by search)
# ---------------------------------------------------------------------------
def reverse(text: str) -> list[tuple[str, str, str]]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 8 or plausible(line):
            continue
        whole = line[::-1]
        words = " ".join(w[::-1] for w in line.split())
        for cand in (whole, words):
            if _better(cand, line):
                out.append(("PIT-E-36", line, cand))
                break
    return out


def _rail_decrypt(cipher: str, rails: int) -> str:
    n = len(cipher)
    pattern = []
    r, step = 0, 1
    for _ in range(n):
        pattern.append(r)
        if rails > 1:
            if r == 0:
                step = 1
            elif r == rails - 1:
                step = -1
            r += step
    order = sorted(range(n), key=lambda i: (pattern[i], i))
    res = [""] * n
    for ch, idx in zip(cipher, order):
        res[idx] = ch
    return "".join(res)


def rail_fence(text: str, max_rails: int = 8) -> list[tuple[str, str, str]]:
    # A transposition cipher only permutes letters, so letter-pair structure
    # cannot tell a solution from the scramble: require real words instead.
    out = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 12 or " " in line.strip() or segmented_share(line) >= 0.6:
            continue
        base = segmented_share(line)
        best = None
        for rails in range(2, min(max_rails, len(line) // 2) + 1):
            cand = _rail_decrypt(line, rails)
            share = segmented_share(cand)
            if share >= 0.7 and share > base + 0.3 and (best is None or share > best[0]):
                best = (share, cand)
        if best:
            out.append(("PIT-E-33", line, best[1]))
    return out


# The decoders, in the order they are tried at each depth.
DECODERS: tuple[Callable[[str], list[tuple[str, str, str]]], ...] = (
    base64_dec, other_bases, hexadecimal, binary, codepoints, url_encoding, html_entities,
    legacy_charset, morse, nato, baconian, tap_code, a1z26, reverse, rail_fence,
)


def decode_once(text: str) -> list[tuple[str, str, str]]:
    seen = set()
    out = []
    for fn in DECODERS:
        for code, excerpt, decoded in fn(text):
            key = (excerpt, decoded)
            if key in seen or decoded == excerpt:
                continue
            seen.add(key)
            out.append((code, excerpt, decoded))
    return out
