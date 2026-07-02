# Kronos

뉴스·공시 분석 기반 한국 주식 자동매매 시스템.

문서: [`docs/README.md`](./docs/README.md) · 현재 상태: [`docs/STATUS.md`](./docs/STATUS.md) · 로드맵: [`docs/5-roadmap/14-roadmap.md`](./docs/5-roadmap/14-roadmap.md)

## Quickstart

### 로컬 개발 (uv)

```bash
uv sync                 # 의존성 설치
cp .env.example .env    # API 키 입력
uv run kronos status    # DART / 네이버 API 연결 점검
uv run pytest -q        # 테스트
```

### 운영 (현재: 호스트 프로세스 + Docker PostgreSQL)

저장소는 PostgreSQL(Docker), 워커·대시보드는 호스트 프로세스, 자체 LLM은 Ollama 네이티브로
운영 중입니다. 자세한 실행/중지 절차와 배경은 [`docs/STATUS.md`](./docs/STATUS.md) 참조.

```bash
docker compose up -d postgres     # PostgreSQL (pgdata named volume)
uv run kronos run &               # 수집 스케줄러 (DART 30초 / 뉴스 5분)
uv run kronos analyze run &       # 감성 분석 워커 (KR-FinBERT)
uv run kronos analyze classify-run &  # 카테고리 분류 워커 (Ollama)
uv run kronos dashboard           # 대시보드 (127.0.0.1:8501)
```

> Docker VM 레지스트리 네트워크 이슈로 앱 컨테이너 재빌드가 막혀 있어 호스트 프로세스로 운영 중.
> Ollama는 macOS GPU(Metal) 가속을 위해 항상 네이티브(`brew services`)로 유지.

## 주요 CLI

```bash
uv run kronos collect dart            # DART 공시 1회 수집
uv run kronos collect naver           # 네이버 뉴스 1회 수집
uv run kronos collect rss             # RSS 1회 수집
uv run kronos tickers sync            # KRX 종목 사전 갱신
uv run kronos match backfill          # 뉴스 종목 매칭 백필
uv run kronos disclosures reclassify  # 공시 유형(pblntf_ty) 백필
uv run kronos run                     # 수집 스케줄러 (foreground)
uv run kronos analyze sentiment       # 감성 분석 1회 (KR-FinBERT)
uv run kronos analyze run             # 감성 분석 루프
uv run kronos analyze category        # 카테고리 분류 1회 (자체 LLM)
uv run kronos analyze classify-run    # 카테고리 분류 루프
uv run kronos dashboard               # 대시보드 (localhost)
```
