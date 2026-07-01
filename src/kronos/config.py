from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    dart_api_key: SecretStr | None = None
    naver_client_id: SecretStr | None = None
    naver_client_secret: SecretStr | None = None

    log_level: str = "INFO"

    # PostgreSQL 연결. 컨테이너에서는 DATABASE_URL 환경변수로 주입
    # (host=postgres). 호스트 개발 시 기본값은 localhost:5432.
    database_url: str = "postgresql://kronos:kronos@localhost:5432/kronos"

    data_dir: Path = PROJECT_ROOT / "data"
    log_dir: Path = PROJECT_ROOT / "logs"


def get_settings() -> Settings:
    return Settings()
