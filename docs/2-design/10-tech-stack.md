# 10. 기술 스택

## 언어 / 런타임

- **Python 3.11+** (타입 힌트, 성능 개선, `tomllib` 표준 포함)
- Python 3.12도 무방. 3.10 이하는 지양

## 패키지 관리

- **`uv`** (추천) — Rust 기반, 설치·해결 속도 압도적
  - 대안: `poetry`, `hatch`
- 가상환경: `uv venv` 또는 `python -m venv`
- 의존성 잠금: `uv.lock` 또는 `poetry.lock`

## 핵심 라이브러리

### 데이터
- **pandas** — DataFrame 표준
- **polars** — 성능 필요한 벡터 연산 (선택)
- **numpy**
- **pyarrow** — Parquet 저장

### 시세·데이터 수집
- **pykrx** — KRX 데이터 (일봉, 수급, PER/PBR)
- **FinanceDataReader** — 한·미 주가
- **OpenDartReader** / **dart-fss** — DART 공시·재무제표
- **mojito** (비공식) 또는 자체 KIS 래퍼 — KIS API

### HTTP / 비동기
- **httpx** — 동기·비동기 통합
- **asyncio** / **aiolimiter** — 레이트 리밋
- **websockets** — WebSocket 클라이언트

### 데이터 검증
- **pydantic v2** — 경계 데이터 모델, 설정
- **pydantic-settings** — 환경변수/설정 로딩

### 스케줄링
- **APScheduler** — 크론 스타일 작업
- 대안: 시스템 cron + CLI 명령

### 분석 / 지표
- **TA-Lib** 또는 **pandas-ta** — 기술지표
- **scikit-learn** — 간단한 ML (스코어링 등)

### 백테스팅
- **vectorbt** — 주 엔진
- **backtrader** — 보조

### 자연어 처리 (Phase 2~)
- **transformers** (HuggingFace) — **KR-FinBERT** (`snunlp/KR-FinBert-SC`) 감성 분석에 사용 중.
  일반 한국어 모델은 금융 어휘 맥락 부족. `analysis` extra로 설치(torch 포함)
- **torch** — KR-FinBERT 런타임
- **자체 LLM (Ollama)** — 카테고리 분류에 사용 중. `qwen2.5:3b-instruct`(Q4)를
  OpenAI 호환 `localhost:11434/v1`로 호출(httpx). 외부 API(anthropic/openai) 대신
  **자체 호스팅**으로 비용 0·데이터 외부 유출 없음. mycomai 등과 서버 공유 가능
- (선택) **sentence-transformers** — 임베딩·근사 중복 제거 (미도입)

### CLI / 대시보드
- **typer** — CLI
- **streamlit** — 간단 대시보드 (MVP)
- **rich** — 터미널 출력

### 로깅 / 관측
- **structlog** — 구조화 로그
- **loguru** (대안, 단순)
- 메트릭: **prometheus-client** (서버 운영 시)

### 테스트
- **pytest**
- **pytest-asyncio**
- **pytest-cov**
- **hypothesis** — 속성 기반 테스트 (리스크 엔진에 유용)
- **freezegun** — 시각 고정

### 코드 품질
- **ruff** — 린터 + 포매터 (black·isort·flake8 대체)
- **mypy** 또는 **pyright** — 정적 타입 검사
- **pre-commit** — 훅 관리

## 데이터 저장

### 현재: PostgreSQL 16 (Docker)
- **psycopg 3** (`dict_row`, autocommit) — SQL 직접 작성
- `pgdata` named volume, 포트 `127.0.0.1:5432`, healthcheck
- Phase 1은 SQLite로 시작했으나 다중 워커 동시쓰기 손상 사고로 조기 전환
  (SQLite는 macOS Docker bind mount에서 WAL 락 미보장 → 손상). 상세는
  [../history/2026-07-02.md](../history/2026-07-02.md)

### 확장
- **PostgreSQL** + **TimescaleDB** — 시세(틱/분봉) 도입 시 시계열 압축·쿼리 최적화
- 캐시: **Redis** (필요 시)

### 자체 LLM 인프라
- **Ollama** (네이티브, `brew services`) — OpenAI 호환 서버. macOS GPU(Metal) 가속을 위해
  Docker가 아닌 네이티브. Linux+NVIDIA 이전 시 컨테이너화 검토

### 파일
- 원본 공시·뉴스 텍스트: 로컬 디스크 또는 S3 호환(미니오) 저장
- 파케이(Parquet) 포맷으로 피처 스냅샷 저장

## ORM / 쿼리

- **SQLAlchemy 2.0** (선택) — 복잡한 쿼리 필요 시
- **SQL 직접 작성** (권장, MVP) — 명시성·디버깅 쉬움
- 마이그레이션: **alembic**

## 환경변수 / 설정

- `.env` 파일 + `python-dotenv`
- `pydantic-settings`로 타입 안전하게 로딩
- **실전 / 모의투자 프로파일 분리** (`KIS_ENV=paper|live`)

## 디렉토리 구조 (제안)

```
kronos/
├── pyproject.toml
├── README.md
├── docs/
├── src/kronos/
│   ├── data/            # 데이터 수집·저장
│   ├── analysis/        # NLP, 펀더멘털
│   ├── strategies/      # 전략 플러그인
│   ├── risk/            # 리스크 엔진
│   ├── broker/          # 증권사 어댑터
│   ├── order/           # 주문 관리
│   ├── backtest/        # 백테스트 엔진
│   ├── scheduler/
│   ├── dashboard/
│   ├── notify/
│   └── cli.py
├── tests/
├── configs/
│   ├── default.yaml
│   ├── paper.yaml
│   └── live.yaml
└── scripts/
```

## 버전 고정 정책

- 잠금 파일(`uv.lock`/`poetry.lock`) 커밋
- 월 1회 업데이트 및 회귀 테스트
- 증권사 API 관련 라이브러리는 **메이저 업데이트 시 수동 검증**

## 제외한 기술

- **Django / Flask 풀스택** — 불필요한 오버헤드. FastAPI로 충분하나 대시보드는 Streamlit
- **Kafka / RabbitMQ** — 개인 규모에 과도
- **Kubernetes** — 단일 프로세스/머신으로 충분
- **GraphQL** — 단일 클라이언트(대시보드)에 REST로 충분
