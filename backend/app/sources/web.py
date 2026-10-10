"""Read a product page the user links to: public http(s) addresses only, small and quick, cached a day.

Every connection (redirects included) is checked at connect time, so a link cannot reach the
server's own network (localhost, private ranges, cloud metadata) even through DNS tricks.
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
from urllib.parse import urlsplit

import httpcore
import httpx

from ..agents.context import cache_get_fresh, cache_key, cache_set

MAX_BYTES = 3_000_000
MAX_TEXT = 12_000  # characters of visible text kept for the extractor
TIMEOUT_S = 15.0
PAGE_TTL_S = 24 * 3600
USER_AGENT = "Mozilla/5.0 (compatible; Sarenakh/1.0; product page reader)"


class PageError(Exception):
    """Raised with a Persian, user-facing message."""


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

    def for_model(self) -> str:
        parts = [f"URL: {self.url}", f"TITLE: {self.title}"]
        if self.description:
            parts.append(f"META DESCRIPTION: {self.description}")
        if self.meta:
            parts.append("META: " + json.dumps(self.meta, ensure_ascii=False))
        if self.structured:
            parts.append("STRUCTURED DATA (JSON-LD): " + json.dumps(self.structured, ensure_ascii=False)[:5000])
        parts.append("VISIBLE TEXT:\n" + self.text)
        return "\n\n".join(parts)


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
    )


# --- fetch (cached) -----------------------------------------------------------------------------


async def _download(url: str, transport: httpx.AsyncBaseTransport | None = None) -> tuple[str, str]:
    """Returns (final_url, html)."""
    async with httpx.AsyncClient(
        transport=transport or _SafeTransport(), follow_redirects=True, max_redirects=4, timeout=TIMEOUT_S,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                 "Accept-Language": "fa,en;q=0.8"},
    ) as client:
        try:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise PageError(f"سایت صفحه را نداد (کد {resp.status_code}). لینک را چک کنید یا محصول را توضیح دهید.")
                ctype = resp.headers.get("content-type", "").lower()
                if ctype and not any(t in ctype for t in ("html", "xml", "text/plain")):
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


async def fetch_page(url: str, *, transport: httpx.AsyncBaseTransport | None = None, use_cache: bool = True) -> Page:
    url = check_url(url)
    key = cache_key("page", url)
    if use_cache and (hit := cache_get_fresh(key, PAGE_TTL_S)):
        return Page(**hit)
    final_url, html = await _download(url, transport)
    page = parse_html(final_url, html)
    cache_set(key, "page", asdict(page))
    return page
