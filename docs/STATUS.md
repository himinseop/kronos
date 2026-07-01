# 프로젝트 상태 (living document)

> 최종 갱신: 2026-07-02. 세션 인수인계용. 매 작업 마무리 시 갱신.

## 현재 단계

- **Phase 1 (수집)**: 완료·운영 중
- **Phase 2 (감성분석)**: 진행 중 — KR-FinBERT 감성 파이프라인 구현 완료,
  **PostgreSQL 전환 완료**(코드·데이터·테스트). 다음: 자체 LLM 카테고리 분류.

## ✅ DB: SQLite → PostgreSQL 전환 완료 (2026-07-02)

SQLite 다중 컨테이너 동시쓰기 손상 사고(아래) 대응으로 PostgreSQL로 전환.

- storage 레이어 psycopg 재작성, 소비자 SQL 전량 PG 방언 전환, 81개 테스트 통과
- 복구본 SQLite → PG 이관 완료 (무손실):
  news 126,337 / disclosures 25,550 / collector_runs 149,574 /
  tickers 3,965 / ticker_aliases 7 / sentiments 11,811
- **동시쓰기 검증**: collector + sentiment가 PG에 동시 기록해도 손상 없음
  (SQLite를 손상시켰던 시나리오가 PG에선 정상)

## ⚠️ 지금 실행 중인 것 (호스트 프로세스)

**컨테이너가 아니라 호스트 venv 프로세스로 PG 스택을 가동 중** — 이유는 아래 Docker 이슈.

| 프로세스 | 명령 | 로그 |
|---|---|---|
| postgres | Docker 컨테이너 (pgdata named volume) | `docker compose logs postgres` |
| collector | `uv run kronos run` (호스트) | `logs/collector.log` |
| sentiment | `uv run kronos analyze run` (호스트) | `logs/sentiment.log` |
| dashboard | `uv run kronos dashboard` (호스트, 127.0.0.1:8501) | `logs/dashboard.log` |

- 접속: `https://office.dropbear-barb.ts.net` (Tailscale serve) 또는 `http://127.0.0.1:8501`
- 중지: `pkill -f "kronos run"`, `pkill -f "analyze run"`, `pkill -f "streamlit run"`
- **PG는 동시성 안전** — 호스트 다중 프로세스가 동시에 붙어도 문제 없음

## 🔴 미해결: Docker VM 레지스트리 네트워크 (컨테이너 재빌드 블로커)

- **증상**: `docker pull` / `docker build`가 "load metadata for ..." 단계에서 무한 hang.
  호스트 curl로는 registry 접근 정상(docker.io 200), 컨테이너 일반 outbound도 정상
  (DART/네이버 수집됨) — **레지스트리 프로토콜만** VM에서 막힘. Docker Desktop
  재시작(클린 kill 포함)으로도 미해소.
- **영향**: collector/sentiment/dashboard 컨테이너 이미지를 PG 코드로 재빌드 불가.
  그래서 현재는 위처럼 호스트 프로세스로 운영.
- **재개 시**: Docker 레지스트리 네트워크 회복 후
  ```bash
  docker compose build          # base + analysis 재빌드
  # 호스트 프로세스 중지 (pkill 위 3개)
  docker compose up -d          # postgres + collector + sentiment + dashboard
  ```
  compose/Dockerfile은 이미 PG 대응 완료. `# syntax=docker/dockerfile:1` 지시자는
  제거됨(레지스트리 frontend pull 회피).

## 🔴 2026-07-02 SQLite 손상 사고 기록 (해결됨)

- sentiment 컨테이너 추가로 collector+sentiment+dashboard 3개가 같은 SQLite를
  Docker bind mount로 동시 접근 → DB 손상. 근본원인: Docker Desktop macOS 가상 FS가
  SQLite WAL 파일 락 미보장.
- `sqlite3 .recover`로 거의 전량 복구 → PG로 이관. 손상본 `data/kronos.db.corrupt`,
  백업 `data/backups/` 보존 (PG 안정화 후 삭제 가능).

## 다음 작업 (Phase 2 잔여)

- [ ] 자체(로컬) LLM 기반 카테고리 분류 (실적/계약/규제/M&A) — 종목·이벤트 매칭분에 선택 적용
- [ ] 대시보드 카테고리 분포/모델 비교 뷰
- [ ] Docker 레지스트리 회복 후 컨테이너 재빌드 → 스택 컨테이너화 복귀
- [ ] sentiment 백로그 소진 완료 확인 (진행 중)

## 원격 접근 (개인 인프라, docs 미기재)

- Tailscale: `office.dropbear-barb.ts.net` — SSH(22)/VNC(5900)/dashboard(8501 serve)
