from __future__ import annotations

from datetime import date

import httpx
import respx
from kronos.collectors import dart
from kronos.collectors.run import collect_dart


def _sample_response(*, list_, total_page=1, page_no=1):
    return {
        "status": "000",
        "message": "정상",
        "page_no": page_no,
        "page_count": len(list_),
        "total_count": sum(1 for _ in list_),
        "total_page": total_page,
        "list": list_,
    }


def _sample_row(rcept_no: str, stock_code: str = "005930"):
    return {
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "stock_code": stock_code,
        "corp_cls": "Y",
        "report_nm": "주요사항보고서(자기주식취득결정)",
        "rcept_no": rcept_no,
        "flr_nm": "삼성전자",
        "rcept_dt": "20260519",
        "rm": "",
        "pblntf_ty": "A",
        "pblntf_detail_ty": "A001",
    }


@respx.mock
def test_iter_disclosures_paginates_and_parses():
    page1 = _sample_response(
        list_=[_sample_row("20260519000001"), _sample_row("20260519000002", stock_code="000660")],
        total_page=2,
        page_no=1,
    )
    page2 = _sample_response(
        list_=[
            {
                "corp_code": "00401731",
                "corp_name": "비상장사",
                "stock_code": "",
                "corp_cls": "N",
                "report_nm": "감사보고서",
                "rcept_no": "20260519000003",
                "flr_nm": "감사인",
                "rcept_dt": "20260519",
                "rm": "",
                "pblntf_ty": "B",
                "pblntf_detail_ty": "B001",
            }
        ],
        total_page=2,
        page_no=2,
    )
    route = respx.get("https://opendart.fss.or.kr/api/list.json")
    route.side_effect = [httpx.Response(200, json=page1), httpx.Response(200, json=page2)]

    items = list(
        dart.iter_disclosures(
            "key",
            bgn_de=date(2026, 5, 19),
            end_de=date(2026, 5, 19),
            page_count=2,
        )
    )

    assert len(items) == 3
    assert items[0].rcept_no == "20260519000001"
    assert items[0].ticker == "005930"
    assert items[2].ticker is None
    assert items[2].source_url is not None and items[2].source_url.endswith("rcpNo=20260519000003")


@respx.mock
def test_iter_disclosures_empty_returns_nothing():
    respx.get("https://opendart.fss.or.kr/api/list.json").mock(
        return_value=httpx.Response(
            200, json={"status": "013", "message": "조회된 데이터가 없습니다."}
        )
    )
    items = list(dart.iter_disclosures("key", bgn_de=date(2026, 5, 19), end_de=date(2026, 5, 19)))
    assert items == []


@respx.mock
def test_collect_dart_persists_and_dedupes(db_conn, test_dsn):
    response = _sample_response(list_=[_sample_row("20260519000001")])
    respx.get("https://opendart.fss.or.kr/api/list.json").mock(
        return_value=httpx.Response(200, json=response)
    )

    bgn = end = date(2026, 5, 19)

    first = collect_dart("key", bgn_de=bgn, end_de=end, dsn=test_dsn)
    assert first.fetched == 1
    assert first.inserted == 1
    assert first.duplicates == 0

    # 두 번째 호출: 같은 rcept_no라 모두 중복으로 처리되어야 함
    second = collect_dart("key", bgn_de=bgn, end_de=end, dsn=test_dsn)
    assert second.inserted == 0
    assert second.duplicates == 1

    assert db_conn.execute("SELECT COUNT(*) AS n FROM disclosures").fetchone()["n"] == 1

    runs = db_conn.execute(
        "SELECT source, ok, fetched, inserted, duplicates FROM collector_runs ORDER BY id"
    ).fetchall()
    assert len(runs) == 2
    assert runs[0]["source"] == "dart"
    assert runs[0]["ok"] is True
    assert runs[1]["duplicates"] == 1  # second run all duplicates
