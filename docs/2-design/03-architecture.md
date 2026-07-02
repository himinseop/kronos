# 03. 아키텍처

## 상위 컴포넌트

```
┌─────────────────────────────────────────────────────────────────┐
│                      External Sources                            │
│   KIS API · DART · pykrx · 네이버 뉴스 · RSS · 기타               │
└────────────┬───────────────┬──────────────┬─────────────────────┘
             │               │              │
             ▼               ▼              ▼
        ┌─────────┐    ┌─────────┐    ┌──────────┐
        │ Market  │    │ Filing  │    │  News    │
        │ Data    │    │ Ingest  │    │ Ingest   │
        │ Ingest  │    │ (DART)  │    │          │
        └────┬────┘    └────┬────┘    └────┬─────┘
             └────────┬─────┴──────────────┘
                      ▼
              ┌───────────────┐
              │   Data Lake   │  PostgreSQL (현재) → +TimescaleDB(시세)
              │  (raw + curated) │
              └──────┬────────┘
                     │
                     ▼
         ┌──────────────────────┐
         │  Strategy Engine     │  단기/중장기/뉴스/퀀트 (플러그인)
         │  Strategy.generate_  │
         │    signals(data)     │
         └──────┬───────────────┘
                │ Signal
                ▼
         ┌──────────────────────┐
         │  Risk Engine         │  포지션 사이징, 한도 검증,
         │  (pre-trade checks)  │  서킷브레이커
         └──────┬───────────────┘
                │ Order (validated)
                ▼
         ┌──────────────────────┐
         │  Order Manager       │  멱등성, 상태 추적,
         │  (broker adapter)    │  체결 콜백
         └──────┬───────────────┘
                │
                ▼
         ┌──────────────────────┐
         │  Broker API (KIS)    │  REST + WebSocket
         └──────────────────────┘

   ┌─────────────┐   ┌─────────────┐   ┌──────────────┐
   │  Scheduler  │   │  Dashboard  │   │  Notifier    │
   │ (APScheduler)│  │ (Streamlit) │   │ (Telegram)   │
   └─────────────┘   └─────────────┘   └──────────────┘
```

## 컴포넌트별 책임

### Data Ingestion
- 외부 소스에서 데이터를 수집해 Data Lake에 저장
- **원본(raw) 레이어**와 **가공(curated) 레이어** 분리
- 실패 시 재시도, 결손 탐지

### Data Lake
- **현재: PostgreSQL 16** (Docker, `pgdata` named volume). psycopg3 + `dict_row` 사용.
- Phase 1은 SQLite로 시작했으나, Phase 2에서 다중 워커(collector+sentiment+classify)가
  동시 기록하며 macOS Docker bind mount 위 SQLite가 손상 → **PostgreSQL로 조기 전환**
  (2026-07-02, [history/2026-07-02.md](../history/2026-07-02.md)).
- **장기 확장**: PostgreSQL + TimescaleDB (시계열 압축, 대용량 시세)

#### 핵심 테이블 스키마 (PostgreSQL)

```sql
-- 뉴스 (Phase 1)
CREATE TABLE news (
  id           BIGSERIAL PRIMARY KEY,
  ticker       TEXT,                  -- 매핑된 종목코드 (다중일 경우 별도 매핑 테이블)
  title        TEXT NOT NULL,
  body         TEXT,
  publisher    TEXT,
  url          TEXT,
  published_at TIMESTAMPTZ NOT NULL,
  hash         CHAR(64) UNIQUE,       -- SHA-256(정규화 제목 + URL) — 중복 차단
  collected_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON news (ticker, published_at DESC);

-- 공시 (Phase 1)
CREATE TABLE disclosures (
  rcept_no    TEXT PRIMARY KEY,        -- DART 접수번호
  ticker      TEXT,
  report_nm   TEXT NOT NULL,
  submitter   TEXT,
  rcept_dt    TIMESTAMPTZ NOT NULL,
  source_url  TEXT,
  pblntf_ty   TEXT                     -- 공시 유형 코드
);
CREATE INDEX ON disclosures (ticker, rcept_dt DESC);

-- 감성 분석 결과 (Phase 2)
CREATE TABLE sentiments (
  id           BIGSERIAL PRIMARY KEY,
  target_type  TEXT NOT NULL,          -- 'news' | 'disclosure'
  target_id    TEXT NOT NULL,          -- news.id 또는 disclosures.rcept_no
  model        TEXT NOT NULL,          -- 'kr-finbert-sc'(감성), 'cat:<모델>'(카테고리)
  score        REAL NOT NULL,          -- -1.0 ~ 1.0
  label        TEXT NOT NULL,          -- 'positive'|'negative'|'neutral' 또는 카테고리 key
  category     TEXT,                   -- 자체 LLM 분류 (실적/계약/규제/M&A/...)
  rationale    TEXT,                   -- LLM 근거 요약 (선택)
  analyzed_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (target_type, target_id, model)  -- 감성·카테고리를 model로 구분해 공존
);
CREATE INDEX ON sentiments (target_type, target_id);
CREATE INDEX ON sentiments (model, analyzed_at DESC);
```

> 감성(KR-FinBERT)과 카테고리(자체 LLM)는 **같은 sentiments 테이블**에 `model` 값으로
> 구분해 저장한다. 한 뉴스가 감성 행 1개 + 카테고리 행 1개를 가질 수 있다.

- 매매 단계(Phase 4~)에서 추가될 테이블: `ohlcv_daily`, `ohlcv_minute`, `financials`, `orders`, `fills`, `pnl`

### Strategy Engine
- 각 전략은 공통 인터페이스 구현: `generate_signals(data, context) -> List[Signal]`
- 전략은 **결정적(deterministic)**: 동일 입력 → 동일 출력
- 상태는 Strategy Engine 밖에 둠 (테스트 용이성)

### Risk Engine
- 모든 신호는 Risk Engine을 거쳐야 Order로 변환됨
- 검증: 포지션 한도, 일일 손실 한도, 종목·섹터 집중도, 현금 충분성
- 실패 시 **주문 생성 자체를 차단**, 사유 로깅

### Order Manager
- **멱등키(client_order_id)** 기반 중복 방지
- 상태 기계: `PENDING → SUBMITTED → PARTIAL/FILLED/CANCELLED/REJECTED`
- Broker Adapter 인터페이스를 통해 증권사 의존성 격리
- WebSocket 체결 이벤트를 받아 내부 상태 갱신

### Scheduler
- APScheduler 기반
- 주요 잡: 장 시작 전 시세 동기화, 공시·뉴스 폴링, 장 마감 후 리포트
- 실시간 반응은 Scheduler가 아니라 이벤트(콜백) 기반

### Dashboard / Notifier
- **Streamlit 대시보드는 Phase 1부터 도입** (수집 즉시 모니터링). 단계별로 탭을 추가:
  - Phase 1: 수집 개요 / 소스 헬스 / 최근 뉴스·공시 피드 / 공시 유형 / 중복·매칭 품질 (구현됨)
  - Phase 2: 감성 탭 + 카테고리 탭 (커버리지·분포·추세·종목별·피드) (구현됨).
    자체 LLM(Ollama)이라 LLM 비용 없음 — 대신 백로그 소진 진행률을 노출
  - Phase 3: 시장 흐름 (섹터 히트맵, Top Movers, 종목 상세 타임라인)
  - Phase 6~: 포지션·PnL, 주문·신호, 전략별 성과, API 헬스
- 로컬 전용(`localhost`), 원격 노출 시 인증 필수 ([12-security.md](../4-operations/12-security.md))
- Notifier: 텔레그램 봇 — 수집 장애, 중요 공시 급변, 체결·리스크 이벤트, 일일 요약

## 데이터 흐름 패턴

### 이벤트 기반 vs 폴링 기반

| 상황 | 권장 |
|---|---|
| 실시간 시세 | 이벤트 (KIS WebSocket) |
| 주문 체결 알림 | 이벤트 (WebSocket) |
| 공시 (DART) | 폴링 (30초 주기) — DART는 WebSocket 미지원 |
| 뉴스 | 폴링 (1~5분) |
| 일봉 종가 | 배치 (장 마감 후 1회) |

### 주문 멱등성 설계

1. 신호 생성 시 `client_order_id = hash(전략ID, 종목, 방향, 시각)` 부여
2. Order Manager는 이 키로 중복 주문 탐지
3. 증권사 API 호출 실패 시 동일 `client_order_id`로 재시도
4. 체결 콜백에도 `client_order_id` 매칭

## 장애 격리 원칙

- **한 전략의 에러가 다른 전략이나 전체 시스템을 멈추지 않도록** 전략별 예외 캡슐화
- 데이터 수집 실패 시 기존 데이터로 운영 유지 (단, 임계값 초과 시 매매 중단)
- Broker API 장애 시 신호는 큐잉하되 **자동 재주문은 하지 않음** (수동 확인 필요)

## 주요 설계 결정

- **모놀리식 프로세스**로 시작. 마이크로서비스는 불필요한 복잡도
- **동기 코드 우선**, 성능 필요한 부분만 asyncio 도입 (WebSocket 구독 등)
- 매매 프로세스는 단일 인스턴스 보장(파일락/systemd) — 중복 주문 방지 (Phase 6~)
- 분석 워커(sentiment·classify)는 PostgreSQL 동시성으로 안전하게 병렬 실행.
  자체 LLM은 Ollama(OpenAI 호환, `localhost:11434/v1`)로 분리 — mycomai 등과 공유 가능한
  호스트 네이티브 인프라 (macOS GPU/Metal 가속 위해 컨테이너화하지 않음)
