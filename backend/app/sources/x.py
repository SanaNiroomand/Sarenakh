"""Persian posts from X (Twitter), from one of three providers (Settings.x_source picks one):

- twitterapi.io (TWITTERAPI_KEY): an unofficial reseller that scrapes X. About $0.15 per 1,000
  tweets, pays by card or crypto.
- twscrape (TWSCRAPE_COOKIES): free. Crawls X's own web search as a logged-in X account, using that
  account's browser cookies. The account may be suspended and the crawler breaks when X changes.
- the official X API v2 (X_BEARER_TOKEN): $0.005 per post, needs prepaid credits, last 7 days only.
The first two are outside X's own terms; the owner chose them knowingly.

The paid ones bill per post returned, so spend is kept low on purpose:
- the search phrases are written once per customer profile and cached;
- each query keeps the posts it found in the stage cache. A repeat search within `x_cache_hours`
  costs nothing; a later one asks only for posts newer than the newest one already kept;
- with the official API, user names are looked up only for leads (user reads are billed too);
  twitterapi.io returns the author with every tweet.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from ..agents.context import cache_get, cache_get_fresh, cache_key, cache_put, cache_set, profile_fingerprint
from ..agents.prompts import PROMPT_VERSIONS, X_QUERY_SYSTEM, profile_block
from ..agents.schemas import XQueryPlan
from ..chat.parse import TEHRAN, ChatMessage, ParsedChat
from ..config import Settings
from ..llm import LLM, Usage
from ..schemas import Profile

log = logging.getLogger("sarenakh.x")

MAX_KEEP = 1000  # posts kept per query in the cache
USER_TTL_S = 7 * 24 * 3600
MAX_QUERY_CHARS = 500

# Field sets to ask the official API for, most preferred first. The API renamed tweet->post; if a set
# is refused (400), the next one is tried and remembered for this process. The last one expands
# authors, which may bill user reads, so it is only a fallback.
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


class _Source:
    """What search_posts needs from a provider."""

    name = ""
    suffix = ""  # filters appended to every query
    page_min = 1  # smallest number of posts worth asking for
    window_s = 7 * 24 * 3600  # how far back posts count as current
    pause_s = 0.0  # wait between queries

    def __init__(self, settings: Settings, base_url: str = "", headers: dict | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.s = settings
        self.billed_posts = 0
        self.billed_users = 0
        self.http = httpx.AsyncClient(base_url=base_url.rstrip("/") + "/", transport=transport, timeout=30.0,
                                      headers={"User-Agent": "Sarenakh/1.0", **(headers or {})}) if base_url else None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        if self.http:
            await self.http.aclose()

    @property
    def cost_usd(self) -> float:
        return self.billed_posts * self.s.x_price_per_post() + self.billed_users * self.s.x_price_per_user_usd

    async def search(self, query: str, *, limit: int, since: dict | None = None) -> tuple[list[dict], dict[str, dict]]:
        raise NotImplementedError

    async def users(self, ids: list[str]) -> dict[str, dict]:
        return {}


class XClient(_Source):
    """Official X API v2."""

    name = "official"
    suffix = " lang:fa -is:retweet -has:links"  # links are mostly ads, and every post costs money
    page_min = 10  # a page holds 10-100 posts
    variant = 0  # index into _FIELDS that the API accepted last (shared in this process)

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.x_bearer_token:
            raise XError("جستجوی ایکس فعال نیست: توکن X تنظیم نشده است.")
        super().__init__(settings, settings.x_api_base, {"Authorization": f"Bearer {settings.x_bearer_token}"},
                         transport)
        self._read: set[str] = set()  # X bills the same post once per day

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

    async def search(self, query: str, *, limit: int, since: dict | None = None) -> tuple[list[dict], dict[str, dict]]:
        """Newest posts first, never more than `limit`. Returns (posts, users included by the API)."""
        posts: list[dict] = []
        users: dict[str, dict] = {}
        token = None
        while limit - len(posts) >= self.page_min:
            params = {"query": query, "max_results": min(100, limit - len(posts)), "sort_order": "recency"}
            if since:
                params["since_id"] = since["id"]
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


class TwitterApiIo(_Source):
    """twitterapi.io advanced search (X's own search syntax, 20 tweets per page, author included)."""

    name = "twitterapi"
    suffix = " lang:fa -filter:retweets -filter:links"
    page = 20
    page_min = 20  # pages are always 20, so a query starts only when a whole page fits the budget
    retry_wait_s = 5.5  # accounts that never paid get 1 request per 5 seconds

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.twitterapi_key:
            raise XError("جستجوی ایکس فعال نیست: کلید twitterapi.io تنظیم نشده است.")
        super().__init__(settings, settings.twitterapi_base, {"X-API-Key": settings.twitterapi_key}, transport)
        self.window_s = max(1, settings.x_window_days) * 86400

    async def _get(self, path: str, params: dict) -> dict:
        for attempt in range(8):
            try:
                r = await self.http.get(path, params=params)
            except httpx.HTTPError as e:
                raise XError("به سرویس توییتر وصل نشدیم. چند دقیقه بعد دوباره امتحان کنید.") from e
            if r.status_code != 429 or attempt == 7:
                break
            await asyncio.sleep(self.retry_wait_s)
        text = r.text.lower()
        if r.status_code == 200 and '"status":"error"' not in text.replace(" ", ""):
            return r.json()
        if r.status_code == 402 or "credit" in text or "balance" in text:
            raise XError("اعتبار twitterapi.io تمام شده است.")
        raise XError({
            401: "کلید twitterapi.io پذیرفته نشد.",
            403: "کلید twitterapi.io دسترسی ندارد.",
            429: "سقف درخواست twitterapi.io پر شده؛ چند دقیقه بعد دوباره امتحان کنید.",
        }.get(r.status_code, f"سرویس توییتر خطا داد (کد {r.status_code})."))

    async def search(self, query: str, *, limit: int, since: dict | None = None) -> tuple[list[dict], dict[str, dict]]:
        """Newest first, at most max(limit, 20) tweets (pages are fixed at 20)."""
        start = int(time.time()) - self.window_s
        if since:
            start = max(start, _ts(since["created_at"]) + 1)
        q = f"{query} since_time:{start}"
        posts: list[dict] = []
        cursor = ""
        while True:
            data = await self._get("twitter/tweet/advanced_search", {"query": q, "queryType": "Latest", "cursor": cursor})
            raw = data.get("tweets") or []
            self.billed_posts += len(raw)
            page = [_post_tapi(t) for t in raw if t.get("id") and not t.get("retweeted_tweet")]
            posts += page
            cursor = data.get("next_cursor") or ""
            if not raw or not data.get("has_next_page") or not cursor or len(posts) + self.page > limit:
                break
        return posts, {}


TWSCRAPE_ACCOUNT = "sarenakh"
_tws: dict[str, Any] = {}  # the twscrape API object, rebuilt when the cookies in .env change


async def _twscrape_api(settings: Settings, refresh: bool = False):
    """The shared twscrape API. refresh=True re-saves the account from .env, which also re-enables it
    after twscrape switched it off on an error (a later bad answer switches it off again)."""
    os.environ.setdefault("TWS_TELEMETRY", "0")  # the library can report usage stats; keep it off
    from twscrape import API

    fp = hashlib.sha256(f"{settings.twscrape_cookies}|{settings.twscrape_proxy}".encode()).hexdigest()
    if _tws.get("fp") != fp:
        _tws.update(fp=fp, api=API(str(settings.data_dir / "twscrape.db"), proxy=settings.twscrape_proxy or None,
                                   raise_when_no_account=True))
        refresh = True
    if refresh:
        try:
            await _tws["api"].pool.add_account_cookies(TWSCRAPE_ACCOUNT, settings.twscrape_cookies)
        except ValueError as e:
            _tws.clear()
            raise XError("کوکی‌های حساب ایکس باید auth_token و ct0 را داشته باشند.") from e
    return _tws["api"]


class Twscrape(_Source):
    """Free: X's own web search through twscrape, as the X account whose cookies are in .env."""

    name = "twscrape"
    suffix = TwitterApiIo.suffix  # the same web search syntax
    pause_s = 2.0  # go easy on the account
    timeout_s = 120.0

    def __init__(self, settings: Settings, api: Any = None):
        if not settings.twscrape_cookies:
            raise XError("جستجوی ایکس فعال نیست: کوکی‌های حساب ایکس تنظیم نشده است.")
        super().__init__(settings)
        self.window_s = max(1, settings.x_window_days) * 86400
        self._api = api
        self._fresh = True  # first query of this search re-enables the account

    async def search(self, query: str, *, limit: int, since: dict | None = None) -> tuple[list[dict], dict[str, dict]]:
        from twscrape.accounts_pool import NoAccountError

        start = int(time.time()) - self.window_s
        if since:
            start = max(start, _ts(since["created_at"]) + 1)
        api = self._api or await _twscrape_api(self.s, refresh=self._fresh)
        self._fresh = False
        posts: list[dict] = []

        async def collect() -> None:
            async for t in api.search(f"{query} since_time:{start}", limit=limit):
                if not getattr(t, "retweetedTweet", None):
                    posts.append(_post_tws(t))
                if len(posts) >= limit:
                    break

        try:
            await asyncio.wait_for(collect(), self.timeout_s)
        except NoAccountError as e:
            if not posts:
                raise XError("حساب ایکس در دسترس نیست: کوکی‌ها منقضی شده یا حساب موقتا محدود شده است.") from e
        except asyncio.TimeoutError as e:
            if not posts:
                raise XError("ایکس دیر جواب داد. چند دقیقه بعد دوباره امتحان کنید.") from e
        except Exception as e:  # noqa: BLE001 — the crawler breaks when X changes its site
            log.warning("twscrape search failed: %s", e)
            if not posts:
                raise XError("خواندن از ایکس انجام نشد؛ شاید ایکس چیزی را عوض کرده و twscrape باید به‌روز شود.") from e
        return posts[:limit], {}


def make_x_client(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> _Source:
    source = settings.x_source()
    if source == "twitterapi":
        return TwitterApiIo(settings, transport)
    if source == "twscrape":
        return Twscrape(settings)
    if source == "official":
        return XClient(settings, transport)
    raise XError("جستجوی ایکس فعال نیست: کلید twitterapi.io، کوکی حساب ایکس یا توکن X تنظیم نشده است.")


def _post(p: dict) -> dict:
    refs = p.get("referenced_posts") or p.get("referenced_tweets") or []
    parent = next((str(r["id"]) for r in refs if r.get("type") == "replied_to" and r.get("id")), None)
    return {"id": str(p["id"]), "text": p.get("text") or "", "author_id": str(p.get("author_id") or ""),
            "created_at": p.get("created_at") or "", "reply_to": parent}


def _iso(created_at: str) -> str:
    """twitterapi.io dates look like 'Tue Dec 10 07:00:30 +0000 2024'."""
    for parse in (lambda s: datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y"),
                  lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))):
        try:
            return parse(created_at).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except ValueError:
            continue
    return ""


def _post_tapi(t: dict) -> dict:
    a = t.get("author") or {}
    return {"id": str(t["id"]), "text": t.get("text") or "", "author_id": str(a.get("id") or ""),
            "created_at": _iso(t.get("createdAt") or ""), "reply_to": str(t.get("inReplyToId") or "") or None,
            "username": a.get("userName") or "", "name": a.get("name") or ""}


def _post_tws(t: Any) -> dict:
    u = t.user
    reply = getattr(t, "inReplyToTweetIdStr", None) or getattr(t, "inReplyToTweetId", None)
    return {"id": str(t.id_str or t.id), "text": t.rawContent or "", "author_id": str(u.id_str or u.id) if u else "",
            "created_at": t.date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "reply_to": str(reply) if reply else None,
            "username": u.username if u else "", "name": u.displayname if u else ""}


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


def build_query(topic: list[str], need: list[str], suffix: str = XClient.suffix) -> str:
    """(topic OR ...) (need OR ...) plus filters; a post must contain one of each."""
    a, b = _group(topic, 5), _group(need, 8)

    def text() -> str:
        groups = [g for g in (a, b) if g]
        return " ".join("(" + " OR ".join(g) + ")" for g in groups) + suffix

    while len(text()) > MAX_QUERY_CHARS and (len(a) > 1 or len(b) > 1):
        (b if len(b) >= len(a) else a).pop()
    return text() if a else ""


async def plan_queries(llm: LLM, settings: Settings, profile: Profile) -> tuple[list[dict], Usage | None]:
    """Search plan for this profile: [{topic, need, why}]. Usage is None when cached."""
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
    queries = [{"topic": item.topic, "need": item.need, "why": item.why}
               for item in plan.queries[:4] if build_query(item.topic, item.need)]
    if queries:
        cache_put(key, "x_queries", {"queries": queries}, usage.cost_usd)
    return queries, usage


# --- search with cache --------------------------------------------------------------------------


@dataclass
class XSearch:
    posts: list[dict] = field(default_factory=list)  # newest first, unique
    users: dict[str, dict] = field(default_factory=dict)
    queries: list[dict] = field(default_factory=list)  # {q, why, found, new, from_cache}


async def search_posts(xc: _Source, plan: list[dict], *, max_posts: int, cache_s: float) -> XSearch:
    """Run the plan's queries, at most about `max_posts` new (billed) posts in total, reusing cached posts."""
    out = XSearch()
    seen: set[str] = set()
    per_query = max(xc.page_min, max_posts // max(1, len(plan)))
    now = time.time()
    for n, item in enumerate(plan):
        q = build_query(item["topic"], item["need"], xc.suffix)
        if not q:
            continue
        key = cache_key("x_search", xc.name, q)
        fresh = cache_get_fresh(key, cache_s)
        new: list[dict] = []
        if fresh is not None:
            posts = fresh["posts"]
        else:
            old = cache_get_fresh(key, xc.window_s) or {}
            posts = [p for p in old.get("posts") or [] if now - _ts(p["created_at"]) < xc.window_s]
            budget_left = max_posts - xc.billed_posts
            if budget_left >= xc.page_min:
                if n and xc.pause_s:
                    await asyncio.sleep(xc.pause_s)
                # only what is newer than the newest post we already have (X rejects too-old since_ids)
                newest = posts[0] if posts and now - _ts(posts[0]["created_at"]) < xc.window_s - 86400 else None
                new, users = await xc.search(q, limit=min(per_query, budget_left), since=newest)
                out.users.update(users)
                merged = {p["id"]: p for p in [*new, *posts]}
                posts = sorted(merged.values(), key=lambda p: int(p["id"]), reverse=True)[:MAX_KEEP]
                cache_set(key, "x_search", {"q": q, "posts": posts})
        for p in posts:
            if p["id"] not in seen:
                seen.add(p["id"])
                out.posts.append(p)
        out.queries.append({"q": q, "why": item.get("why", ""), "found": len(posts), "new": len(new),
                            "from_cache": fresh is not None})
    out.posts.sort(key=lambda p: int(p["id"]), reverse=True)
    return out


async def resolve_authors(xc: _Source, author_ids: list[str]) -> dict[str, dict]:
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

UNNAMED = "کاربر ایکس"


def author_label(aid: str, user: dict | None) -> str:
    if user and user.get("username"):
        name = (user.get("name") or "").strip()
        return f"{name} (@{user['username']})" if name else f"@{user['username']}"
    return f"{UNNAMED} {aid[-4:]}" if aid else UNNAMED


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
        user = found.users.get(aid) or (p if p.get("username") else None)
        msgs.append(ChatMessage(
            id=i, ts=ts, date=datetime.fromtimestamp(ts, TEHRAN).strftime("%Y-%m-%dT%H:%M:%S"),
            author_id=f"x:{aid}" if aid else f"x:post{p['id']}", author=author_label(aid, user)[:120],
            text=_clean(p["text"]), reply_to=local.get(p["reply_to"] or ""), ext_id=p["id"],
        ).finish())
    return ParsedChat(name=name, source="twitter", messages=msgs)


def post_url(ext_id: str | None) -> str | None:
    return f"https://x.com/i/status/{ext_id}" if ext_id else None
