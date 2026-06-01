from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from kronos.storage.models import Disclosure

DART_BASE_URL = "https://opendart.fss.or.kr/api"
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"

# DART list.json 응답에 공시 유형 코드(pblntf_ty)가 빠져 있어 report_nm 패턴으로 추정한다.
# 코드 의미: A=정기공시, B=주요사항보고, C=발행공시, D=지분공시, E=기타공시,
#            F=외부감사, G=펀드공시, H=거래소공시, I=공정위공시, J=자율공시
# 룰 적용 순서가 중요 — 더 구체적·고유한 패턴을 먼저 매칭한다.
_PBLNTF_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # 우선순위: 명확한 wrapper / 고유 키워드 먼저
    ("B", ("주요사항보고서",)),  # 'XXX결정' 같은 내부 키워드보다 wrapper가 우선
    ("F", ("감사보고서", "외부감사", "감사인지정")),
    ("G", ("집합투자증권", "투자신탁", "투자회사", "수익증권", "(집합투자")),
    (
        "D",
        (
            "주식등의대량보유",
            "임원ㆍ주요주주",
            "임원·주요주주",
            "특정증권등소유",
            "최대주주변경",
            "최대주주등소유주식변동",
            "지분변동",
        ),
    ),
    (
        "C",
        (
            "증권발행",
            "투자설명서",
            "전환사채권",
            "신주인수권부사채",
            "교환사채권",
            "유상증자결정",
            "무상증자결정",
            "신주발행",
            "전환가액조정",
            "일괄신고",
            "파생결합사채",
            "파생결합증권",
        ),
    ),
    ("I", ("대규모기업집단", "공정거래", "지주회사")),
    (
        "H",
        (
            "거래정지",
            "관리종목",
            "투자위험",
            "투자주의",
            "투자경고",
            "상장폐지",
            "조회공시",
            "불성실공시",
            "공시번복",
        ),
    ),
    (
        "J",
        (
            "공정공시",
            "자율공시",
            "지연공시",
            "결산실적",
            "기업설명회",
            "단일판매ㆍ공급계약",
            "단일판매·공급계약",
            "기업지배구조보고서",
            "주주총회결과",
        ),
    ),
    ("B", ("타법인주식및출자증권", "자금차입")),  # wrapper 외 B 패턴
    ("A", ("사업보고서", "분기보고서", "반기보고서", "연결재무제표")),
)

_BRACKET_PREFIX = re.compile(r"^\[[^\]]+\]")


def infer_pblntf_ty(report_nm: str | None) -> str | None:
    """report_nm 패턴으로 공시 유형 코드 추정. 기본은 'E'(기타공시)."""
    if not report_nm:
        return None
    # [기재정정], [첨부정정] 같은 prefix 제거
    name = _BRACKET_PREFIX.sub("", report_nm).strip()
    for code, keywords in _PBLNTF_RULES:
        for kw in keywords:
            if kw in name:
                return code
    return "E"


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
    report_nm = row.get("report_nm", "").strip()
    # DART list.json은 pblntf_ty를 응답에 포함하지 않으므로 report_nm 패턴으로 추정
    pblntf_ty = row.get("pblntf_ty") or infer_pblntf_ty(report_nm)
    return Disclosure(
        rcept_no=rcept_no,
        corp_code=row.get("corp_code") or None,
        corp_name=row.get("corp_name") or None,
        ticker=stock_code if stock_code and stock_code.strip() else None,
        report_nm=report_nm,
        submitter=row.get("flr_nm") or None,
        rcept_dt=_parse_dart_dt(row["rcept_dt"]),
        source_url=DART_VIEWER_URL.format(rcept_no=rcept_no),
        pblntf_ty=pblntf_ty,
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
