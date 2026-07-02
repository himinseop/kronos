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

    # 자체 LLM 추론 서버 (OpenAI 호환). Ollama 기본 엔드포인트를 가리킴.
    # mycomai 등 다른 프로젝트와 동일 서버를 공유할 수 있도록 OpenAI /v1 규격 사용.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:3b-instruct"
    llm_api_key: SecretStr | None = None  # 로컬 서버는 불필요, 클라우드 폴백 시 사용
    llm_timeout_seconds: float = 60.0

    data_dir: Path = PROJECT_ROOT / "data"
    log_dir: Path = PROJECT_ROOT / "logs"


def get_settings() -> Settings:
    return Settings()
