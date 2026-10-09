"""Persian text normalization for chat messages.

`normalize()` produces the text the agents and embeddings see; the raw text is kept for display.
- Arabic ي/ى/ك/ة -> Persian ی/ی/ک/ه, Persian/Arabic-Indic digits -> ASCII
- zero-width cleanup: one canonical ZWNJ (U+200C), no stray ZWSP/BOM/bidi marks, "می خوام" -> "می‌خوام"
- strips kashida and harakat, collapses "سلاااام" -> "سلام", collapses emoji runs ("🔥🔥🔥" -> "🔥")
`detect_lang()` tells Persian / Finglish (Persian in Latin letters) / English / mixed apart.
"""

from __future__ import annotations

import re

ZWNJ = "‌"

_CHAR_MAP = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "هٔ",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٬": ",", "٫": ".",
    "​": ZWNJ,  # zero-width space used as a half-space by some keyboards
    "¬": ZWNJ,  # "¬" typed by some Windows layouts instead of ZWNJ
    "﻿": None, "‎": None, "‏": None, "‪": None, "‫": None,
    "‬": None, "‭": None, "‮": None, "⁦": None, "⁧": None,
    "⁨": None, "⁩": None,
    "ـ": None,  # kashida
})

_HARAKAT = re.compile(r"[ً-ٰٟ]")
_FA = "؀-ۿﭐ-﷿ﹰ-﻿"
_ZWNJ_RUNS = re.compile(f"{ZWNJ}{{2,}}")
_ZWNJ_EDGES = re.compile(rf"\s*{ZWNJ}\s+|\s+{ZWNJ}\s*|^{ZWNJ}|{ZWNJ}$", re.M)
_MI_PREFIX = re.compile(rf"(^|[\s(«\"'])(ن?می)\s+(?=[{_FA}])", re.M)
_HA_SUFFIX = re.compile(rf"(?<=[{_FA}])\s+(ها|های|هایی|هایم|هایت|هایش|هامون|هاتون|هاشون)(?=[\s.,!?؟،؛:)»]|$)", re.M)
_FA_LETTER_RUNS = re.compile(rf"([{_FA}])\1{{2,}}")  # "سلاااام" -> "سلام"
_LAT_LETTER_RUNS = re.compile(r"([a-zA-Z])\1{2,}")  # "salaaaam" -> "salaam", keeps "khoob"
_WORD = re.compile(r"\S+")
_EMOJI = (
    "[\U0001f000-\U0001faff☀-➿⬀-⯿⌀-⏿←-⇿〰〽㊗㊙"
    "\U0001f1e6-\U0001f1ff]"
)
_EMOJI_SEQ = rf"(?:{_EMOJI}[️⃣\U0001f3fb-\U0001f3ff]*(?:‍{_EMOJI}[️\U0001f3fb-\U0001f3ff]*)*)"
_EMOJI_RUN = re.compile(rf"({_EMOJI_SEQ})(?:\s*{_EMOJI_SEQ})+")
_EMOJI_ANY = re.compile(_EMOJI_SEQ)
_SPACES = re.compile(r"[ \t  -   　]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def _squeeze_word(m: re.Match) -> str:
    w = m.group(0)
    if any(c in w for c in "/.@`_=") or w.lower().startswith("www"):
        return w  # URLs, handles, code: leave untouched
    return _LAT_LETTER_RUNS.sub(r"\1\1", _FA_LETTER_RUNS.sub(r"\1", w))


def normalize(text: str) -> str:
    if not text:
        return ""
    t = text.translate(_CHAR_MAP)
    t = _HARAKAT.sub("", t)
    t = _ZWNJ_RUNS.sub(ZWNJ, t)
    t = _ZWNJ_EDGES.sub(" ", t)
    t = _MI_PREFIX.sub(lambda m: f"{m[1]}{m[2]}{ZWNJ}", t)
    t = _HA_SUFFIX.sub(lambda m: f"{ZWNJ}{m[1]}", t)
    t = _WORD.sub(_squeeze_word, t)
    t = _EMOJI_RUN.sub(r"\1", t)
    t = _SPACES.sub(" ", t)
    t = _BLANK_LINES.sub("\n\n", t)
    return "\n".join(line.strip() for line in t.split("\n")).strip()


def emoji_count(text: str) -> int:
    return len(_EMOJI_ANY.findall(text or ""))


# Frequent Finglish tokens (several spellings each). Enough to separate Finglish from English.
_FINGLISH = set("""
salam slm bache bachea bacheha bachehaa kasi mikham mikhastam mikhay mikhaid mishe mitoonam mitunam mitoonid
chejoori chejori chetori chetor khoob khub khube khubi dore doreh dorei doreye yad begiram begirim bekhunam bekhoonam
sefr shoru shoroo shooroo dars kar kardam karde hast hastam hastid nist nistam dare dari daram darin darid nadaram
chi chera koja ye yek va ba az baraye vase vaseye ham hamin alan lotfan merci mersi mamnoon mamnun moteshakeram
khaste cheshmam cheshmam eynak eynake arzesh arzeshesh bekharam bekharim kharid pool pul poolesh pulesh moshkel
moshkeli sorag soragh darin midoonin midunin midoonid behtarin chand gheimat gheymat gheymatesh toman tomaan
man to shoma ina oon una injori inja bia biya bashe bood bud shod nashod emtehan tanha tanhayi tanhai vel velesh
edame bedam bede javab soal soalam soalamo bebin bebinid dide didam boodam sabtenam sabt nam faghat vali chon
age agar bad baad ghabl khodam khodet khodesh hanooz hanuz donbale donbal peyda nakard kard mentor dorost
""".split())
_EN_COMMON = set("""
the a an is are was were be to of and in on for with this that it you i we they my your can could should would
have has had do does did not no yes what how why when where which who will just from at by about any some
""".split())
_LATIN_WORD = re.compile(r"[a-zA-Z']+")


def detect_lang(text: str) -> str:
    """'fa' | 'finglish' | 'en' | 'mixed' | 'other'."""
    fa = sum(1 for ch in text if "؀" <= ch <= "ۿ")
    lat = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if fa == 0 and lat == 0:
        return "other"
    if fa >= lat:
        return "mixed" if lat / (fa + lat) > 0.25 else "fa"
    words = [w.lower() for w in _LATIN_WORD.findall(text)]
    fing = sum(1 for w in words if w in _FINGLISH)
    eng = sum(1 for w in words if w in _EN_COMMON)
    if fing >= 2 and fing >= eng:
        return "finglish"
    return "mixed" if fa else "en"
