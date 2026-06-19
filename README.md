# Kronos

뉴스·공시 분석 기반 한국 주식 자동매매 시스템.

준비 문서: [`docs/README.md`](./docs/README.md)
로드맵: [`docs/14-roadmap.md`](./docs/14-roadmap.md)

## Quickstart

### 로컬 개발 (uv)

```bash
uv sync                 # 의존성 설치
cp .env.example .env    # API 키 입력
uv run kronos status    # DART / 네이버 API 연결 점검
uv run pytest -q        # 테스트
```

### 운영 (Docker Compose)

```bash
cp .env.example .env              # API 키 입력 (최초 1회)
docker compose up -d --build      # collector + dashboard 기동
docker compose logs -f collector  # 수집 로그
# 대시보드: http://127.0.0.1:8501
docker compose down               # 중지
```

- `collector`: 수집 스케줄러 (DART 30초 / 뉴스 5분)
- `dashboard`: Streamlit (`127.0.0.1:8501`로만 노출)
- SQLite는 `./data` 볼륨에 영속. 재부팅 복원은 Docker Desktop 자동 시작 설정 필요.

## 주요 CLI

```bash
uv run kronos collect dart            # DART 공시 1회 수집
uv run kronos collect naver           # 네이버 뉴스 1회 수집
uv run kronos collect rss             # RSS 1회 수집
uv run kronos tickers sync            # KRX 종목 사전 갱신
uv run kronos match backfill          # 뉴스 종목 매칭 백필
uv run kronos disclosures reclassify  # 공시 유형(pblntf_ty) 백필
uv run kronos run                     # 스케줄러 (foreground)
uv run kronos dashboard               # 대시보드 (localhost)
```
