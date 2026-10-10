"""Product page reader and X search, with no network: pages and X API answers are faked."""

import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.context import cache_key, cache_set
from app.agents.schemas import ProductFacts
from app.config import get_settings
from app.db import init_db
from app.main import app
from app.sources import web, x


@pytest.fixture(autouse=True, scope="module")
def _db():
    init_db()


PAGE = """<html><head><title>دوره پایتون | سایت</title>
<meta name="description" content="پایتون را از صفر یاد بگیرید">
<meta property="og:site_name" content="سایت">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"x"},
{"@type":"Product","name":"دوره پایتون","image":"a.png","offers":{"@type":"Offer","price":"3499000","priceCurrency":"IRR"}}]}</script>
<style>.a{color:red}</style><script>var secret = 1;</script></head>
<body><nav><a>خانه</a><a>دوره‌ها</a></nav><h1>دوره پایتون</h1><p>قیمت: ۳,۴۹۹,۰۰۰ <span>تومان</span></p>
<p>۱۱۰ درسنامه</p><footer><a>خانه</a></footer></body></html>"""


def test_parse_html_keeps_text_meta_and_product_data():
    p = web.parse_html("https://example.com/p", PAGE)
    assert p.title == "دوره پایتون | سایت"
    assert p.description == "پایتون را از صفر یاد بگیرید"
    assert "قیمت: ۳,۴۹۹,۰۰۰ تومان" in p.text  # inline tags do not split a line
    assert "secret" not in p.text and "color" not in p.text
    assert "خانه دوره‌ها" in p.text  # side-by-side menu links stay separate words
    assert web.parse_html("u", "<p>تکرار</p><p>تکرار</p>").text == "تکرار"  # repeated lines dropped
    assert p.structured[0]["name"] == "دوره پایتون" and "image" not in p.structured[0]
    assert p.structured[0]["offers"]["price"] == "3499000"


@pytest.mark.parametrize("ip,public", [
    ("8.8.8.8", True), ("127.0.0.1", False), ("10.1.2.3", False), ("192.168.1.1", False),
    ("169.254.169.254", False), ("100.64.0.1", False), ("::1", False), ("::ffff:127.0.0.1", False),
    ("fd00::1", False), ("0.0.0.0", False),
])
def test_only_public_addresses(ip, public):
    assert web._is_public(ip) is public


async def test_local_names_are_blocked():
    with pytest.raises(web.BlockedAddress):
        await web._public_ip("localhost", 80)
    with pytest.raises(web.PageError):
        await web.fetch_page("http://127.0.0.1:8000/", use_cache=False)


@pytest.mark.parametrize("url", ["localhost:8000", "ftp://example.com/a", "http://user:pw@example.com/", "nonsense"])
def test_bad_links_are_refused(url):
    with pytest.raises(web.PageError):
        web.check_url(url)


async def test_fetch_page_is_cached():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, html=PAGE)

    t = httpx.MockTransport(handler)
    url = f"https://example.com/p/{time.time()}"
    a = await web.fetch_page(url, transport=t)
    b = await web.fetch_page(url, transport=t)
    assert a.title == b.title and len(calls) == 1


async def test_non_html_is_refused():
    t = httpx.MockTransport(lambda r: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}))
    with pytest.raises(web.PageError):
        await web.fetch_page("https://example.com/file.pdf", transport=t, use_cache=False)


# --- X --------------------------------------------------------------------------------------------


def _iso(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class FakeX:
    """Answers recent search with numbered posts, newest first, honoring max_results/next_token/since_id."""

    def __init__(self, total=30, refuse_post_fields=False):
        self.total = total
        self.refuse_post_fields = refuse_post_fields
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        self.requests.append(q)
        assert request.headers["authorization"] == "Bearer test-token"
        if request.url.path.endswith("/users"):
            ids = q["ids"].split(",")
            return httpx.Response(200, json={"data": [{"id": i, "username": f"user{i}", "name": f"نام {i}"} for i in ids]})
        if self.refuse_post_fields and "post.fields" in q:
            return httpx.Response(400, json={"errors": [{"parameters": {"post.fields": [q["post.fields"]]},
                                                         "message": "invalid"}]})
        ids = list(range(1000 + self.total, 1000, -1))  # newest first
        if "since_id" in q:
            ids = [i for i in ids if i > int(q["since_id"])]
        start = int(q.get("next_token", 0))
        page = ids[start : start + int(q["max_results"])]
        refs = "referenced_tweets" if "tweet.fields" in q else "referenced_posts"
        data = [{"id": str(i), "author_id": str(i % 7), "created_at": _iso(1000 + 1000 - i),
                 "text": f"@someone @other کسی دوره پایتون خوب سراغ داره؟ &amp; {i}",
                 **({refs: [{"type": "replied_to", "id": str(i - 1)}]} if i % 5 == 0 else {})} for i in page]
        meta = {"result_count": len(data)}
        if start + len(page) < len(ids):
            meta["next_token"] = str(start + len(page))
        return httpx.Response(200, json={"data": data, "meta": meta})


@pytest.fixture
def xsettings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "x_bearer_token", "test-token")
    monkeypatch.setattr(s, "twitterapi_key", "")  # tests must not depend on the local .env
    monkeypatch.setattr(s, "twscrape_cookies", "")
    monkeypatch.setattr(s, "x_provider", "auto")
    monkeypatch.setattr(x.XClient, "variant", 0)
    monkeypatch.setattr(x.TwitterApiIo, "retry_wait_s", 0)
    return s


def _plan(*words):
    stamp = str(time.time())
    return [{"topic": [w + stamp], "need": ["پیشنهاد"], "why": w} for w in words]


def test_build_query():
    q = x.build_query(["پایتون", "python", "پایتون"], ["پیشنهاد", 'گیر "کردم"'])
    assert q == '(پایتون OR python) (پیشنهاد OR "گیر کردم") lang:fa -is:retweet -has:links'
    assert x.build_query(["پایتون"], []) == "(پایتون) lang:fa -is:retweet -has:links"
    long = x.build_query([f"موضوع شماره {i}" for i in range(5)], [f"عبارت خیلی طولانی شماره {i} " * 4 for i in range(8)])
    assert len(long) <= x.MAX_QUERY_CHARS and long.endswith("-has:links") and long.count("(") == 2
    assert x.build_query(["", "  "], ["کمک"]) == ""


async def test_search_pages_and_never_exceeds_limit(xsettings):
    fake = FakeX(total=300)
    async with x.XClient(xsettings, transport=httpx.MockTransport(fake.handler)) as xc:
        posts, _ = await xc.search("q", limit=150)
    assert len(posts) == 150 and xc.billed_posts == 150
    assert [r["max_results"] for r in fake.requests] == ["100", "50"]
    assert posts[0]["id"] == "1300"


async def test_field_names_fall_back(xsettings):
    fake = FakeX(total=20, refuse_post_fields=True)
    async with x.XClient(xsettings, transport=httpx.MockTransport(fake.handler)) as xc:
        posts, _ = await xc.search("q", limit=20)
    assert len(posts) == 20 and x.XClient.variant == 1
    assert any(p["reply_to"] for p in posts)  # parsed from referenced_tweets


async def test_x_errors_are_persian(xsettings):
    t = httpx.MockTransport(lambda r: httpx.Response(402, json={"title": "CreditsDepleted"}))
    async with x.XClient(xsettings, transport=t) as xc:
        with pytest.raises(x.XError, match="اعتبار"):
            await xc.search("q", limit=10)


async def test_search_cache_then_only_newer_posts(xsettings):
    queries = _plan("تست", "دوم")
    fake = FakeX(total=50)
    t = httpx.MockTransport(fake.handler)

    async with x.XClient(xsettings, transport=t) as xc:
        first = await x.search_posts(xc, queries, max_posts=40, cache_s=3600)
    assert len(fake.requests) == 2 and len(first.posts) == 20
    assert xc.billed_posts == 20  # both queries returned the same posts: billed once

    async with x.XClient(xsettings, transport=t) as xc:  # within the cache window: free
        again = await x.search_posts(xc, queries, max_posts=40, cache_s=3600)
    assert xc.billed_posts == 0 and len(fake.requests) == 2 and len(again.posts) == 20
    assert all(q["from_cache"] for q in again.queries)

    fake.total = 55  # five new posts appear
    async with x.XClient(xsettings, transport=t) as xc:  # cache too old: ask only for newer posts
        later = await x.search_posts(xc, queries, max_posts=40, cache_s=0)
    assert all(r.get("since_id") == "1050" for r in fake.requests[2:]) and len(fake.requests) == 4
    assert xc.billed_posts == 5 and later.posts[0]["id"] == "1055"


async def test_authors_looked_up_once(xsettings):
    fake = FakeX()
    t = httpx.MockTransport(fake.handler)
    ids = [str(int(time.time() * 1000)), str(int(time.time() * 1000) + 1)]
    async with x.XClient(xsettings, transport=t) as xc:
        users = await x.resolve_authors(xc, ids)
    assert users[ids[0]]["username"] == f"user{ids[0]}" and xc.billed_users == 2
    async with x.XClient(xsettings, transport=t) as xc:
        await x.resolve_authors(xc, ids)
    assert xc.billed_users == 0


def test_posts_become_a_dataset():
    found = x.XSearch(posts=[
        {"id": "11", "text": "@a @b کسی دوره پایتون سراغ داره؟ &amp; ممنون", "author_id": "7", "created_at": _iso(5), "reply_to": "10"},
        {"id": "10", "text": "دنبال دوره پایتونم", "author_id": "8", "created_at": _iso(9), "reply_to": None},
    ], users={"8": {"username": "ali", "name": "علی"}})
    parsed = x.to_parsed(found, "ایکس: تست")
    a, b = parsed.messages
    assert (a.ext_id, b.ext_id) == ("10", "11") and b.reply_to == a.id
    assert b.text == "کسی دوره پایتون سراغ داره؟ & ممنون"
    assert a.author == "علی (@ali)" and b.author.startswith("کاربر ایکس")
    assert b.author_id == "x:7" and parsed.source == "twitter"
    assert x.post_url("11") == "https://x.com/i/status/11" and x.post_url(None) is None


# --- API ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        r = c.post("/api/auth/signup", json={"email": "links@example.com", "password": "correct-horse-1"})
        assert r.status_code == 200, r.text
        yield c


def test_product_from_link(client, monkeypatch):
    from app.api import products

    async def fake_fetch(url):
        return web.parse_html("https://example.com/python", PAGE.replace("۱۱۰ درسنامه", "۱۱۰ درسنامه " * 60))

    async def fake_read(llm, settings, page):
        return ProductFacts(found=True, product_name="دوره پایتون", seller="سایت", summary="پایتون از صفر.",
                            audience="تازه‌کارها", price="۳,۴۹۹,۰۰۰ تومان", features=["۱۱۰ درسنامه", "گواهی پایان دوره"]), None

    monkeypatch.setattr(products, "fetch_page", fake_fetch)
    monkeypatch.setattr(products, "read_product", fake_read)
    r = client.post("/api/products/from-url", json={"url": "example.com/python"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["name"] == "دوره پایتون" and p["source"]["url"] == "https://example.com/python"
    assert "قیمت: ۳,۴۹۹,۰۰۰ تومان" in p["description"] and p["setup_chat"][0]["content"] == p["description"]

    async def empty_fetch(url):
        return web.parse_html("https://example.com/spa", "<html><body><div id=root></div></body></html>")

    monkeypatch.setattr(products, "fetch_page", empty_fetch)
    r = client.post("/api/products/from-url", json={"url": "https://example.com/spa"})
    assert r.status_code == 422 and "توضیح" in r.json()["detail"]


def test_twitter_dataset(client, monkeypatch, xsettings):
    from app.api import datasets
    from app.samples import sample_profile

    r = client.post("/api/products/sample/quera_python")
    pid = r.json()["id"]

    monkeypatch.setattr(xsettings, "x_bearer_token", "")
    r = client.post("/api/datasets/twitter", json={"product_id": pid})
    assert r.status_code == 400 and "توکن" in r.json()["detail"]
    monkeypatch.setattr(xsettings, "x_bearer_token", "test-token")

    async def fake_plan(llm, settings, profile):
        return _plan("پایتون"), None

    fake = FakeX(total=40)
    monkeypatch.setattr(datasets, "plan_queries", fake_plan)
    monkeypatch.setattr(datasets, "make_x_client", lambda s: x.XClient(s, transport=httpx.MockTransport(fake.handler)))
    assert sample_profile("quera_python")
    r = client.post("/api/datasets/twitter", json={"product_id": pid, "max_posts": 30})
    assert r.status_code == 200, r.text
    ds = r.json()
    assert ds["source"] == "twitter" and ds["stats"]["messages"] == 30
    assert ds["stats"]["x"]["new_posts"] == 30 and ds["stats"]["x"]["cost_usd"] == pytest.approx(0.15)
    msgs = client.get(f"/api/datasets/{ds['id']}/messages").json()["messages"]
    assert msgs[0]["url"].startswith("https://x.com/i/status/")
    assert json.dumps(client.get("/api/config").json()["x"])


# --- twitterapi.io --------------------------------------------------------------------------------


def _tw_date(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%a %b %d %H:%M:%S +0000 %Y")


class FakeTapi:
    """twitterapi.io advanced search: 20 tweets a page, newest first, author inside each tweet."""

    def __init__(self, total=50, throttle_first=0):
        self.total = total
        self.throttle = throttle_first
        self.requests: list[dict] = []
        self.t0 = int(time.time()) - 200 * 60  # tweet 5000+k was posted k minutes after t0

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "tapi-key"
        assert request.url.path == "/twitter/tweet/advanced_search"
        q = dict(request.url.params)
        self.requests.append(q)
        if self.throttle:
            self.throttle -= 1
            return httpx.Response(429, json={"error": 429, "message": "Too many requests"})
        since = int(q["query"].rsplit("since_time:", 1)[1])
        ids = [i for i in range(5000 + self.total, 5000, -1)]
        made = {i: self.t0 + (i - 5000) * 60 for i in ids}
        ids = [i for i in ids if made[i] >= since]
        start = int(q["cursor"] or 0)
        page = ids[start : start + 20]
        tweets = [{
            "type": "tweet", "id": str(i), "url": f"https://x.com/u/status/{i}", "text": f"کسی دوره پایتون سراغ داره؟ {i}",
            "createdAt": datetime.fromtimestamp(made[i], timezone.utc).strftime("%a %b %d %H:%M:%S +0000 %Y"),
            "lang": "fa", "isReply": i % 4 == 0, "inReplyToId": str(i - 1) if i % 4 == 0 else "",
            "author": {"type": "user", "id": str(i % 6), "userName": f"user{i % 6}", "name": f"نام {i % 6}"},
            "retweeted_tweet": None,
        } for i in page]
        more = start + 20 < len(ids)
        return httpx.Response(200, json={"tweets": tweets, "has_next_page": more, "next_cursor": str(start + 20) if more else ""})


@pytest.fixture
def tapi(monkeypatch, xsettings):
    monkeypatch.setattr(xsettings, "twitterapi_key", "tapi-key")
    return xsettings


def test_provider_choice(tapi, monkeypatch):
    assert tapi.x_source() == "twitterapi" and tapi.x_price_per_post() == pytest.approx(0.00015)
    assert isinstance(x.make_x_client(tapi), x.TwitterApiIo)
    monkeypatch.setattr(tapi, "twitterapi_key", "")
    assert tapi.x_source() == "official" and isinstance(x.make_x_client(tapi), x.XClient)
    monkeypatch.setattr(tapi, "x_bearer_token", "")
    assert tapi.x_source() is None
    with pytest.raises(x.XError):
        x.make_x_client(tapi)


async def test_twitterapi_search_pages_and_bills_per_tweet(tapi):
    fake = FakeTapi(total=100, throttle_first=1)
    async with x.TwitterApiIo(tapi, transport=httpx.MockTransport(fake.handler)) as xc:
        posts, _ = await xc.search('(پایتون) lang:fa -filter:retweets', limit=50)
    assert len(posts) == 40 and xc.billed_posts == 40  # two pages of 20; a third would pass the limit
    assert len(fake.requests) == 3  # the first was throttled and retried
    assert fake.requests[-1]["queryType"] == "Latest" and "since_time:" in fake.requests[-1]["query"]
    p = posts[0]
    assert p["id"] == "5100" and p["username"] == "user0" and p["created_at"].endswith("Z")
    assert xc.cost_usd == pytest.approx(40 * 0.00015)


async def test_twitterapi_cache_and_newer_only(tapi):
    fake = FakeTapi(total=30)
    t = httpx.MockTransport(fake.handler)
    plan = _plan("پایتون")
    async with x.make_x_client(tapi, transport=t) as xc:
        first = await x.search_posts(xc, plan, max_posts=100, cache_s=3600)
    assert len(first.posts) == 30 and xc.billed_posts == 30
    assert "-filter:retweets" in first.queries[0]["q"]

    fake.total = 33  # three new tweets
    async with x.make_x_client(tapi, transport=t) as xc:
        later = await x.search_posts(xc, plan, max_posts=100, cache_s=0)
    assert xc.billed_posts == 3 and len(later.posts) == 33

    parsed = x.to_parsed(later, "ایکس")
    assert parsed.messages[-1].author == "نام 5 (@user5)"  # tweet 5033; names come with the tweets
    assert any(m.reply_to for m in parsed.messages)


async def test_twitterapi_errors_are_persian(tapi):
    t = httpx.MockTransport(lambda r: httpx.Response(402, json={"error": 402, "message": "Credits not enough"}))
    async with x.TwitterApiIo(tapi, transport=t) as xc:
        with pytest.raises(x.XError, match="اعتبار"):
            await xc.search("q", limit=20)
    t = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": 401, "message": "Unauthorized"}))
    async with x.TwitterApiIo(tapi, transport=t) as xc:
        with pytest.raises(x.XError, match="کلید"):
            await xc.search("q", limit=20)


async def test_twitterapi_never_passes_max_posts(tapi):
    fake = FakeTapi(total=200)
    async with x.make_x_client(tapi, transport=httpx.MockTransport(fake.handler)) as xc:
        found = await x.search_posts(xc, _plan("a", "b", "c", "d"), max_posts=50, cache_s=3600)
    assert xc.billed_posts <= 50 and [q["new"] for q in found.queries] == [20, 20, 0, 0]


# --- twscrape -------------------------------------------------------------------------------------

from types import SimpleNamespace


def _tws_tweet(i: int, minutes_ago: int, retweet: bool = False, reply_to: int | None = None):
    user = SimpleNamespace(id=i % 5, id_str=str(i % 5), username=f"acc{i % 5}", displayname=f"حساب {i % 5}")
    return SimpleNamespace(
        id=i, id_str=str(i), rawContent=f"کسی دوره پایتون سراغ داره؟ {i}", user=user,
        date=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        retweetedTweet=object() if retweet else None, inReplyToTweetIdStr=str(reply_to) if reply_to else None,
    )


class FakeTwscrapeApi:
    def __init__(self, tweets=None, error: Exception | None = None):
        self.tweets = tweets or []
        self.error = error
        self.queries: list[str] = []

    async def search(self, q, limit=-1):
        self.queries.append(q)
        if self.error:
            raise self.error
        for t in self.tweets:
            yield t


@pytest.fixture
def tws(monkeypatch, xsettings):
    monkeypatch.setattr(xsettings, "twscrape_cookies", "auth_token=a; ct0=b")
    monkeypatch.setattr(x.Twscrape, "pause_s", 0)
    return xsettings


def test_twscrape_is_free_and_chosen_by_setting(tws, monkeypatch):
    assert tws.x_source() == "twscrape" and tws.x_price_per_post() == 0
    assert isinstance(x.make_x_client(tws), x.Twscrape)
    monkeypatch.setattr(tws, "twitterapi_key", "tapi-key")
    assert tws.x_source() == "twitterapi"  # auto: twitterapi.io first
    monkeypatch.setattr(tws, "x_provider", "twscrape")
    assert tws.x_source() == "twscrape"
    monkeypatch.setattr(tws, "twscrape_cookies", "")
    assert tws.x_source() is None  # chosen explicitly but not configured


async def test_twscrape_search(tws):
    api = FakeTwscrapeApi([_tws_tweet(9003, 1), _tws_tweet(9002, 2, retweet=True), _tws_tweet(9001, 3, reply_to=9000)])
    found = await x.search_posts(x.Twscrape(tws, api=api), _plan("پایتون"), max_posts=100, cache_s=3600)
    assert [p["id"] for p in found.posts] == ["9003", "9001"]  # the retweet is dropped
    assert "since_time:" in api.queries[0] and "-filter:retweets" in api.queries[0]
    assert found.queries[0]["new"] == 2
    parsed = x.to_parsed(found, "ایکس")
    assert parsed.messages[-1].author == "حساب 3 (@acc3)" and parsed.messages[0].ext_id == "9001"


async def test_twscrape_errors_are_persian(tws):
    from twscrape.accounts_pool import NoAccountError

    for err, word in [(NoAccountError("none"), "کوکی"), (RuntimeError("x changed"), "twscrape")]:
        xc = x.Twscrape(tws, api=FakeTwscrapeApi(error=err))
        with pytest.raises(x.XError, match=word):
            await xc.search("q", limit=20)


async def test_twscrape_account_from_cookies(tws, monkeypatch, tmp_path):
    monkeypatch.setattr(tws, "data_dir", tmp_path)
    monkeypatch.setattr(x, "_tws", {})
    api = await x._twscrape_api(tws)  # offline: only writes the account to its own sqlite file
    info = await api.pool.accounts_info()
    assert [a["username"] for a in info] == [x.TWSCRAPE_ACCOUNT] and info[0]["active"]
    assert await x._twscrape_api(tws) is api  # same cookies: reused
    await api.pool.mark_inactive(x.TWSCRAPE_ACCOUNT, "Logged-out X web app")  # what twscrape does on an error
    await x._twscrape_api(tws, refresh=True)  # a new search turns it back on
    assert (await api.pool.accounts_info())[0]["active"]
    monkeypatch.setattr(tws, "twscrape_cookies", "just-garbage")
    with pytest.raises(x.XError, match="auth_token"):
        await x._twscrape_api(tws)
