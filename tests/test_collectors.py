import httpx
import respx
from kronos.collectors import dart, naver


@respx.mock
def test_dart_ping_ok():
    respx.get("https://opendart.fss.or.kr/api/list.json").mock(
        return_value=httpx.Response(200, json={"status": "000", "message": "정상"})
    )
    result = dart.ping("dummy")
    assert result.ok
    assert result.dart_status == "000"


@respx.mock
def test_dart_ping_invalid_key():
    respx.get("https://opendart.fss.or.kr/api/list.json").mock(
        return_value=httpx.Response(200, json={"status": "010", "message": "등록되지 않은 키"})
    )
    result = dart.ping("dummy")
    assert not result.ok
    assert result.dart_status == "010"


@respx.mock
def test_naver_ping_ok():
    respx.get("https://openapi.naver.com/v1/search/news.json").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    result = naver.ping("id", "secret")
    assert result.ok
    assert result.status_code == 200


@respx.mock
def test_naver_ping_unauthorized():
    respx.get("https://openapi.naver.com/v1/search/news.json").mock(
        return_value=httpx.Response(401, json={"errorMessage": "Authentication failed"})
    )
    result = naver.ping("id", "bad")
    assert not result.ok
    assert result.status_code == 401
