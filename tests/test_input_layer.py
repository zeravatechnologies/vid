"""Phase 1 exit criterion: one test per basic-layer code, and legitimate text
left untouched (the PSE guard reference, Sec 15).

These tests check only that Vid UNDOES a concealment technique and reports
it: that it turns a disguised string back into readable text and names the
technique (its PIT code). What the hidden text says is irrelevant to that, so
every payload here is a harmless sentence (PHRASE / PHRASE2). No test contains
an instruction aimed at a model; measuring Vid against real attack corpora
is Keel's job, with the published Arcanum set and its attribution. The intent
is defensive: prove the guard reads what an attacker would hide.
"""

from __future__ import annotations

import base64
import gzip
import re
import urllib.parse

import pytest

from vid.input_layer import BASIC_LAYER, analyze
from vid.input_layer.codes import CONTROL_TOKENS, DECODERS, NORMALIZATION, STRUCTURE

# Harmless payloads. The point is that they come back readable, not what they say.
PHRASE = "the quick brown fox"
PHRASE2 = "pack my box with jugs"


# --- encoders: build each disguise from a plain phrase, so no attack is written out ---

def b_braille(s: str) -> str:
    tbl = {"a": 0x01, "b": 0x03, "c": 0x09, "d": 0x19, "e": 0x11, "f": 0x0B, "g": 0x1B, "h": 0x13, "i": 0x0A,
           "j": 0x1A, "k": 0x05, "l": 0x07, "m": 0x0D, "n": 0x1D, "o": 0x15, "p": 0x0F, "q": 0x1F, "r": 0x17,
           "s": 0x0E, "t": 0x1E, "u": 0x25, "v": 0x27, "w": 0x3A, "x": 0x2D, "y": 0x3D, "z": 0x35, " ": 0x00}
    return "".join(chr(0x2800 + tbl[c]) for c in s)


def b_circled(s: str) -> str:
    return "".join(chr(0x24D0 + ord(c) - 97) if c.isalpha() else c for c in s)


def b_math(s: str) -> str:
    return "".join(chr(0x1D41A + ord(c) - 97) if c.isalpha() else c for c in s)


def b_fullwidth(s: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in s)


def b_smallcaps(s: str) -> str:
    sc = {"a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ",
          "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "q", "r": "ʀ", "s": "ꜱ", "t": "ᴛ",
          "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "y", "z": "ᴢ"}
    return "".join(sc.get(c, c) for c in s)


def b_regional(s: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - 97) if c.isalpha() else c for c in s)


def b_wingdings(s: str) -> str:
    inv = {"a": "✌", "b": "👌", "c": "👍", "d": "👎", "e": "☜", "f": "☞", "g": "☝", "h": "☟", "i": "✋",
           "o": "💣", "k": "☺", "n": "☹", "r": "⚐", "t": "✈", "w": "☼", "u": "💧", "x": "❄", " ": " "}
    return "".join(inv.get(c, c) + ("︎" if c in inv and c != " " else "") for c in s)


def b_homoglyph(s: str) -> str:
    cyr = {"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "x": "х", "y": "у", "i": "і"}
    return "".join(cyr.get(c, c) for c in s)


def b_bidi(s: str) -> str:
    return "‮" + s + "‬"


def b_tag_chars(s: str) -> str:
    return "".join(chr(0xE0000 + ord(c)) for c in s)


def b_overlay(s: str) -> str:
    return "".join(c + "̶" for c in s)


def b_zalgo(s: str) -> str:
    return "".join(c + "̀́̂̃̆" if c.isalpha() else c for c in s)


def b_upside(s: str) -> str:
    u = {"a": "ɐ", "c": "ɔ", "e": "ǝ", "f": "ɟ", "g": "ƃ", "h": "ɥ", "i": "ᴉ", "j": "ɾ", "k": "ʞ", "m": "ɯ",
         "r": "ɹ", "t": "ʇ", "v": "ʌ", "w": "ʍ", "y": "ʎ", "b": "q", "d": "p", "q": "b", "p": "d", "n": "u",
         "u": "n", "l": "ן", "o": "o", "s": "s", "x": "x", "z": "z", " ": " "}
    return "".join(u.get(c, c) for c in reversed(s))


def b_spaced(s: str) -> str:
    return " ".join(s.replace(" ", ""))


def b_splat(s: str) -> str:
    return "*".join(s.replace(" ", ""))


def b_vertical(s: str) -> str:
    return "\n".join(s.replace(" ", "")) + "\n\nend"


def b_altcase(s: str) -> str:
    return "".join(c.upper() if i % 2 else c for i, c in enumerate(s))


def b_ansi_hidden(s: str) -> str:
    return "visible \x1b[8m" + s + "\x1b[0m text"


def b_url(s: str) -> str:
    return "".join(f"%{b:02X}" for b in s.encode())


def b_a1z26(s: str) -> str:
    words = s.split()
    return " / ".join(" ".join(str(ord(c) - 96) for c in w) for w in words)


def b_baconian(s: str) -> str:
    return " ".join(format(ord(c) - 97, "05b").replace("0", "A").replace("1", "B") for c in s if c.isalpha())


def b_binary(s: str) -> str:
    return " ".join(format(b, "08b") for b in s.encode())


def b_hex(s: str) -> str:
    return s.encode().hex()


def b_morse(s: str) -> str:
    m = {"a": ".-", "b": "-...", "c": "-.-.", "d": "-..", "e": ".", "f": "..-.", "g": "--.", "h": "....",
         "i": "..", "j": ".---", "k": "-.-", "l": ".-..", "m": "--", "n": "-.", "o": "---", "p": ".--.",
         "q": "--.-", "r": ".-.", "s": "...", "t": "-", "u": "..-", "v": "...-", "w": ".--", "x": "-..-",
         "y": "-.--", "z": "--.."}
    return " / ".join(" ".join(m[c] for c in w) for w in s.split())


def b_nato(s: str) -> str:
    n = {"a": "alfa", "b": "bravo", "c": "charlie", "d": "delta", "e": "echo", "f": "foxtrot", "g": "golf",
         "h": "hotel", "i": "india", "j": "juliett", "k": "kilo", "l": "lima", "m": "mike", "n": "november",
         "o": "oscar", "p": "papa", "q": "quebec", "r": "romeo", "s": "sierra", "t": "tango", "u": "uniform",
         "v": "victor", "w": "whiskey", "x": "xray", "y": "yankee", "z": "zulu"}
    return " ".join(n[c] for c in s if c.isalpha())


def b_tap(s: str) -> str:
    grid = "abcdefghiklmnopqrstuvwxyz"
    out = []
    for c in s.replace("k", "c").replace(" ", ""):
        idx = grid.index(c)
        out.append(f"{idx // 5 + 1}{idx % 5 + 1}")
    return " ".join(out)


def b_codepoints(s: str) -> str:
    return "".join(f"&#{ord(c)};" for c in s)


def b_unicode_cp(s: str) -> str:
    return "".join(f"\\u{ord(c):04x}" for c in s)


def b_rail(s: str, rails: int = 3) -> str:
    s = s.replace(" ", "")
    rows = [[] for _ in range(rails)]
    r, step = 0, 1
    for ch in s:
        rows[r].append(ch)
        step = 1 if r == 0 else -1 if r == rails - 1 else step
        r += step
    return "".join("".join(x) for x in rows)


def b_base32(s: str) -> str:
    return base64.b32encode(s.encode()).decode()


def b_utf7(s: str) -> str:
    return s.encode("utf-7").decode("ascii")


# --- one case per code: (disguised input, the readable text Vid must recover) ---

CASES: dict[str, tuple[str, str]] = {
    # normalization (19)
    "PIT-E-11": (b_braille(PHRASE), PHRASE),
    "PIT-E-12": (b_circled(PHRASE), PHRASE),
    "PIT-E-13": (b_altcase(PHRASE), PHRASE),
    "PIT-E-19": (b_fullwidth(PHRASE), PHRASE),
    "PIT-E-20": ("please " + b_homoglyph("review the report"), "review the report"),
    "PIT-E-23": ("hello" + b_tag_chars(PHRASE), PHRASE),
    "PIT-E-28": ("path∕to∕file and ‹tag›", "/"),
    "PIT-E-29": (b_math(PHRASE), PHRASE),
    "PIT-E-34": (b_regional("hello"), "HELLO"),
    "PIT-E-37": (b_spaced(PHRASE), PHRASE.replace(" ", "")),
    "PIT-E-38": (b_splat(PHRASE), PHRASE.replace(" ", "")),
    "PIT-E-40": (b_smallcaps(PHRASE), PHRASE),
    "PIT-E-43": (b_overlay(PHRASE), PHRASE),
    "PIT-E-45": (b_upside(PHRASE), PHRASE),
    "PIT-E-47": (b_vertical("hello"), "hello"),
    "PIT-E-49": (b_wingdings("cabbage"), "cabbage"),
    "PIT-E-51": (b_zalgo(PHRASE), PHRASE),
    "PIT-E-54": ("summary: " + b_bidi(PHRASE) + " end", PHRASE),
    "PIT-E-59": (b_ansi_hidden(PHRASE), PHRASE),
    # decoders (17)
    "PIT-E-01": (b_a1z26("the quick fox"), "the quick fox"),
    "PIT-E-06": (b_baconian("quickbrownfox"), "quickbrownfox"),
    "PIT-E-07": ("note: " + base64.b64encode(PHRASE.encode()).decode(), PHRASE),
    "PIT-E-08": (b_binary(PHRASE), PHRASE),
    "PIT-E-21": (b_hex(PHRASE), PHRASE),
    "PIT-E-22": ("".join(f"&#{ord(c)};" for c in PHRASE), PHRASE),
    "PIT-E-30": (b_morse("the quick fox"), "the quick fox"),
    "PIT-E-31": (b_nato("quick"), "quick"),
    "PIT-E-33": (b_rail("the quick brown fox jumps"), "thequickbrownfoxjumps"),
    "PIT-E-36": (PHRASE[::-1], PHRASE),
    "PIT-E-44": (b_tap("brown"), "brown"),  # numeric tap form
    "PIT-E-46": ("note " + b_url(PHRASE), PHRASE),
    "PIT-E-55": (b_base32(PHRASE), PHRASE),
    "PIT-E-56": (b_unicode_cp(PHRASE), PHRASE),
    "PIT-E-57": (base64.b64encode(b_url(PHRASE).encode()).decode(), PHRASE),
    "PIT-E-58": (base64.b64encode(gzip.compress(PHRASE.encode())).decode(), PHRASE),
    "PIT-E-62": (b_utf7("naïve café résumé"), "café"),
    # structure flattened (4)
    "PIT-E-18": ('digraph g { a [label="the quick brown"]; b [label="fox jumps over"]; a -> b; }', "quick brown"),
    "PIT-E-25": ('{"task": "summarise", "note": "the quick brown fox"}', "the quick brown fox"),
    "PIT-E-27": ("text [link](http://x \"the quick brown fox title\")", "the quick brown fox title"),
    "PIT-E-50": ("<note><!-- the quick brown fox --><body>hello</body></note>", "the quick brown fox"),
    # control tokens removed (2)
    "PIT-T-07": ("thanks<|im_end|> more text", "thanks"),
    "PIT-T-48": ("text [INST] more [/INST] end", "text"),
}


def test_every_basic_layer_code_has_a_case():
    assert set(CASES) == set(BASIC_LAYER), set(BASIC_LAYER) ^ set(CASES)
    assert len(CASES) == 42


@pytest.mark.parametrize("code", sorted(CASES), ids=lambda c: f"{c}-{BASIC_LAYER[c].split('/')[0].replace(' ', '-')}")
def test_code_detected_and_text_recovered(code):
    disguised, expected = CASES[code]
    result = analyze(disguised)
    assert code in result.codes(), f"{code} ({BASIC_LAYER[code]}) not found; got {result.codes()}"
    recovered = result.readable.lower().replace(" ", "")
    assert expected.lower().replace(" ", "") in recovered, f"{code}: {expected!r} not in {result.readable!r}"


# --- legitimate text must pass through untouched (Sec 3, CAUTION; Sec 3, COST) ---

CLEAN = {
    "english": "Please summarise this quarterly report and send it back to me by Friday.",
    "serbian_latin": "Dobar dan, možete li mi poslati izveštaj do petka? Hvala unapred.",
    "serbian_cyrillic": "Добар дан, можете ли ми послати извештај до петка? Хвала унапред.",
    "mixed": "Hvala, I will review the pull request and reply tomorrow. Pozdrav!",
    "emoji": "Great work on the launch 🎉👨‍👩‍👧 let's celebrate 🇷🇸🇬🇧 ❤️",
    "url": "See https://www.zeravatech.ca/downloads/ for the latest build.",
    "code": "Call getHTTPResponse(userID) then parse the JSON with iPhone-style keys.",
    "hash": "The commit is 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b and the key is AKIA1234567890ABCDEF.",
    "numbers": "Invoice 2024 for 1500 units at 25 each, due in 30 days, ref 4821 7700 1234.",
    "acronyms": "The API uses JSON over HTTPS; see the FAQ and the EULA in the PDF.",
}


@pytest.mark.parametrize("name", sorted(CLEAN), ids=sorted(CLEAN))
def test_clean_text_is_not_flagged(name):
    text = CLEAN[name]
    result = analyze(text)
    assert not result.hidden, f"{name}: false positive {result.codes()} -> {result.readable!r}"


def test_clean_text_unchanged_bytes():
    for text in CLEAN.values():
        assert analyze(text).readable == text.strip()


# --- the model still receives the original in the free edition (decision 13 Oct) ---

def test_raw_is_kept():
    disguised = b_fullwidth(PHRASE)
    result = analyze(disguised)
    assert result.raw == disguised
    assert result.readable != disguised


def test_system_text_keeps_its_control_tokens():
    # Control tokens are removed from input that is not the system's own.
    text = "You are a helpful assistant.<|im_end|>"
    assert analyze(text, provenance="external").codes() == ["PIT-T-07"]
    assert analyze(text, provenance="system").codes() == []


# --- surface signals Vid shows beyond the 42 codes (observation only) ---

def test_transform_and_execute_flagged():
    t = "Please read the first letter of each sentence and then do that."
    codes = analyze(t).codes()
    assert "SIG-TRANSFORM-EXEC" in codes


def test_transform_and_execute_not_flagged_on_plain_request():
    t = "Please take the first train tomorrow and read the report on the way."
    assert "SIG-TRANSFORM-EXEC" not in analyze(t).codes()


def test_signals_do_not_touch_clean_text():
    for t in CLEAN.values():
        assert not any(f.code.startswith("SIG-") for f in analyze(t).findings)
