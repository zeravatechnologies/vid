"""Unicode normalization: the 19 normalization codes of the basic layer
(the PSE guard reference Sec 3, Sec 15).

Every step takes text and returns (text, findings). Legitimate text in other
scripts is left alone: Cyrillic is a script, not a homoglyph attack, and
mixed-language text is legitimate (Sec 3, CAUTION). Emoji sequences keep
their joiners and presentation selectors.
"""

from __future__ import annotations

import re
import unicodedata

from vid.input_layer.textscore import WORDS, plausible, printable_text
from vid.input_layer.types import Finding, short

# ---------------------------------------------------------------------------
# E-59 ANSI escape concealment
# ---------------------------------------------------------------------------
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
_CONCEAL = re.compile(r"\x1b\[(?:[0-9;]*;)?8(?:;[0-9;]*)?m(.*?)(?=\x1b\[|$)", re.S)


def ansi(text: str, s: dict) -> tuple[str, list[Finding]]:
    if "\x1b" not in text:
        return text, []
    concealed = [m.group(1) for m in _CONCEAL.finditer(text) if m.group(1).strip()]
    n = len(_ANSI.findall(text))
    out = _ANSI.sub("", text)
    detail = f"{n} terminal escape sequence(s) removed"
    if concealed:
        detail += "; text set to be invisible in a terminal is shown"
    return out, [Finding("PIT-E-59", detail + ".", short(text), short(" ".join(concealed) or out), count=n)]


# ---------------------------------------------------------------------------
# E-54 bidirectional override
# ---------------------------------------------------------------------------
_BIDI = dict.fromkeys(map(ord, "‪‫‬‭‮⁦⁧⁨⁩‎‏؜"))


def bidi(text: str, s: dict) -> tuple[str, list[Finding]]:
    n = sum(1 for ch in text if ord(ch) in _BIDI)
    if not n:
        return text, []
    out = text.translate(_BIDI)
    return out, [Finding("PIT-E-54", f"{n} text-direction control(s) removed; the text is shown in the order the model reads it.",
                         short(text), short(out), count=n)]


# ---------------------------------------------------------------------------
# E-23 invisible text
# ---------------------------------------------------------------------------
_ZERO_WIDTH = set("​‌‍⁠﻿᠎⁡⁢⁣⁤­͏ᅟᅠㅤﾠ឴឵")
_TAG = range(0xE0000, 0xE0080)
_VS = set(range(0xFE00, 0xFE10)) | set(range(0xE0100, 0xE01F0))


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return 0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or cp in (0x2764, 0x2B50, 0x2B55)


def _vs_value(cp: int) -> int:
    return cp - 0xFE00 if cp < 0xFE10 else cp - 0xE0100 + 16


def invisible(text: str, s: dict) -> tuple[str, list[Finding]]:
    out: list[str] = []
    revealed: list[str] = []
    removed = 0
    i, n = 0, len(text)
    while i < n:
        ch, cp = text[i], ord(text[i])
        # Tag characters spell ASCII invisibly ("ASCII smuggling").
        if cp in _TAG:
            j = i
            while j < n and ord(text[j]) in _TAG:
                j += 1
            hidden = "".join(chr(ord(c) - 0xE0000) for c in text[i:j] if 0xE0020 <= ord(c) <= 0xE007E)
            if hidden:
                revealed.append(hidden)
            removed += j - i
            i = j
            continue
        # Runs of variation selectors after one character carry bytes.
        if cp in _VS:
            j = i
            while j < n and ord(text[j]) in _VS:
                j += 1
            run = text[i:j]
            prev = text[i - 1] if i else ""
            legit = len(run) == 1 and (cp in (0xFE0E, 0xFE0F) or (prev and unicodedata.category(prev).startswith("L")))
            if legit:
                out.append(ch)
            else:
                decoded = printable_text(bytes(_vs_value(ord(c)) for c in run))
                if decoded:
                    revealed.append(decoded)
                removed += len(run)
            i = j
            continue
        if ch in _ZERO_WIDTH:
            # Zero-width joiner inside an emoji sequence is legitimate.
            if ch == "‍" and i and i + 1 < n and _is_emoji(text[i - 1]) and _is_emoji(text[i + 1]):
                out.append(ch)
                i += 1
                continue
            j = i
            while j < n and text[j] in _ZERO_WIDTH:
                j += 1
            run = text[i:j]
            bits = "".join("0" if c == "​" else "1" if c == "‌" else "" for c in run)
            if len(bits) >= 8 and len(bits) % 8 == 0:
                decoded = printable_text(int(bits, 2).to_bytes(len(bits) // 8, "big"))
                if decoded:
                    revealed.append(decoded)
            removed += len(run)
            i = j
            continue
        out.append(ch)
        i += 1
    if not removed:
        return text, []
    result = "".join(out)
    detail = f"{removed} invisible character(s) removed"
    if revealed:
        detail += "; they carried hidden text"
        result = result + "\n" + "\n".join(revealed)
    return result, [Finding("PIT-E-23", detail + ".", short(text), short(" ".join(revealed) or result), count=removed)]


# ---------------------------------------------------------------------------
# E-43 strikethrough/underline/overlay, E-51 zalgo
# ---------------------------------------------------------------------------
_OVERLAY = set("̴̵̶̷̸⃒⃓⃥⃦̲̳̱̠̅̿")


def overlay(text: str, s: dict) -> tuple[str, list[Finding]]:
    n = sum(1 for ch in text if ch in _OVERLAY)
    if n < s["overlay_min"]:
        return text, []
    out = "".join(ch for ch in text if ch not in _OVERLAY)
    return out, [Finding("PIT-E-43", f"{n} line-drawing mark(s) (strikethrough, underline, overlay) removed.", short(text), short(out), count=n)]


def zalgo(text: str, s: dict) -> tuple[str, list[Finding]]:
    # No NFC first: that would fuse the first mark into the base letter (e+◌̀ -> è)
    # and hide it. Count raw combining marks and drop the whole stack.
    out: list[str] = []
    stripped = 0
    marks = 0
    for ch in text:
        if unicodedata.category(ch) == "Mn":
            marks += 1
            out.append(ch)
            continue
        if marks >= s["zalgo_marks"]:
            # drop the whole stack of marks on the previous character
            del out[len(out) - marks:]
            stripped += marks
        marks = 0
        out.append(ch)
    if marks >= s["zalgo_marks"]:
        del out[len(out) - marks:]
        stripped += marks
    if not stripped:
        return text, []
    res = "".join(out)
    return res, [Finding("PIT-E-51", f"{stripped} stacked combining mark(s) (\"zalgo\") removed.", short(text), short(res), count=stripped)]


# ---------------------------------------------------------------------------
# Character folds: E-19, E-29, E-12, E-40, E-11, E-34, E-49, E-28, E-20
# ---------------------------------------------------------------------------
_BRAILLE = {0x01: "a", 0x03: "b", 0x09: "c", 0x19: "d", 0x11: "e", 0x0B: "f", 0x1B: "g", 0x13: "h", 0x0A: "i",
            0x1A: "j", 0x05: "k", 0x07: "l", 0x0D: "m", 0x1D: "n", 0x15: "o", 0x0F: "p", 0x1F: "q", 0x17: "r",
            0x0E: "s", 0x1E: "t", 0x25: "u", 0x27: "v", 0x3A: "w", 0x2D: "x", 0x3D: "y", 0x35: "z", 0x00: " "}
_BRAILLE_DIGITS = dict(zip("abcdefghij", "1234567890"))

_WINGDINGS = dict(zip(
    ["♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓", "🙰", "🙵", "●", "❍", "■", "□", "◻", "❑", "❒", "⬧", "◆", "❖", "⬥", "⧫", "⌧", "⍓", "⌘",
     "✌", "👌", "👍", "👎", "☜", "☞", "☝", "☟", "✋", "☺", "😐", "☹", "💣", "☠", "⚐", "🏱", "✈", "☼", "💧", "❄", "🕆", "✞", "🕈", "✠", "✡", "☪"],
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"))

_METACHAR = {"∶": ":", "꞉": ":", "ː": ":", "︰": ":", "﹕": ":", "ǀ": "|", "∣": "|",
             "‹": "<", "›": ">", "〈": "<", "〉": ">", "〈": "<", "〉": ">", "⟨": "<",
             "⟩": ">", "﹤": "<", "﹥": ">", "ᐸ": "<", "ᐳ": ">", "˂": "<", "˃": ">",
             "⁄": "/", "∕": "/", "⧸": "/", "⧵": "\\", "∖": "\\", "ʼ": "'", "։": ":",
             "׃": ":", "܃": ":", "❰": "<", "❱": ">", "❮": "<", "❯": ">", "﹝": "[",
             "﹞": "]", "❴": "{", "❵": "}", "⦃": "{", "⦄": "}", "〔": "[", "〕": "]"}

# Letters of other scripts that look like Latin letters (Unicode confusables,
# the ones seen in attacks). Used only inside Latin words or Latin text.
_HOMOGLYPH = {
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "ё": "e", "і": "i", "ї": "i", "ј": "j", "к": "k", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "ѕ": "s", "ԁ": "d", "ԛ": "q", "ԝ": "w", "һ": "h", "ӏ": "l", "ɡ": "g",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "Ү": "Y", "І": "I", "Ј": "J", "Ѕ": "S", "Ԁ": "D", "Ԛ": "Q", "Ԝ": "W",
    # Greek
    "α": "a", "ο": "o", "ν": "v", "ρ": "p", "ι": "i", "κ": "k", "υ": "u", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z",
    "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    # Others commonly used
    "ı": "i", "ȷ": "j", "ℓ": "l", "ᴦ": "r", "ꓲ": "I", "ꓳ": "O", "ꓑ": "P", "ꓢ": "S", "ꓔ": "T", "ꓮ": "A", "ꓐ": "B",
    "ꓚ": "C", "ꓓ": "D", "ꓰ": "E", "ꓝ": "F", "ꓖ": "G", "ꓧ": "H", "ꓗ": "K", "ꓡ": "L", "ꓟ": "M", "ꓠ": "N", "ꓣ": "R",
    "ꓴ": "U", "ꓦ": "V", "ꓪ": "W", "ꓫ": "X", "ꓬ": "Y", "ꓜ": "Z",
}


def _styled_latin(ch: str) -> str | None:
    """Base letter of a styled Latin letter (math, enclosed, small caps, ...)."""
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    m = re.search(r"SMALL CAPITAL ([A-Z])$", name)
    if m:
        return m.group(1).lower()
    m = re.search(r"\b(?:LATIN )?(CAPITAL|SMALL)(?: LETTER)? ([A-Z])$", name)
    if m and ("LATIN" in name or "MATHEMATICAL" in name or "CIRCLED" in name or "SQUARED" in name or "PARENTHESIZED" in name):
        return m.group(2) if m.group(1) == "CAPITAL" else m.group(2).lower()
    m = re.search(r"LATIN LETTER SMALL CAPITAL ([A-Z])$", name)
    if m:
        return m.group(1).lower()
    m = re.search(r"(?:DIGIT|NUMBER) (ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE)$", name)
    if m and ("CIRCLED" in name or "MATHEMATICAL" in name or "PARENTHESIZED" in name or "FULLWIDTH" in name):
        return str("ZERO ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE".split().index(m.group(1)))
    return None


def _fold_code(ch: str) -> tuple[str, str] | None:
    """(code, replacement) for a character some fold undoes, else None."""
    cp = ord(ch)
    if 0xFF01 <= cp <= 0xFF5E:
        return "PIT-E-19", chr(cp - 0xFEE0)
    if 0x1D400 <= cp <= 0x1D7FF:
        r = unicodedata.normalize("NFKC", ch)
        return ("PIT-E-29", r) if r != ch else None
    if 0x2460 <= cp <= 0x24FF or 0x1F100 <= cp <= 0x1F1E5 or 0x3251 <= cp <= 0x32BF:
        r = _styled_latin(ch) or unicodedata.normalize("NFKC", ch)
        return ("PIT-E-12", r.strip("()")) if r != ch else None
    if (0x1D00 <= cp <= 0x1DBF or 0x2070 <= cp <= 0x209F or 0xA730 <= cp <= 0xA7AF
            or cp in (0xB2, 0xB3, 0xB9, 0x2071, 0x207F, 0x0274, 0x0280, 0x0262, 0x029C, 0x026A, 0x029F, 0x1D04, 0x0299, 0x1D20, 0x1D21, 0x1D22)):
        try:
            nm = unicodedata.name(ch)
        except ValueError:
            nm = ""
        if any(w in nm for w in ("SMALL CAPITAL", "SUBSCRIPT", "SUPERSCRIPT", "MODIFIER LETTER SMALL")):
            r = _styled_latin(ch) or unicodedata.normalize("NFKC", ch)
            return ("PIT-E-40", r) if r != ch and r.isascii() and r.isalnum() else None
        return None
    if 0x2800 <= cp <= 0x28FF:
        return "PIT-E-11", _BRAILLE.get(cp - 0x2800, "?")
    if 0x1F1E6 <= cp <= 0x1F1FF:
        return "PIT-E-34", chr(ord("A") + cp - 0x1F1E6)
    if ch in _WINGDINGS:
        return "PIT-E-49", _WINGDINGS[ch]
    if ch in _METACHAR:
        return "PIT-E-28", _METACHAR[ch]
    return None


_DESCRIPTIONS = {
    "PIT-E-19": "full-width character(s) folded to ordinary letters",
    "PIT-E-29": "mathematical-style letter(s) folded to ordinary letters",
    "PIT-E-12": "enclosed or bubble letter(s) folded to ordinary letters",
    "PIT-E-40": "small-caps, superscript or subscript letter(s) folded",
    "PIT-E-11": "Braille character(s) read as letters",
    "PIT-E-34": "regional-indicator symbol(s) read as letters",
    "PIT-E-49": "symbol-font character(s) (Wingdings) read as letters",
    "PIT-E-28": "look-alike delimiter(s) (colons, brackets, bars, slashes) folded",
}


def folds(text: str, s: dict) -> tuple[str, list[Finding]]:
    counts: dict[str, int] = {}
    out: list[str] = []
    i = 0
    chars = list(text)
    # Braille digits follow the number sign (⠼).
    while i < len(chars):
        ch = chars[i]
        if ch == "⠼":
            j = i + 1
            digits = []
            while j < len(chars) and 0x2800 <= ord(chars[j]) <= 0x28FF and _BRAILLE.get(ord(chars[j]) - 0x2800) in _BRAILLE_DIGITS:
                digits.append(_BRAILLE_DIGITS[_BRAILLE[ord(chars[j]) - 0x2800]])
                j += 1
            if digits:
                out.append("".join(digits))
                counts["PIT-E-11"] = counts.get("PIT-E-11", 0) + j - i
                i = j
                continue
        if ch in ("︎", "️") and out and out[-1] in _WINGDINGS.values():
            i += 1
            continue
        f = _fold_code(ch)
        if f:
            counts[f[0]] = counts.get(f[0], 0) + 1
            out.append(f[1])
        else:
            out.append(ch)
        i += 1
    if not counts:
        return text, []
    res = "".join(out)
    findings = []
    for code, n in counts.items():
        # Flags (pairs of regional indicators) and the odd symbol are ordinary:
        # report a run only when it actually spells something.
        if code in ("PIT-E-34", "PIT-E-49") and not _spells_text(text, res, code):
            continue
        findings.append(Finding(code, f"{n} {_DESCRIPTIONS[code]}.", short(text), short(res), count=n))
    if not findings:
        return text, []
    reported = {f.code for f in findings}
    if reported != set(counts):
        # Undo only what was reported; leave ordinary flags and symbols alone.
        res = "".join(_fold_code(ch)[1] if (_fold_code(ch) and _fold_code(ch)[0] in reported) else ch
                      for ch in text if not (ch in ("︎", "️") and "PIT-E-49" in reported))
    return res, findings


def _spells_text(original: str, folded: str, code: str) -> bool:
    if code == "PIT-E-34":
        runs = re.findall(r"[\U0001F1E6-\U0001F1FF]{4,}", original)
        return any(plausible("".join(chr(ord("a") + ord(c) - 0x1F1E6) for c in r), min_known=0.6) for r in runs)
    runs = re.findall("(?:[" + "".join(re.escape(k) for k in _WINGDINGS) + r"][︎️]?\s?){4,}", original)
    return any(plausible("".join(_WINGDINGS.get(c, " " if c == " " else "") for c in r)) for r in runs)


_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _script(ch: str) -> str:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return "?"
    return name.split(" ", 1)[0]


def homoglyphs(text: str, s: dict) -> tuple[str, list[Finding]]:
    letters = [ch for ch in text if ch.isalpha()]
    latin_share = sum(_script(ch) == "LATIN" for ch in letters) / len(letters) if letters else 0
    changed = 0
    examples = []

    def fix(m: re.Match) -> str:
        nonlocal changed
        w = m.group(0)
        scripts = {_script(ch) for ch in w}
        mixed = "LATIN" in scripts and len(scripts) > 1
        # A whole word of look-alikes inside otherwise Latin text.
        disguised = latin_share >= s["homoglyph_latin_share"] and "LATIN" not in scripts and all(ch in _HOMOGLYPH for ch in w) and len(w) >= 2
        if not (mixed or disguised):
            return w
        new = "".join(_HOMOGLYPH.get(ch, ch) if _script(ch) != "LATIN" else ch for ch in w)
        if new != w:
            changed += sum(a != b for a, b in zip(w, new))
            if len(examples) < 3:
                examples.append(f"{w}→{new}")
        return new

    res = _WORD.sub(fix, text)
    if not changed:
        return text, []
    return res, [Finding("PIT-E-20", f"{changed} look-alike letter(s) from another script replaced inside Latin words ({', '.join(examples)}).",
                         short(text), short(res), count=changed)]


# ---------------------------------------------------------------------------
# E-45 upside down
# ---------------------------------------------------------------------------
_UPSIDE = {"ɐ": "a", "q": "b", "ɔ": "c", "p": "d", "ǝ": "e", "ɟ": "f", "ƃ": "g", "ɥ": "h", "ᴉ": "i", "ı": "i", "ɾ": "j",
           "ʞ": "k", "ן": "l", "l": "l", "ɯ": "m", "u": "n", "o": "o", "d": "p", "b": "q", "ɹ": "r", "s": "s", "ʇ": "t",
           "n": "u", "ʌ": "v", "ʍ": "w", "x": "x", "ʎ": "y", "z": "z", "∀": "A", "ꓭ": "B", "Ɔ": "C", "ꓷ": "D", "Ǝ": "E",
           "Ⅎ": "F", "⅁": "G", "H": "H", "I": "I", "ſ": "J", "ꓘ": "K", "˥": "L", "W": "M", "N": "N", "O": "O", "Ԁ": "P",
           "Ꝺ": "Q", "ꓤ": "R", "S": "S", "⊥": "T", "∩": "U", "Λ": "V", "M": "W", "X": "X", "⅄": "Y", "Z": "Z",
           "¡": "!", "¿": "?", "˙": ".", "'": ",", ",": "'", " ": " "}
_UPSIDE_MARK = set("ɐɔǝɟƃɥᴉɾʞɯɹʇʌʍʎ∀ꓭƆꓷƎℲ⅁ſꓘ˥ԀꝹꓤ⊥∩Λ⅄¡¿˙ן")


def upside_down(text: str, s: dict) -> tuple[str, list[Finding]]:
    if sum(ch in _UPSIDE_MARK for ch in text) < s["upside_down_min"]:
        return text, []
    found = []

    def flip(m: re.Match) -> str:
        run = m.group(0)
        if sum(ch in _UPSIDE_MARK for ch in run) < s["upside_down_min"]:
            return run
        new = "".join(_UPSIDE.get(ch, ch) for ch in reversed(run))
        found.append((run, new))
        return new

    res = re.sub("[" + re.escape("".join(_UPSIDE)) + r"\s]{4,}", flip, text)
    if not found:
        return text, []
    return res, [Finding("PIT-E-45", "Upside-down text turned the right way up.", short(found[0][0]), short(found[0][1]), count=len(found))]


# ---------------------------------------------------------------------------
# E-37 spaces/whitespace, E-38 splats, E-47 vertical, E-13 case
# ---------------------------------------------------------------------------
_EXOTIC_SPACE = re.compile("[ -  　   \u0085]")


def whitespace(text: str, s: dict) -> tuple[str, list[Finding]]:
    findings = []
    n_exotic = len(_EXOTIC_SPACE.findall(text))
    res = _EXOTIC_SPACE.sub(" ", text).replace(" ", " ").replace(" ", " ")
    spaced = []

    def join(m: re.Match) -> str:
        joined = m.group(0).replace(" ", "").replace("\t", "")
        if plausible(joined):
            spaced.append((m.group(0), joined))
            return joined
        return m.group(0)

    res = re.sub(r"(?<!\S)(?:[^\W_][ \t]{1,2}){%d,}[^\W_](?!\S)" % (s["spaced_letters_min"] - 1), join, res)
    if spaced:
        findings.append(Finding("PIT-E-37", "Letters spread out with spaces were joined back into words.", short(spaced[0][0]), short(spaced[0][1]), count=len(spaced)))
    elif n_exotic >= s["exotic_space_min"]:
        findings.append(Finding("PIT-E-37", f"{n_exotic} unusual space character(s) replaced with ordinary spaces.", short(text), short(res), count=n_exotic))
    return res, findings


def splats(text: str, s: dict) -> tuple[str, list[Finding]]:
    found = []

    def join(m: re.Match) -> str:
        sep = m.group(1)
        parts = m.group(0).split(sep)
        joined = "".join(parts)
        if all(len(p) <= 2 for p in parts) and plausible(joined):
            found.append((m.group(0), joined))
            return joined
        return m.group(0)

    res = re.sub(r"\b\w{1,2}([*._\-|~+^#=/\\])(?:\w{1,2}\1){%d,}\w{1,2}\b" % (s["splat_min_parts"] - 2), join, text)
    if not found:
        return text, []
    return res, [Finding("PIT-E-38", "Words broken up with symbols between the letters were joined back.", short(found[0][0]), short(found[0][1]), count=len(found))]


def vertical(text: str, s: dict) -> tuple[str, list[Finding]]:
    found = []
    vforms = sum(1 for ch in text if 0xFE10 <= ord(ch) <= 0xFE19 or 0xFE30 <= ord(ch) <= 0xFE4F)
    res = "".join(unicodedata.normalize("NFKC", ch) if (0xFE10 <= ord(ch) <= 0xFE19 or 0xFE30 <= ord(ch) <= 0xFE4F) else ch for ch in text)

    def join(m: re.Match) -> str:
        lines = [ln.strip() for ln in m.group(0).split("\n")]
        joined = "".join(ln if ln else " " for ln in lines)
        if plausible(joined):
            found.append((m.group(0), joined))
            return joined + "\n"
        return m.group(0)

    res = re.sub(r"(?m)(?:^[ \t]*\S?[ \t]*\n){%d,}" % s["vertical_min_lines"], join, res + "\n")[:-1]
    if not found and not vforms:
        return text, []
    excerpt = found[0][0] if found else text
    return res, [Finding("PIT-E-47", "Text written one letter per line (vertical) was read across.", short(excerpt), short(found[0][1] if found else res), count=len(found) or vforms)]


def case_changes(text: str, s: dict) -> tuple[str, list[Finding]]:
    words = []

    def fix(m: re.Match) -> str:
        w = m.group(0)
        if len(w) < 3 or w.isupper() or w.islower():
            return w
        flips = sum(1 for a, b in zip(w, w[1:]) if a.isupper() != b.isupper())
        # Only real words: a token mixing letters with digits or + / = is an
        # encoding or an identifier, and decoders need its case intact.
        if flips / (len(w) - 1) >= s["case_flip_ratio"] and (w.lower() in WORDS or plausible(w.lower(), min_known=0.6)):
            words.append(w)
            return w.lower()
        return w

    res = re.sub(r"(?<![\w+/=])[^\W\d_]+(?![\w+/=])", fix, text)
    if len(words) < s["case_words_min"]:
        return text, []
    return res, [Finding("PIT-E-13", f"{len(words)} word(s) with alternating capital letters read in ordinary case.", short(" ".join(words)), short(res), count=len(words))]


# Order matters: escapes and controls first, then what hides inside words,
# then character folds, then layout tricks.
STEPS = (ansi, bidi, invisible, overlay, zalgo, folds, upside_down, homoglyphs, whitespace, splats, vertical, case_changes)


def normalize(text: str, s: dict) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    for step in STEPS:
        text, f = step(text, s)
        findings.extend(f)
    return text, findings
