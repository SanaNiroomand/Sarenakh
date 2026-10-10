"""Persian posts from X (Twitter) through the official API v2. Pay-per-use: every post read is billed.

Spend is kept low on purpose:
- the search phrases are written once per customer profile and cached;
- each query keeps the posts it found in the stage cache. A repeat search within `x_cache_hours`
  costs nothing; a later one asks X only for posts newer than the last one seen (since_id);
- user names are looked up only for the people who became leads (user reads are billed too).
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from ..agents.context import cache_get, cache_get_fresh, cache_key, cache_put, cache_set, profile_fingerprint
from ..agents.prompts import PROMPT_VERSIONS, X_QUERY_SYSTEM, profile_block
from ..agents.schemas import XQueryPlan
from ..chat.parse import TEHRAN, ChatMessage, ParsedChat
from ..config import Settings
from ..llm import LLM, Usage
from ..schemas import Profile

WINDOW_S = 7 * 24 * 3600  # recent search only covers the last 7 days
MAX_KEEP = 1000  # posts kept per query in the cache
USER_TTL_S = 7 * 24 * 3600
MAX_QUERY_CHARS = 500
QUERY_SUFFIX = " lang:fa -is:retweet -has:links"  # links are mostly ads, and every post costs money

# Field sets to ask for, most preferred first. The API renamed tweet->post; if a set is refused (400),
# the next one is tried and remembered for this process. The last one expands authors, which may
# bill user reads, so it is only a fallback.
_FIELDS = [
    {"post.fields": "created_at,conversation_id,lang,author_id,referenced_posts,in_reply_to_user_id"},
    {"tweet.fields": "created_at,conversation_id,lang,author_id,referenced_tweets,in_reply_to_user_id"},
    {"post.fields": "created_at,conversation_id,lang", "expansions": "author_id"},
]
_FIELD_PARAMS = {"post.fields", "tweet.fields", "expansions", "user.fields"}


class XError(Exception):
    """Raised with a Persian, user-facing message."""


class _FieldsRefused(XError):
    pass


def _bad_params(resp: httpx.Response) -> set[str]:
    try:
        body = resp.json()
    except ValueError:
        return set()
    names: set[str] = set()
    for err in body.get("errors") or []:
        names |= set((err.get("parameters") or {}).keys())
    return names


class XClient:
    variant = 0  # index into _FIELDS that the API accepted last (shared in this process)

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.x_bearer_token:
            raise XError("جستجوی ایکس فعال نیست: توکن X تنظیم نشده است.")
        self.s = settings
        self.billed_posts = 0  # distinct posts read: X bills the same post once per day
        self.billed_users = 0
        self._read: set[str] = set()
        self.http = httpx.AsyncClient(
            base_url=settings.x_api_base.rstrip("/") + "/", transport=transport, timeout=20.0,
            headers={"Authorization": f"Bearer {settings.x_bearer_token}", "User-Agent": "Sarenakh/1.0"},
        )

    async def __aenter__(self) -> "XClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.http.aclose()

    @property
    def cost_usd(self) -> float:
        return self.billed_posts * self.s.x_price_per_post_usd + self.billed_users * self.s.x_price_per_user_usd

    async def _get(self, path: str, params: dict) -> dict:
        try:
            r = await self.http.get(path, params=params)
        except httpx.HTTPError as e:
            raise XError("به ایکس وصل نشدیم. چند دقیقه بعد دوباره امتحان کنید.") from e
        if r.status_code == 200:
            return r.json()
        if r.status_code == 400 and _bad_params(r) & _FIELD_PARAMS:
            raise _FieldsRefused(r.text[:300])
        raise XError({
            400: "ایکس جستجو را نپذیرفت.",
            401: "توکن X پذیرفته نشد.",
            402: "اعتبار حساب X تمام شده است.",
            403: "توکن X به جستجو دسترسی ندارد.",
            429: "سقف درخواست ایکس پر شده؛ چند دقیقه بعد دوباره امتحان کنید.",
        }.get(r.status_code, f"ایکس خطا داد (کد {r.status_code})."))

    async def search(self, query: str, *, limit: int, since_id: str | None = None) -> tuple[list[dict], dict[str, dict]]:
        """Newest posts first, never more than `limit`. Returns (posts, users included by the API)."""
        posts: list[dict] = []
        users: dict[str, dict] = {}
        token = None
        while limit - len(posts) >= 10:  # a page holds 10-100 posts
            params = {"query": query, "max_results": min(100, limit - len(posts)), "sort_order": "recency"}
            if since_id:
                params["since_id"] = since_id
            if token:
                params["next_token"] = token
            while True:
                try:
                    data = await self._get("tweets/search/recent", {**params, **_FIELDS[XClient.variant]})
                    break
                except _FieldsRefused:
                    if XClient.variant + 1 >= len(_FIELDS):
                        raise XError("ایکس فیلدهای درخواست را نپذیرفت.") from None
                    XClient.variant += 1
            page = [_post(p) for p in data.get("data") or []]
            fresh = {p["id"] for p in page} - self._read
            self._read |= fresh
            self.billed_posts += len(fresh)
            posts += page
            for u in (data.get("includes") or {}).get("users") or []:
                users[str(u["id"])] = u
            token = (data.get("meta") or {}).get("next_token")
            if not token or not page:
                break
        return posts, users

    async def users(self, ids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(ids), 100):
            data = await self._get("users", {"ids": ",".join(ids[i : i + 100]), "user.fields": "username,name"})
            found = data.get("data") or []
            self.billed_users += len(found)
            out.update({str(u["id"]): u for u in found})
        return out


def _post(p: dict) -> dict:
    refs = p.get("referenced_posts") or p.get("referenced_tweets") or []
    parent = next((str(r["id"]) for r in refs if r.get("type") == "replied_to" and r.get("id")), None)
    return {"id": str(p["id"]), "text": p.get("text") or "", "author_id": str(p.get("author_id") or ""),
            "created_at": p.get("created_at") or "", "reply_to": parent}


def _ts(created_at: str) -> int:
    try:
        return int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


# --- queries ------------------------------------------------------------------------------------


def _group(terms: list[str], limit: int) -> list[str]:
    out: list[str] = []
    for t in terms[:limit]:
        t = " ".join(re.sub(r'["()]', " ", t).split())
        if t and t not in out:
            out.append(t)
    return [f'"{t}"' if " " in t else t for t in out]


def build_query(topic: list[str], need: list[str]) -> str:
    """(topic OR ...) (need OR ...) plus filters; a post must contain one of each."""
    a, b = _group(topic, 5), _group(need, 8)

    def text() -> str:
        groups = [g for g in (a, b) if g]
        return " ".join("(" + " OR ".join(g) + ")" for g in groups) + QUERY_SUFFIX

    while len(text()) > MAX_QUERY_CHARS and (len(a) > 1 or len(b) > 1):
        (b if len(b) >= len(a) else a).pop()
    return text() if a else ""


async def plan_queries(llm: LLM, settings: Settings, profile: Profile) -> tuple[list[dict], Usage | None]:
    """Search queries for this profile: [{q, why}]. Usage is None when cached."""
    model = settings.profile_model
    key = cache_key("x_queries", model, PROMPT_VERSIONS["x_queries"], profile_fingerprint(profile))
    if hit := cache_get(key):
        return hit[0]["queries"], None
    plan, usage = await llm.structured(
        model=model,
        instructions=X_QUERY_SYSTEM.format(profile=profile_block(profile, with_examples=True)),
        input="Write the 4 queries.",
        output_type=XQueryPlan,
        reasoning=settings.agent_reasoning,
        max_output_tokens=2000,
        cache_key="sarenakh-xq",
    )
    queries = [{"q": q, "why": item.why} for item in plan.queries[:4] if (q := build_query(item.topic, item.need))]
    if queries:
        cache_put(key, "x_queries", {"queries": queries}, usage.cost_usd)
    return queries, usage


# --- search with cache --------------------------------------------------------------------------


@dataclass
class XSearch:
    posts: list[dict] = field(default_factory=list)  # newest first, unique
    users: dict[str, dict] = field(default_factory=dict)
    queries: list[dict] = field(default_factory=list)  # {q, why, found, new, from_cache}


async def search_posts(xc: XClient, queries: list[dict], *, max_posts: int, cache_s: float) -> XSearch:
    """Run the queries, at most `max_posts` new (billed) posts in total, reusing cached posts."""
    out = XSearch()
    seen: set[str] = set()
    per_query = max(10, max_posts // max(1, len(queries)))
    now = time.time()
    for q in queries:
        key = cache_key("x_search", q["q"])
        fresh = cache_get_fresh(key, cache_s)
        old = cache_get_fresh(key, WINDOW_S)
        new: list[dict] = []
        if fresh is not None:
            posts = fresh["posts"]
        else:
            posts = [p for p in (old or {}).get("posts") or [] if now - _ts(p["created_at"]) < WINDOW_S]
            budget_left = max_posts - xc.billed_posts
            if budget_left >= 10:
                # only what is newer than the newest post we already have (X rejects too-old since_ids)
                since = posts[0]["id"] if posts and now - _ts(posts[0]["created_at"]) < WINDOW_S - 86400 else None
                new, users = await xc.search(q["q"], limit=min(per_query, budget_left), since_id=since)
                out.users.update(users)
                merged = {p["id"]: p for p in [*new, *posts]}
                posts = sorted(merged.values(), key=lambda p: int(p["id"]), reverse=True)[:MAX_KEEP]
                cache_set(key, "x_search", {"q": q["q"], "posts": posts})
        for p in posts:
            if p["id"] not in seen:
                seen.add(p["id"])
                out.posts.append(p)
        out.queries.append({**q, "found": len(posts), "new": len(new), "from_cache": fresh is not None})
    out.posts.sort(key=lambda p: int(p["id"]), reverse=True)
    return out


async def resolve_authors(xc: XClient, author_ids: list[str]) -> dict[str, dict]:
    """{id: {username, name}} for these X users; cached for a week, so each person is paid once."""
    out: dict[str, dict] = {}
    todo = []
    for aid in dict.fromkeys(author_ids):
        if hit := cache_get_fresh(cache_key("x_user", aid), USER_TTL_S):
            out[aid] = hit
        else:
            todo.append(aid)
    if todo:
        for aid, u in (await xc.users(todo)).items():
            row = {"username": u.get("username", ""), "name": u.get("name", "")}
            cache_set(cache_key("x_user", aid), "x_user", row)
            out[aid] = row
    return out


# --- to a dataset -------------------------------------------------------------------------------


def author_label(aid: str, user: dict | None) -> str:
    if user and user.get("username"):
        name = (user.get("name") or "").strip()
        return f"{name} (@{user['username']})" if name else f"@{user['username']}"
    return f"کاربر ایکس {aid[-4:]}" if aid else "کاربر ایکس"


def _clean(text: str) -> str:
    text = html.unescape(text)
    body = re.sub(r"^(?:@\w+\s+)+", "", text).strip()  # the @mentions a reply starts with
    return body or text.strip()


def to_parsed(found: XSearch, name: str) -> ParsedChat:
    posts = sorted(found.posts, key=lambda p: (_ts(p["created_at"]), int(p["id"])))
    local = {p["id"]: i for i, p in enumerate(posts, 1)}
    msgs = []
    for i, p in enumerate(posts, 1):
        ts = _ts(p["created_at"]) or int(time.time())
        aid = p["author_id"]
        msgs.append(ChatMessage(
            id=i, ts=ts, date=datetime.fromtimestamp(ts, TEHRAN).strftime("%Y-%m-%dT%H:%M:%S"),
            author_id=f"x:{aid}" if aid else f"x:post{p['id']}", author=author_label(aid, found.users.get(aid)),
            text=_clean(p["text"]), reply_to=local.get(p["reply_to"] or ""), ext_id=p["id"],
        ).finish())
    return ParsedChat(name=name, source="twitter", messages=msgs)


def post_url(ext_id: str | None) -> str | None:
    return f"https://x.com/i/status/{ext_id}" if ext_id else None
