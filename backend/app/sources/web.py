"""Read a product page the user links to: public http(s) addresses only, small and quick, cached a day.

Every connection (redirects included) is checked at connect time, so a link cannot reach the
server's own network (localhost, private ranges, cloud metadata) even through DNS tricks.

Many Iranian shops build their pages in the browser, so the HTML alone can be empty:
- data the page embeds for its own scripts (Next.js __NEXT_DATA__, preloaded state) is read too;
- Digikala and Snappshop pages are read from the same public product API their pages call.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urlsplit

import httpcore
import httpx

from ..agents.context import cache_get_fresh, cache_key, cache_set

MAX_BYTES = 3_000_000
MAX_TEXT = 12_000  # characters of visible text kept for the extractor
MAX_EMBEDDED = 7_000  # characters of the page's own data kept when the visible text is thin
THIN_TEXT = 2_000  # below this much visible text, the page's own data is read too
TIMEOUT_S = 15.0
PAGE_TTL_S = 24 * 3600
USER_AGENT = "Mozilla/5.0 (compatible; Sarenakh/1.0; product page reader)"


class PageError(Exception):
    """Raised with a Persian, user-facing message."""


BOT_CHECK = ("این سایت جلوی خواندن خودکار را گرفته (از ما می‌خواهد ثابت کنیم ربات نیستیم). "
             "محصول را چند خطی توضیح دهید یا لینک همین محصول را از فروشگاه دیگری بدهید.")


# --- safe connections ---------------------------------------------------------------------------


def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def _public_ip(host: str, port: int) -> str:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise httpx.ConnectError(f"cannot resolve {host}") from e
    ips = [info[4][0] for info in infos]
    if not ips or not all(_is_public(ip) for ip in ips):
        raise BlockedAddress(host)
    return ips[0]


class BlockedAddress(httpx.ConnectError):
    def __init__(self, host: str):
        super().__init__(f"{host} is not a public address")


class _PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """Resolves the host itself and connects only to public IPs (TLS still verifies the hostname)."""

    def __init__(self) -> None:
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        ip = await _public_ip(host, port)
        return await self._inner.connect_tcp(ip, port, timeout=timeout, local_address=local_address,
                                             socket_options=socket_options)

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise BlockedAddress(path)

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class _SafeTransport(httpx.AsyncHTTPTransport):
    def __init__(self) -> None:
        super().__init__(trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(), max_connections=4, network_backend=_PublicOnlyBackend(),
        )


def check_url(url: str) -> str:
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or "." not in parts.hostname:
        raise PageError("لینک معتبر نیست. آدرس کامل صفحه محصول را بدهید.")
    if parts.username or parts.password:
        raise PageError("لینک نباید نام کاربری یا رمز داشته باشد.")
    return url


# --- HTML to text -------------------------------------------------------------------------------

_SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
          "section", "article", "header", "footer", "table", "dd", "dt", "nav", "main", "aside", "form",
          "figure", "figcaption", "blockquote", "pre", "dl"}
_SPACED = {"a", "button", "label", "option"}  # menus put these side by side with no whitespace


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self.parts: list[str] = []
        self._skip = 0
        self._in_title = False
        self._in_jsonld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            name = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if name and a.get("content"):
                self.meta.setdefault(name, a["content"].strip())
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in_jsonld, self._buf = True, []
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
        elif tag in _SPACED:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._in_jsonld:
            self.jsonld.append("".join(self._buf))
            self._in_jsonld = False
        if tag in _SKIP and self._skip:
            self._skip -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")
        elif tag in _SPACED:
            self.parts.append(" ")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_jsonld:
            self._buf.append(data)
        elif not self._skip:
            self.parts.append(data)


def _walk_jsonld(node: Any, out: list[dict]) -> None:
    if isinstance(node, list):
        for n in node:
            _walk_jsonld(n, out)
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(k in ("Product", "Course", "SoftwareApplication", "Service", "Book", "Offer") for k in kinds):
            out.append(node)
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                _walk_jsonld(node[key], out)


def _trim(node: Any, depth: int = 0) -> Any:
    """Keep structured data small: drop images/urls/reviews and deep nesting."""
    if depth > 4:
        return None
    if isinstance(node, dict):
        return {k: _trim(v, depth + 1) for k, v in node.items()
                if k not in ("image", "@context", "review", "url", "logo", "sameAs", "potentialAction")}
    if isinstance(node, list):
        return [_trim(v, depth + 1) for v in node[:12]]
    if isinstance(node, str):
        return node[:600]
    return node


@dataclass
class Page:
    url: str
    title: str = ""
    description: str = ""
    text: str = ""
    structured: list[dict] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    embedded: str = ""  # the site's own data as "key: value" lines (embedded JSON or its product API)

    @property
    def readable(self) -> bool:
        return len(self.text) >= 200 or bool(self.structured) or len(self.embedded) >= 80

    def for_model(self) -> str:
        parts = [f"URL: {self.url}", f"TITLE: {self.title}"]
        if self.description:
            parts.append(f"META DESCRIPTION: {self.description}")
        if self.meta:
            parts.append("META: " + json.dumps(self.meta, ensure_ascii=False))
        if self.structured:
            parts.append("STRUCTURED DATA (JSON-LD): " + json.dumps(self.structured, ensure_ascii=False)[:5000])
        if self.embedded:
            parts.append("SITE DATA (key: value):\n" + self.embedded)
        parts.append("VISIBLE TEXT:\n" + self.text)
        return "\n\n".join(parts)


# --- data the page embeds for its own scripts ---------------------------------------------------

_NUXT = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)
_STATE = [
    re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S),
    re.compile(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S),
    re.compile(r"window\.(?:__PRELOADED_STATE__|__INITIAL_STATE__|__APOLLO_STATE__|__STATE__)\s*=\s*(\{.*?\})\s*;?\s*</script>",
               re.S),
]
_NOISE_KEY = re.compile(r"(url|href|src|image|img|icon|logo|slug|token|hash|color|css|class|uuid|typename|cookie|"
                        r"script|style|seo|tracking|analytics|banner|menu|footer|header|navigation|locale|lang)", re.I)
_USEFUL_KEY = re.compile(r"(title|name|desc|price|spec|attr|feature|value|summary|detail|content|review|warranty|"
                         r"brand|category|weight|size|duration|teacher|author|stock|discount|text)", re.I)
_PERSIAN = re.compile(r"[\u0600-\u06FF]")


def _leaf(v: Any) -> str | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return str(v)
    if not isinstance(v, str):
        return None
    v = " ".join(re.sub(r"<[^>]+>", " ", v).split())
    if not 2 <= len(v) <= 600 or v.startswith(("http", "/", "#", "{", "data:")) or not (_PERSIAN.search(v) or re.search(r"\d", v)):
        return None
    return v


def _flatten(node: Any, key: str, out: list[tuple[bool, str]], seen: set[str], depth: int = 0) -> None:
    if depth > 14 or len(out) > 3000:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and len(k) <= 40 and (k in ("id", "key", "_id") or _NOISE_KEY.search(k)):
                continue
            _flatten(v, str(k), out, seen, depth + 1)
    elif isinstance(node, list):
        for v in node[:40]:
            _flatten(v, key, out, seen, depth + 1)
    elif (v := _leaf(node)) is not None:
        if isinstance(node, (int, float)) and not _USEFUL_KEY.search(key):
            return  # bare numbers are only worth keeping under telling keys (price, weight...)
        line = f"{key}: {v}"
        if v not in seen:
            seen.add(v)
            out.append((bool(_USEFUL_KEY.search(key)), line))


def json_lines(data: Any, limit: int = MAX_EMBEDDED) -> str:
    """The meaningful leaves of a JSON document as "key: value" lines, telling keys first."""
    found: list[tuple[bool, str]] = []
    _flatten(data, "", found, set())
    lines = [ln for useful, ln in found if useful] + [ln for useful, ln in found if not useful]
    out, size = [], 0
    for ln in lines:
        if size + len(ln) + 1 > limit:
            break
        out.append(ln)
        size += len(ln) + 1
    return "\n".join(out)


_NUXT_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef", "Set", "Map"}


def nuxt_payload(arr: list) -> Any:
    """Nuxt 3 sends page data as a flat array where numbers inside objects and lists point at other
    entries (the devalue format). Rebuild the nested data."""
    memo: dict[int, Any] = {}

    def at(i: Any, depth: int = 0) -> Any:
        if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(arr) or depth > 40:
            return None
        if i in memo:
            return memo[i]
        v = arr[i]
        memo[i] = None  # cycles resolve to None
        if isinstance(v, dict):
            out: Any = {k: at(x, depth + 1) for k, x in v.items()}
        elif isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in _NUXT_WRAPPERS:
                out = at(v[1], depth + 1) if len(v) > 1 else None
            else:
                out = [at(x, depth + 1) for x in v]
        else:
            out = v
        memo[i] = out
        return out

    return at(0)


def embedded_text(html: str) -> str:
    blobs = []
    for m in _NUXT.finditer(html):
        try:
            data = json.loads(m.group(1))
            blobs.append(nuxt_payload(data) if isinstance(data, list) else data)
        except (json.JSONDecodeError, ValueError, RecursionError):
            continue
    for rx in _STATE:
        for m in rx.finditer(html):
            try:
                blobs.append(json.loads(m.group(1)))
            except (json.JSONDecodeError, ValueError):
                continue
    return json_lines(blobs) if blobs else ""


_KEEP_META = ("og:title", "og:description", "og:site_name", "og:type", "product:price:amount",
              "product:price:currency", "og:price:amount", "price", "pricecurrency", "keywords")


def parse_html(url: str, html: str) -> Page:
    r = _Reader()
    try:
        r.feed(html)
        r.close()
    except Exception:  # noqa: BLE001 — keep whatever was read before broken markup
        pass
    found: list[dict] = []
    for raw in r.jsonld:
        try:
            _walk_jsonld(json.loads(raw), found)
        except (json.JSONDecodeError, ValueError):
            continue
    text = "".join(r.parts)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.split("\n")]
    seen: set[str] = set()
    kept = []
    for ln in lines:  # drop empty and repeated lines (menus, footers repeat a lot)
        if len(ln) < 2 or ln in seen:
            continue
        seen.add(ln)
        kept.append(ln)
    body = "\n".join(kept)
    return Page(
        url=url,
        title=" ".join(r.title.split())[:300],
        description=(r.meta.get("description") or r.meta.get("og:description") or "")[:1000],
        text=body[:MAX_TEXT],
        structured=[_trim(n) for n in found[:3]],
        meta={k: r.meta[k][:300] for k in _KEEP_META if k in r.meta},
        embedded=embedded_text(html) if len(body) < THIN_TEXT else "",
    )


# --- fetch (cached) -----------------------------------------------------------------------------


async def _download(url: str, transport: httpx.AsyncBaseTransport | None = None, *,
                    want_json: bool = False) -> tuple[str, str]:
    """Returns (final_url, body)."""
    accept = "application/json" if want_json else "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"
    async with httpx.AsyncClient(
        transport=transport or _SafeTransport(), follow_redirects=True, max_redirects=4, timeout=TIMEOUT_S,
        headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "fa,en;q=0.8"},
    ) as client:
        try:
            async with client.stream("GET", url) as resp:
                if resp.status_code in (403, 429, 490):
                    raise PageError(BOT_CHECK)
                if resp.status_code >= 400:
                    raise PageError(f"سایت صفحه را نداد (کد {resp.status_code}). لینک را چک کنید یا محصول را توضیح دهید.")
                ctype = resp.headers.get("content-type", "").lower()
                allowed = ("json",) if want_json else ("html", "xml", "text/plain")
                if ctype and not any(t in ctype for t in allowed):
                    raise PageError("این لینک صفحه وب نیست. لینک صفحه محصول را بدهید.")
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks)
                enc = resp.charset_encoding or "utf-8"
                return str(resp.url), raw.decode(enc, errors="replace")
        except BlockedAddress as e:
            raise PageError("این آدرس عمومی نیست و خوانده نمی‌شود.") from e
        except httpx.TooManyRedirects as e:
            raise PageError("لینک بیش از حد ریدایرکت می‌شود.") from e
        except httpx.TimeoutException as e:
            raise PageError("سایت دیر جواب داد. دوباره امتحان کنید یا محصول را توضیح دهید.") from e
        except httpx.HTTPError as e:
            raise PageError("به سایت وصل نشدیم. لینک را چک کنید یا محصول را توضیح دهید.") from e


# --- shops whose pages are built in the browser: read their public product API -------------------


def _toman(rial: Any) -> str:
    try:
        return f"{int(rial) // 10:,} تومان"
    except (TypeError, ValueError):
        return ""


def _digikala(p: dict) -> list[str]:
    lines = [f"نام: {p.get('title_fa', '')}" + (f" ({p['title_en']})" if p.get("title_en") else "")]
    if (b := (p.get("brand") or {}).get("title_fa")):
        lines.append(f"برند: {b}")
    if (c := (p.get("category") or {}).get("title_fa")):
        lines.append(f"دسته: {c}")
    variant = p.get("default_variant") if isinstance(p.get("default_variant"), dict) else {}
    price = variant.get("price") or {}
    if price.get("selling_price"):
        lines.append(f"قیمت: {_toman(price['selling_price'])}")
        if price.get("rrp_price") and price["rrp_price"] > price["selling_price"]:
            lines.append(f"قیمت قبل از تخفیف: {_toman(price['rrp_price'])} ({price.get('discount_percent', '')}٪ تخفیف)")
    elif p.get("status") and p["status"] != "marketable":
        lines.append("وضعیت: ناموجود")
    if (w := (variant.get("warranty") or {}).get("title_fa")):
        lines.append(f"گارانتی: {w}")
    if (r := p.get("rating")) and r.get("count"):
        lines.append(f"امتیاز خریداران: {round(r.get('rate', 0) / 20, 1)} از ۵ ({r['count']} رأی)")
    for group in p.get("specifications") or []:
        for a in group.get("attributes") or []:
            values = "، ".join(v.strip() for v in a.get("values") or [] if v.strip())
            if values:
                lines.append(f"{a.get('title', '')}: {values}")
    pc = p.get("pros_and_cons") or {}
    lines += [f"نقطه قوت: {x}" for x in pc.get("advantages") or []]
    lines += [f"نقطه ضعف: {x}" for x in pc.get("disadvantages") or []]
    review = (p.get("expert_reviews") or {}).get("description") or (p.get("review") or {}).get("description") or ""
    if review:
        lines.append("نقد و بررسی: " + " ".join(re.sub(r"<[^>]+>", " ", review).split())[:2500])
    return lines


def _snappshop(d: dict) -> list[str]:
    content = d.get("content") or {}
    lines = [f"نام: {content.get('title_fa', '')}"]
    if (b := (d.get("brand") or {}).get("title_fa")):
        lines.append(f"برند: {b}")
    cats = [c.get("title") for c in d.get("categories") or [] if c.get("title")]
    if len(cats) > 1:
        lines.append("دسته: " + " / ".join(cats[1:]))
    for ld in (d.get("page") or {}).get("json_ld") or []:
        offers = ld.get("offers") if isinstance(ld, dict) else None
        if isinstance(offers, dict) and offers.get("price"):
            cur = str(offers.get("priceCurrency", "")).upper()
            lines.append("قیمت: " + (_toman(offers["price"]) if cur == "IRR" else f"{offers['price']} {cur}".strip()))
            if "OutOfStock" in str(offers.get("availability", "")):
                lines.append("وضعیت: ناموجود")
    if not d.get("variants") and not any(ln.startswith("قیمت") for ln in lines):
        lines.append("وضعیت: ناموجود")
    lines += [f"{a.get('title', '')}: {a.get('value', '')}" for a in d.get("attributes") or [] if a.get("value")]
    if (desc := content.get("description")):
        lines.append("توضیحات: " + " ".join(re.sub(r"<[^>]+>", " ", desc).split())[:2500])
    return lines


# (host suffix, product id in the path, API url, unwrap the response, format it)
_SHOP_APIS = [
    ("digikala.com", re.compile(r"/product/dkp-(\d+)"), "https://api.digikala.com/v2/product/{}/",
     lambda j: j["data"]["product"], _digikala),
    ("digistyle.com", re.compile(r"/product/(?:dkp-)?(\d+)"), "https://api.digikala.com/v2/product/{}/",
     lambda j: j["data"]["product"], _digikala),  # Digistyle products live in Digikala's catalogue
    ("snappshop.ir", re.compile(r"/product/snp-(\d+)"), "https://apix.snappshop.ir/products/v2/{}",
     lambda j: j["data"], _snappshop),
]


async def _from_shop_api(url: str, transport: httpx.AsyncBaseTransport | None) -> Page | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    for suffix, path_re, api, unwrap, fmt in _SHOP_APIS:
        if not (host == suffix or host.endswith("." + suffix)):
            continue
        m = path_re.search(unquote(parts.path))
        if not m:
            return None
        try:
            _, body = await _download(api.format(m.group(1)), transport, want_json=True)
            lines = [ln for ln in fmt(unwrap(json.loads(body))) if ln.split(":", 1)[-1].strip()]
        except (PageError, KeyError, TypeError, ValueError):
            return None  # the API changed or refused: fall back to the HTML page
        title = lines[0].split(":", 1)[-1].strip() if lines else ""
        return Page(url=url, title=title, embedded="\n".join(lines)[:MAX_EMBEDDED])
    return None


_GENERIC_TITLE = re.compile(r"فروشگاه اینترنتی|صفحه اصلی|صفحه پیدا نشد|خطا|home ?page|not found|404", re.I)
_TITLE_PREFIX = re.compile(r"^(خرید و قیمت|قیمت و خرید|خرید اینترنتی|خرید آنلاین|مشخصات، قیمت و خرید|خرید)\s+")


def product_name_guess(page: Page) -> str:
    """When a page can't be read, its title or a Persian URL slug still names the product."""
    title = re.split(r"\s+[|\-–—]\s+", _TITLE_PREFIX.sub("", page.title.strip()))[0].strip()
    if len(title) >= 8 and not _GENERIC_TITLE.search(title):
        return title[:150]
    slug = unquote(urlsplit(page.url).path).rstrip("/").split("/")[-1]
    words = [w for w in re.split(r"[-_\s]+", slug) if w and not re.fullmatch(r"[a-z]{0,4}\d+", w, re.I)]
    return " ".join(words)[:150] if sum(bool(_PERSIAN.search(w)) for w in words) >= 2 else ""


async def fetch_page(url: str, *, transport: httpx.AsyncBaseTransport | None = None, use_cache: bool = True) -> Page:
    url = check_url(url)
    key = cache_key("page", url)
    if use_cache and (hit := cache_get_fresh(key, PAGE_TTL_S)):
        return Page(**hit)
    page = await _from_shop_api(url, transport)
    if page is None or not page.readable:
        final_url, html = await _download(url, transport)
        page = parse_html(final_url, html)
        if re.search(r"captcha|ربات هستید|are you a robot|access denied", f"{page.title}\n{page.text[:300]}", re.I):
            raise PageError(BOT_CHECK)  # not cached: the block may lift
    cache_set(key, "page", asdict(page))
    return page
