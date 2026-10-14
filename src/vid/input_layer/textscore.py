"""Does a string read like language? Used to accept or reject a decoding, so
identifiers, hashes, keys, code and random tokens are not "decoded" into
nonsense (the PSE guard reference Sec 3, COST).

The main signal is the letter-pair structure of the text: real English and
Serbian (Latin) words are built from a small set of common letter pairs, while
hashes, keys and random strings are full of rare pairs ("xq", "zk", "vr").
This is the letter-pair idea of Sec 7, in a compact form. A short list of
common words adds confidence. Phase 2 replaces this with the full
declared-language letter tables; the interface stays.
"""

from __future__ import annotations

import re

# Common English letter pairs plus the ones Serbian (Latin) adds. A real word's
# adjacent letters are nearly all in here; a random token's are mostly not.
_COMMON_BIGRAMS = frozenset((
    "th he in er an re on at en nd ti es or te of ed is it al ar st to nt ng se ha as ou io le ve co me de hi ri "
    "ro ic ne ea ra ce li ch ll be ma si om ur ca el ta la ns di fo ho pe ec pr ne nc "
    "wa sh et na ro ol pa op ad ys ir si tr su ea ee ss oo mm tt ff pp rr nn cc dd gg "
    "pl cl bl fl gl sl sp st sc sk sm sn sw tw dr fr gr pr tr br cr wr "
    "ab ac ad ag ak am ap ar as at av aw ay "
    "eb ec ed ef eg ek el em en ep er es et ev ew ex ey "
    "ib ic id if ig ik il im in ip ir is it iv "
    "ob oc od of og ok ol om on op or os ot ov ow oy "
    "ub uc ud uf ug uk ul um un up ur us ut uv "
    "do go ho jo ko lo mo no po so wo yo "
    "ba ca da fa ga ja ka pa va wa ya za "
    "ja je ji jo ju lj nj dj "
    "ko ni po ti vi za sa mo bi da ne se te to tu ra "
).split())


_EN = ("the be to of and a in that have i it for not on with he as you do at this but his by from they we say "
       "her she or an will my one all would there their what so up out if about who get which go me when make can "
       "like time no just him know take into year good some could them see other than then now look only come its "
       "over think also after use two how first work well way even new want because any give day most us are was "
       "ignore previous instructions system prompt assistant please send show read file data key password quick "
       "brown fox jumps over lazy dog pack box jugs note text hello world review report summary title end task").split()
_SR = ("je i u da se na za ne to sa od su sam si smo ste kao ali ili ako jer kad kada sve što sta koji koja koje "
       "nije biti bio bila bilo ima imam nema mogu može treba hoću reci kaži pošalji obriši lozinka ključ sistem "
       "uputstvo zanemari prethodna pravila poruka fajl podatke dobar dan kako ste hvala molim zdravo ovo taj "
       "danas sutra možete poslati izveštaj petka unapred pozdrav").split()
WORDS = frozenset(_EN) | frozenset(_SR)

_VOWELS = set("aeiouyàáâãäåèéêëìíîïòóôõöùúûüçćčđšžабвгдђежзијклмнопрстћуфхцчџш")
_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)


def _bigram_coverage(token: str) -> float:
    """Share of adjacent letter pairs that are common in English/Serbian."""
    t = token.lower()
    pairs = [t[i:i + 2] for i in range(len(t) - 1)]
    if not pairs:
        return 1.0 if t in WORDS or (len(t) == 1 and t in _VOWELS) else 0.0
    return sum(p in _COMMON_BIGRAMS for p in pairs) / len(pairs)


def _vowel_ok(token: str) -> bool:
    """Real words of 3+ letters almost always contain a vowel and are not all vowels."""
    t = token.lower()
    if len(t) < 3:
        return True
    vowels = sum(c in _VOWELS for c in t)
    return 0 < vowels < len(t)


def score(s: str) -> float:
    """0 (noise) .. 1 (ordinary language)."""
    tokens = [t.lower() for t in _TOKEN.findall(s)]
    if not tokens:
        return 0.0
    letters = sum(len(t) for t in tokens)
    if not letters:
        return 0.0
    known = sum(len(t) for t in tokens if t in WORDS)
    cover = sum(len(t) * _bigram_coverage(t) for t in tokens) / letters
    voweled = sum(len(t) for t in tokens if _vowel_ok(t)) / letters
    printable = sum(ch.isprintable() or ch in "\n\t" for ch in s) / len(s)
    base = 0.6 * cover + 0.4 * voweled
    bonus = 0.25 * known / letters
    return round(printable * min(1.0, base + bonus), 3)


def known_share(s: str) -> float:
    tokens = [t.lower() for t in _TOKEN.findall(s)]
    letters = sum(len(t) for t in tokens)
    return sum(len(t) for t in tokens if t in WORDS) / letters if letters else 0.0


def _cover(token: str) -> int:
    """Letters of `token` covered by known words of 2+ letters, allowing the
    word boundaries to be missing (e.g. "thequickfox")."""
    if token in WORDS:
        return len(token)
    n = len(token)
    best = [0] * (n + 1)
    for i in range(1, n + 1):
        best[i] = best[i - 1]
        for j in range(max(0, i - 14), i - 1):
            w = token[j:i]
            if len(w) >= 2 and w in WORDS:
                best[i] = max(best[i], best[j] + (i - j))
    return best[n]


def segmented_share(s: str) -> float:
    """Share of letters belonging to known words, even with spaces removed."""
    tokens = [t.lower() for t in _TOKEN.findall(s)]
    letters = sum(len(t) for t in tokens)
    return sum(_cover(t) for t in tokens) / letters if letters else 0.0


def plausible(s: str, threshold: float = 0.6, min_letters: int = 4, min_known: float = 0.0) -> bool:
    """True when `s` reads like language: what a decoding must produce to count.

    `min_known` is kept for callers that want to require known words as well;
    the default relies on letter-pair structure so ordinary words outside the
    small list still pass.
    """
    if sum(ch.isalpha() for ch in s) < min_letters:
        return False
    if known_share(s) < min_known:
        return False
    return score(s) >= threshold


def printable_text(b: bytes) -> str | None:
    """bytes -> str when the bytes are readable text, else None."""
    try:
        s = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not s or sum(ch.isprintable() or ch in "\n\r\t" for ch in s) / len(s) < 0.95:
        return None
    return s
