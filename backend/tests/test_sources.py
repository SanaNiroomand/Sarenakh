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
    monkeypatch.setattr(x.XClient, "variant", 0)
    return s


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
    queries = [{"q": f"(تست{time.time()}) lang:fa", "why": "a"}, {"q": f"(دوم{time.time()}) lang:fa", "why": "b"}]
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
    assert all(r.get("since_id") == "1050" for r in fake.requests[2:])
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
        return [{"q": f"(پایتون{time.time()}) lang:fa -is:retweet", "why": "تست"}], None

    fake = FakeX(total=40)

    class TestClientX(x.XClient):
        def __init__(self, settings):
            super().__init__(settings, transport=httpx.MockTransport(fake.handler))

    monkeypatch.setattr(datasets, "plan_queries", fake_plan)
    monkeypatch.setattr(datasets, "XClient", TestClientX)
    assert sample_profile("quera_python")
    r = client.post("/api/datasets/twitter", json={"product_id": pid, "max_posts": 30})
    assert r.status_code == 200, r.text
    ds = r.json()
    assert ds["source"] == "twitter" and ds["stats"]["messages"] == 30
    assert ds["stats"]["x"]["new_posts"] == 30 and ds["stats"]["x"]["cost_usd"] == pytest.approx(0.15)
    msgs = client.get(f"/api/datasets/{ds['id']}/messages").json()["messages"]
    assert msgs[0]["url"].startswith("https://x.com/i/status/")
    assert json.dumps(client.get("/api/config").json()["x"])
