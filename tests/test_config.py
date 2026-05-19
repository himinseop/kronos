from kronos.config import Settings


def test_settings_loads_without_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in ("DART_API_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.dart_api_key is None
    assert s.naver_client_id is None
    assert s.naver_client_secret is None
    assert s.log_level == "INFO"


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "abc")
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")
    s = Settings(_env_file=None)
    assert s.dart_api_key is not None and s.dart_api_key.get_secret_value() == "abc"
    assert s.naver_client_id is not None and s.naver_client_id.get_secret_value() == "id"
    assert (
        s.naver_client_secret is not None and s.naver_client_secret.get_secret_value() == "secret"
    )
