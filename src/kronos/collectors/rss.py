from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from urllib.parse import urlparse

import feedparser
import httpx

from kronos.storage.models import NewsArticle

SOURCE = "rss"

_TAG = re.compile(r"<[^>]+>")

# 사용자가 별도 지정하지 않으면 사용할 기본 피드.
# 안정성 보장은 어렵지만, 한국 경제 뉴스의 대표적 RSS 출처.
DEFAULT_FEEDS: tuple[str, ...] = (
    "https://www.hankyung.com/feed/economy",
    "https://www.mk.co.kr/rss/30000001/",
    "https://www.yna.co.kr/rss/economy.xml",
)


@dataclass(slots=True)
class FeedResult:
    url: str
    articles: list[NewsArticle]
    error: str | None = None


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return unescape(_TAG.sub("", text)).strip() or None


def _publisher_from_url(url: str | None) -> str | None:
    if not url:
        return None
    netloc = urlparse(url).netloc
    return netloc.removeprefix("www.") or None


def _entry_to_article(entry: dict, feed_publisher: str | None) -> NewsArticle | None:
    title = _strip_html(entry.get("title"))
    if not title:
        return None
    url = entry.get("link") or None
    body = _strip_html(entry.get("summary") or entry.get("description"))
    publisher = feed_publisher or _publisher_from_url(url)

    pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if pub_struct is not None:
        published_at = datetime(*pub_struct[:6], tzinfo=UTC)
    else:
        published_at = datetime.now(UTC)

    return NewsArticle(
        source=SOURCE,
        title=title,
        body=body,
        publisher=publisher,
        url=url,
        published_at=published_at,
    )


def fetch_feed(
    url: str, *, timeout: float = 10.0, client: httpx.Client | None = None
) -> FeedResult:
    """단일 RSS 피드를 가져와 파싱."""
    owned = client is None
    c = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        resp = c.get(url, headers={"User-Agent": "kronos/0.1 (+local)"})
        resp.raise_for_status()
        raw = resp.content
    except httpx.HTTPError as exc:
        return FeedResult(url=url, articles=[], error=f"fetch: {exc!r}")
    finally:
        if owned:
            c.close()

    parsed = feedparser.parse(raw)
    feed_publisher = _publisher_from_url(url) or (parsed.feed.get("title") if parsed.feed else None)

    articles: list[NewsArticle] = []
    for entry in parsed.entries:
        article = _entry_to_article(entry, feed_publisher)
        if article is not None:
            articles.append(article)

    if not articles and parsed.bozo:
        return FeedResult(url=url, articles=[], error=f"parse: {parsed.bozo_exception!r}")
    return FeedResult(url=url, articles=articles)
