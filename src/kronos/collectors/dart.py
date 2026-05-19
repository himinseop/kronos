from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from kronos.storage.models import Disclosure

DART_BASE_URL = "https://opendart.fss.or.kr/api"
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


@dataclass
class DartPingResult:
    ok: bool
    status_code: int | None
    dart_status: str | None
    message: str


def ping(api_key: str, *, timeout: float = 5.0) -> DartPingResult:
    """공시 목록을 1건만 조회해 키가 유효한지 확인."""
    try:
        resp = httpx.get(
            f"{DART_BASE_URL}/list.json",
            params={"crtfc_key": api_key, "page_no": 1, "page_count": 1},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return DartPingResult(ok=False, status_code=None, dart_status=None, message=str(exc))

    if resp.status_code != 200:
        return DartPingResult(
            ok=False,
            status_code=resp.status_code,
            dart_status=None,
            message=f"HTTP {resp.status_code}",
        )

    try:
        body = resp.json()
    except ValueError:
        return DartPingResult(
            ok=False,
            status_code=resp.status_code,
            dart_status=None,
            message="응답이 JSON이 아님",
        )

    status = body.get("status")
    message = body.get("message", "")

    # "000" = 정상, "013" = 조회된 데이터 없음(키는 유효)
    ok = status in {"000", "013"}
    return DartPingResult(ok=ok, status_code=resp.status_code, dart_status=status, message=message)


def _parse_dart_dt(raw: str) -> datetime:
    """DART 'rcept_dt'는 'YYYYMMDD'. 한국 시간 09:00을 기본 시각으로 부여."""
    d = date.fromisoformat(f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}")
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=UTC)


def _row_to_disclosure(row: dict) -> Disclosure:
    rcept_no = row["rcept_no"]
    stock_code = row.get("stock_code") or None
    return Disclosure(
        rcept_no=rcept_no,
        corp_code=row.get("corp_code") or None,
        corp_name=row.get("corp_name") or None,
        ticker=stock_code if stock_code and stock_code.strip() else None,
        report_nm=row.get("report_nm", "").strip(),
        submitter=row.get("flr_nm") or None,
        rcept_dt=_parse_dart_dt(row["rcept_dt"]),
        source_url=DART_VIEWER_URL.format(rcept_no=rcept_no),
        pblntf_ty=row.get("pblntf_ty") or None,
        pblntf_detail_ty=row.get("pblntf_detail_ty") or None,
    )


def fetch_list(
    api_key: str,
    *,
    bgn_de: date,
    end_de: date,
    page_no: int = 1,
    page_count: int = 100,
    timeout: float = 10.0,
    client: httpx.Client | None = None,
) -> dict:
    """원본 DART list.json 응답 반환. 호출자가 페이지네이션·중복 처리."""
    params = {
        "crtfc_key": api_key,
        "bgn_de": bgn_de.strftime("%Y%m%d"),
        "end_de": end_de.strftime("%Y%m%d"),
        "page_no": page_no,
        "page_count": page_count,
    }
    owned = client is None
    c = client or httpx.Client(timeout=timeout)
    try:
        resp = c.get(f"{DART_BASE_URL}/list.json", params=params)
        resp.raise_for_status()
        return resp.json()
    finally:
        if owned:
            c.close()


def iter_disclosures(
    api_key: str,
    *,
    bgn_de: date,
    end_de: date,
    page_count: int = 100,
    max_pages: int = 50,
    client: httpx.Client | None = None,
):
    """DART 공시를 페이지를 따라가며 Disclosure로 yield."""
    page_no = 1
    while page_no <= max_pages:
        body = fetch_list(
            api_key,
            bgn_de=bgn_de,
            end_de=end_de,
            page_no=page_no,
            page_count=page_count,
            client=client,
        )
        status = body.get("status")
        if status == "013":  # 데이터 없음
            return
        if status != "000":
            raise RuntimeError(f"DART API error: status={status} {body.get('message')}")
        for row in body.get("list", []):
            yield _row_to_disclosure(row)
        total_page = int(body.get("total_page", 1))
        if page_no >= total_page:
            return
        page_no += 1
