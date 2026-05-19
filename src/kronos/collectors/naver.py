from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape

import httpx

from kronos.storage.models import NewsArticle

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
SOURCE = "naver"

_TAG = re.compile(r"<[^>]+>")
_PUB_DOMAIN = re.compile(r"https?://(?:www\.)?([^/]+)")


@dataclass
class NaverPingResult:
    ok: bool
    status_code: int | None
    message: str


def _strip_html(text: str) -> str:
    return unescape(_TAG.sub("", text)).strip()


def _infer_publisher(originallink: str | None, link: str | None) -> str | None:
    for url in (originallink, link):
        if not url:
            continue
        m = _PUB_DOMAIN.search(url)
        if m:
            return m.group(1)
    return None


def ping(client_id: str, client_secret: str, *, timeout: float = 5.0) -> NaverPingResult:
    """검색 API를 1건만 호출해 자격증명이 유효한지 확인."""
    try:
        resp = httpx.get(
            NAVER_NEWS_URL,
            params={"query": "테스트", "display": 1},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return NaverPingResult(ok=False, status_code=None, message=str(exc))

    if resp.status_code == 200:
        return NaverPingResult(ok=True, status_code=200, message="OK")

    try:
        body = resp.json()
        err = body.get("errorMessage") or body.get("message") or resp.text
    except ValueError:
        err = resp.text
    return NaverPingResult(ok=False, status_code=resp.status_code, message=str(err))


def _row_to_news(row: dict) -> NewsArticle | None:
    title = _strip_html(row.get("title", ""))
    if not title:
        return None
    body = _strip_html(row.get("description", "")) or None
    url = row.get("originallink") or row.get("link") or None
    publisher = _infer_publisher(row.get("originallink"), row.get("link"))
    pub_raw = row.get("pubDate")
    try:
        published_at = parsedate_to_datetime(pub_raw) if pub_raw else datetime.now().astimezone()
    except (TypeError, ValueError):
        published_at = datetime.now().astimezone()

    return NewsArticle(
        source=SOURCE,
        title=title,
        body=body,
        publisher=publisher,
        url=url,
        published_at=published_at,
    )


def search(
    client_id: str,
    client_secret: str,
    query: str,
    *,
    display: int = 100,
    start: int = 1,
    sort: str = "date",
    timeout: float = 10.0,
    client: httpx.Client | None = None,
):
    """네이버 검색 API 1회 호출, NewsArticle iterable 반환."""
    owned = client is None
    c = client or httpx.Client(timeout=timeout)
    try:
        resp = c.get(
            NAVER_NEWS_URL,
            params={"query": query, "display": display, "start": start, "sort": sort},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
        )
        resp.raise_for_status()
        body = resp.json()
    finally:
        if owned:
            c.close()

    items = []
    for row in body.get("items", []):
        article = _row_to_news(row)
        if article is not None:
            items.append(article)
    return items
