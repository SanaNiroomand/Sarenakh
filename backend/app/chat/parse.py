"""Turn user input into ChatMessages.

Supported inputs
- Telegram Desktop "Export chat history" JSON (result.json), or a full-account export (picks the
  biggest chat).
- Pasted text in Telegram Desktop copy format ("Name, [02.10.26 14:31]" header + body),
  "Name: message" lines, or plain lines/paragraphs.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from .normalize import detect_lang, emoji_count, normalize

TEHRAN = timezone(timedelta(hours=3, minutes=30))
MAX_MESSAGES = 5000


class ChatParseError(ValueError):
    """Raised with a Persian, user-facing message."""


@dataclass
class ChatMessage:
    id: int
    ts: int  # unix seconds
    date: str  # local time as exported, "YYYY-MM-DDTHH:MM:SS"
    author_id: str
    author: str
    text: str  # display text
    norm: str = ""  # normalized text the agents see
    reply_to: int | None = None
    kind: str = "text"  # text | sticker | photo | video | voice | file | other
    lang: str = "fa"
    forwarded_from: str | None = None
    emojis: int = 0

    def finish(self) -> "ChatMessage":
        self.norm = normalize(self.text)
        self.lang = detect_lang(self.norm)
        self.emojis = emoji_count(self.text)
        return self

    @property
    def analyzable(self) -> bool:
        """Worth sending to the pipeline: has real words, not just a sticker/emoji/media placeholder."""
        if self.kind != "text" and self.text.startswith("["):
            return False
        return len(re.sub(r"\W", "", self.norm)) >= 4

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedChat:
    name: str
    source: str  # telegram_json | pasted_text
    messages: list[ChatMessage]
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def stats(self) -> dict:
        authors = {m.author_id for m in self.messages}
        langs: dict[str, int] = {}
        for m in self.messages:
            langs[m.lang] = langs.get(m.lang, 0) + 1
        return {
            "messages": len(self.messages),
            "analyzable": sum(1 for m in self.messages if m.analyzable),
            "authors": len(authors),
            "replies": sum(1 for m in self.messages if m.reply_to),
            "langs": langs,
            "skipped": self.skipped,
            "first": self.messages[0].date if self.messages else None,
            "last": self.messages[-1].date if self.messages else None,
        }


# --- Telegram JSON ------------------------------------------------------------------------


def _flatten(text) -> str:
    if isinstance(text, str):
        return text
    out = []
    for part in text or []:
        if isinstance(part, str):
            out.append(part)
        elif isinstance(part, dict):
            out.append(str(part.get("text", "")))
    return "".join(out)


def _kind(m: dict) -> str:
    media = m.get("media_type")
    if media == "sticker":
        return "sticker"
    if media in ("voice_message", "audio_file", "video_message"):
        return "voice"
    if media in ("video_file", "animation"):
        return "video"
    if "photo" in m:
        return "photo"
    if "file" in m:
        return "file"
    return "text"


_KIND_LABEL = {"sticker": "استیکر", "voice": "پیام صوتی", "video": "ویدیو", "photo": "عکس", "file": "فایل"}


def parse_telegram_export(raw: bytes | str | dict, max_messages: int = MAX_MESSAGES) -> ParsedChat:
    try:
        data = raw if isinstance(raw, dict) else json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ChatParseError("فایل JSON معتبر نیست. از تلگرام دسکتاپ: Export chat history ← فرمت JSON.") from e
    if not isinstance(data, dict):
        raise ChatParseError("ساختار فایل با خروجی JSON تلگرام دسکتاپ نمی‌خواند.")

    if "messages" not in data:  # full-account export: {"chats": {"list": [...]}}
        chats = (data.get("chats") or {}).get("list") or []
        chats = [c for c in chats if isinstance(c, dict) and c.get("messages")]
        if not chats:
            raise ChatParseError("در این فایل پیامی پیدا نشد. خروجی یک گروه را با فرمت JSON بگیرید.")
        data = max(chats, key=lambda c: len(c["messages"]))

    out: list[ChatMessage] = []
    skipped = 0
    for m in data.get("messages") or []:
        if not isinstance(m, dict) or m.get("type") != "message" or "id" not in m:
            skipped += 1
            continue
        kind = _kind(m)
        text = _flatten(m.get("text")).strip()
        if not text and kind != "text":
            emoji = m.get("sticker_emoji", "")
            text = f"[{_KIND_LABEL[kind]} {emoji}]".replace(" ]", "]")
        if not text:
            skipped += 1
            continue
        try:
            ts = int(m["date_unixtime"]) if m.get("date_unixtime") else int(
                datetime.fromisoformat(m["date"]).replace(tzinfo=TEHRAN).timestamp()
            )
        except (KeyError, ValueError):
            ts = 0
        author = (m.get("from") or "").strip() or "حساب حذف‌شده"
        reply = m.get("reply_to_message_id")
        out.append(ChatMessage(
            id=int(m["id"]),
            ts=ts,
            date=m.get("date") or datetime.fromtimestamp(ts, TEHRAN).strftime("%Y-%m-%dT%H:%M:%S"),
            author_id=str(m.get("from_id") or f"anon:{author}"),
            author=author,
            text=text,
            reply_to=int(reply) if isinstance(reply, int) else None,
            kind=kind,
            forwarded_from=m.get("forwarded_from"),
        ).finish())

    if not out:
        raise ChatParseError("هیچ پیام متنی در این فایل نبود.")
    out.sort(key=lambda x: (x.ts, x.id))
    warnings = []
    if len(out) > max_messages:
        warnings.append(f"فقط {max_messages} پیام آخر بررسی می‌شود (از {len(out)} پیام).")
        out = out[-max_messages:]
    return ParsedChat(name=str(data.get("name") or "گفتگوی تلگرام"), source="telegram_json",
                      messages=out, skipped=skipped, warnings=warnings)


# --- Pasted text --------------------------------------------------------------------------

_TG_COPY_HEADER = re.compile(r"^(?P<name>[^\n\[\]]{1,64}?),\s*\[(?P<when>[^\]]{4,40})\]\s*$")
_NAME_LINE = re.compile(r"^(?P<name>[^:\n\[\]]{1,40}?)\s*[:：]\s+(?P<text>\S.*)$")
_DATE_FORMATS = [
    "%d.%m.%y %H:%M", "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M:%S", "%d.%m.%Y %H:%M:%S",
    "%m/%d/%Y %I:%M %p", "%m/%d/%y %I:%M %p", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
]


def _parse_when(s: str) -> int | None:
    s = normalize(s).replace(" ", " ").strip()
    for fmt in _DATE_FORMATS:
        try:
            return int(datetime.strptime(s, fmt).replace(tzinfo=TEHRAN).timestamp())
        except ValueError:
            continue
    return None


def parse_pasted_text(text: str, max_messages: int = MAX_MESSAGES) -> ParsedChat:
    text = (text or "").replace("\r\n", "\n").strip()
    if len(re.sub(r"\s", "", text)) < 10:
        raise ChatParseError("متن واردشده خیلی کوتاه است. چند پیام از گروه را کپی کنید.")
    lines = text.split("\n")
    entries: list[tuple[str, int | None, str]] = []  # (author, ts, body)

    if sum(1 for ln in lines if _TG_COPY_HEADER.match(ln.strip())) >= 2:
        author, when, body = None, None, []
        for ln in lines:
            if h := _TG_COPY_HEADER.match(ln.strip()):
                if author is not None and "\n".join(body).strip():
                    entries.append((author, when, "\n".join(body).strip()))
                author, when, body = h["name"].strip(), _parse_when(h["when"]), []
            else:
                body.append(ln)
        if author is not None and "\n".join(body).strip():
            entries.append((author, when, "\n".join(body).strip()))
    elif sum(1 for ln in lines if _NAME_LINE.match(ln.strip())) >= max(2, len([ln for ln in lines if ln.strip()]) // 2):
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            if m := _NAME_LINE.match(ln):
                entries.append((m["name"].strip(), None, m["text"].strip()))
            elif entries:  # continuation line
                a, w, b = entries[-1]
                entries[-1] = (a, w, f"{b}\n{ln}")
    else:
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text)] if "\n\n" in text else [ln.strip() for ln in lines]
        entries = [(f"کاربر {i + 1}", None, b) for i, b in enumerate(blocks) if b]

    if not entries:
        raise ChatParseError("پیامی در متن پیدا نشد.")
    base = int(time.time()) - 60 * len(entries)
    out: list[ChatMessage] = []
    for i, (author, ts, body) in enumerate(entries[-max_messages:]):
        ts = ts or base + 60 * i
        out.append(ChatMessage(
            id=i + 1, ts=ts, date=datetime.fromtimestamp(ts, TEHRAN).strftime("%Y-%m-%dT%H:%M:%S"),
            author_id=f"name:{author}", author=author, text=body,
        ).finish())
    warnings = [f"فقط {max_messages} پیام آخر بررسی می‌شود."] if len(entries) > max_messages else []
    return ParsedChat(name="متن واردشده", source="pasted_text", messages=out, warnings=warnings)
