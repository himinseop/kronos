from dataclasses import dataclass

import httpx

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


@dataclass
class NaverPingResult:
    ok: bool
    status_code: int | None
    message: str


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
