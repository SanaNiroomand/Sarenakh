"""In-memory index over one chat: reply threads, author history, neighbours, keyword search.

The investigator agent's tools are thin wrappers around these methods.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque

from .normalize import normalize
from .parse import ChatMessage

_TOKEN = re.compile(r"[\w‌]+")


def _tokens(text: str) -> set[str]:
    return {t.replace("‌", "") for t in _TOKEN.findall(text.lower()) if len(t) >= 2}


class ChatIndex:
    def __init__(self, messages: list[ChatMessage]):
        self.msgs = sorted(messages, key=lambda m: (m.ts, m.id))
        self.by_id = {m.id: m for m in self.msgs}
        self.pos = {m.id: i for i, m in enumerate(self.msgs)}
        self.children: dict[int, list[int]] = defaultdict(list)
        self.by_author: dict[str, list[ChatMessage]] = defaultdict(list)
        for m in self.msgs:
            if m.reply_to in self.by_id:
                self.children[m.reply_to].append(m.id)
            self.by_author[m.author_id].append(m)
        self._tok = {m.id: _tokens(m.norm) for m in self.msgs}

    def get(self, msg_id: int) -> ChatMessage | None:
        return self.by_id.get(msg_id)

    # --- threads ---------------------------------------------------------------------------

    def ancestors(self, msg_id: int, limit: int = 12) -> list[ChatMessage]:
        """Reply chain above the message, root first."""
        out: list[ChatMessage] = []
        seen = {msg_id}
        cur = self.by_id.get(msg_id)
        while cur and cur.reply_to in self.by_id and cur.reply_to not in seen and len(out) < limit:
            seen.add(cur.reply_to)
            cur = self.by_id[cur.reply_to]
            out.append(cur)
        return out[::-1]

    def descendants(self, msg_id: int, limit: int = 40) -> list[ChatMessage]:
        """All replies below the message (any depth), chronological."""
        out: list[ChatMessage] = []
        queue = deque(self.children.get(msg_id, []))
        seen = {msg_id}
        while queue and len(out) < limit:
            cid = queue.popleft()
            if cid in seen:
                continue
            seen.add(cid)
            out.append(self.by_id[cid])
            queue.extend(self.children.get(cid, []))
        return sorted(out, key=lambda m: (m.ts, m.id))

    def thread(self, msg_id: int) -> list[ChatMessage]:
        """Ancestors + the message + everything that replied below it, chronological."""
        m = self.by_id.get(msg_id)
        if not m:
            return []
        return self.ancestors(msg_id) + [m] + self.descendants(msg_id)

    # --- people & surroundings --------------------------------------------------------------

    def user_history(self, author_id: str, around: int | None = None, limit: int = 15) -> list[ChatMessage]:
        """The author's messages (stickers excluded), closest to `around` if there are too many."""
        hist = [m for m in self.by_author.get(author_id, []) if m.kind != "sticker"]
        if len(hist) <= limit:
            return hist
        if around in self.by_id:
            t = self.by_id[around].ts
            hist = sorted(hist, key=lambda m: abs(m.ts - t))[:limit]
            return sorted(hist, key=lambda m: (m.ts, m.id))
        return hist[-limit:]

    def nearby(self, msg_id: int, n: int = 5) -> list[ChatMessage]:
        i = self.pos.get(msg_id)
        if i is None:
            return []
        return self.msgs[max(0, i - n) : i + n + 1]

    def search(self, query: str, limit: int = 8, exclude: set[int] | None = None) -> list[ChatMessage]:
        """Keyword search over normalized text (Persian, Finglish and English tokens)."""
        q = _tokens(normalize(query))
        if not q:
            return []
        scored = []
        for m in self.msgs:
            if exclude and m.id in exclude:
                continue
            hit = len(q & self._tok[m.id])
            if hit:
                scored.append((hit, m.ts, m))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return sorted((m for _, _, m in scored[:limit]), key=lambda m: (m.ts, m.id))

    # --- rendering for prompts ----------------------------------------------------------------

    @staticmethod
    def line(m: ChatMessage, focus: int | None = None, max_chars: int = 500) -> str:
        text = m.norm if len(m.norm) <= max_chars else m.norm[:max_chars] + "…"
        text = text.replace("\n", " ⏎ ")
        reply = f" ↩#{m.reply_to}" if m.reply_to else ""
        fwd = f" [fwd: {m.forwarded_from}]" if m.forwarded_from else ""
        mark = ">>> " if focus == m.id else ""
        return f"{mark}#{m.id} [{m.date[5:16].replace('T', ' ')}] {m.author} ({m.author_id}){reply}{fwd}: {text}"

    def render(self, msgs: list[ChatMessage], focus: int | None = None, max_chars: int = 500) -> str:
        return "\n".join(self.line(m, focus, max_chars) for m in msgs) or "(nothing)"
