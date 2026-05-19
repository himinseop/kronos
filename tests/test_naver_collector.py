from __future__ import annotations

import httpx
import respx
from kronos.collectors import naver
from kronos.collectors.run import collect_naver

_SAMPLE = {
    "items": [
        {
            "title": "<b>삼성전자</b>, 사상최대 실적",
            "originallink": "https://hankyung.com/news/article/1",
            "link": "https://news.naver.com/main/read?aid=1",
            "description": "<b>삼성전자</b>가 사상 최대 실적을 기록...",
            "pubDate": "Tue, 19 May 2026 09:00:00 +0900",
        },
        {
            "title": "삼전 호실적!",
            "originallink": "https://hankyung.com/news/article/1",
            "link": "https://news.naver.com/main/read?aid=2",
            "description": "다른 기사",
            "pubDate": "Tue, 19 May 2026 10:00:00 +0900",
        },
    ]
}


@respx.mock
def test_search_strips_html_and_parses():
    respx.get("https://openapi.naver.com/v1/search/news.json").mock(
        return_value=httpx.Response(200, json=_SAMPLE)
    )
    items = naver.search("id", "secret", "삼성전자")
    assert len(items) == 2
    assert items[0].title == "삼성전자, 사상최대 실적"  # <b> 제거됨
    assert items[0].url == "https://hankyung.com/news/article/1"
    assert items[0].publisher == "hankyung.com"
    assert items[0].source == "naver"


@respx.mock
def test_collect_naver_persists_and_dedupes_on_rerun(tmp_path):
    respx.get("https://openapi.naver.com/v1/search/news.json").mock(
        return_value=httpx.Response(200, json=_SAMPLE)
    )
    db = tmp_path / "kronos.db"

    first = collect_naver(db, "id", "secret", ["삼성전자"])
    assert first.fetched == 2
    # 두 row는 제목이 달라 신규 등록됨
    assert first.inserted == 2
    assert first.duplicates == 0

    # 동일 질의 재호출 시 모두 중복
    second = collect_naver(db, "id", "secret", ["삼성전자"])
    assert second.inserted == 0
    assert second.duplicates == 2

    import sqlite3

    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    assert rows == 2
    conn.close()
