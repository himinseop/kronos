from __future__ import annotations

import httpx
import respx
from kronos.collectors import rss
from kronos.collectors.run import collect_rss

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>Sample</description>
    <item>
      <title><![CDATA[삼성전자, 사상최대 실적]]></title>
      <link>https://example.com/article/1</link>
      <description><![CDATA[<p>삼성전자가 ...</p>]]></description>
      <pubDate>Tue, 19 May 2026 09:00:00 +0900</pubDate>
    </item>
    <item>
      <title>SK하이닉스 신규 투자</title>
      <link>https://example.com/article/2</link>
      <description>본문</description>
      <pubDate>Tue, 19 May 2026 10:00:00 +0900</pubDate>
    </item>
  </channel>
</rss>
"""


@respx.mock
def test_fetch_feed_parses_items():
    respx.get("https://example.com/feed.xml").mock(
        return_value=httpx.Response(200, content=SAMPLE_RSS.encode("utf-8"))
    )
    result = rss.fetch_feed("https://example.com/feed.xml")
    assert result.error is None
    assert len(result.articles) == 2
    a = result.articles[0]
    assert a.title == "삼성전자, 사상최대 실적"
    assert a.url == "https://example.com/article/1"
    assert a.body and a.body.startswith("삼성전자")  # <p> 태그 제거됨
    assert a.publisher == "example.com"


@respx.mock
def test_fetch_feed_http_error():
    respx.get("https://example.com/bad.xml").mock(return_value=httpx.Response(500))
    result = rss.fetch_feed("https://example.com/bad.xml")
    assert result.error is not None
    assert result.articles == []


@respx.mock
def test_collect_rss_continues_past_bad_feed(tmp_path):
    respx.get("https://good.example.com/feed.xml").mock(
        return_value=httpx.Response(200, content=SAMPLE_RSS.encode("utf-8"))
    )
    respx.get("https://bad.example.com/feed.xml").mock(return_value=httpx.Response(502))

    db = tmp_path / "kronos.db"
    stats = collect_rss(
        db,
        ["https://good.example.com/feed.xml", "https://bad.example.com/feed.xml"],
    )
    assert stats.fetched == 2
    assert stats.inserted == 2
    assert stats.duplicates == 0

    import sqlite3

    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT COUNT(*) FROM news WHERE source='rss'").fetchone()[0]
    assert rows == 2
    # 실패한 피드가 있으므로 run.ok=0, error 컬럼에 메시지가 기록
    run = conn.execute("SELECT ok, error FROM collector_runs WHERE source='rss'").fetchone()
    assert run[0] == 0
    assert "bad.example.com" in (run[1] or "")
    conn.close()
