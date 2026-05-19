from dataclasses import dataclass

import httpx

DART_BASE_URL = "https://opendart.fss.or.kr/api"


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
