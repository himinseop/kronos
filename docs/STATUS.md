# 프로젝트 상태 (living document)

> 최종 갱신: 2026-07-02. 세션 인수인계용. 매 작업 마무리 시 갱신.

## 현재 단계

- **Phase 1 (수집)**: 완료·운영 중
- **Phase 2 (감성분석)**: 진행 중 — KR-FinBERT 감성 파이프라인 완료(백로그 100% 소진),
  **PostgreSQL 전환 완료**, **자체 LLM 카테고리 분류 가동**(Ollama+Qwen2.5-3B, 백로그 소진 중).
  다음: 라벨링 샘플 수동 평가 + 모델 비교 뷰.

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
| ollama | `brew services` 네이티브 (localhost:11434, Metal 가속) | `brew services info ollama` |
| collector | `uv run kronos run` (호스트) | `logs/collector.log` |
| sentiment | `uv run kronos analyze run` (호스트) | `logs/sentiment.log` |
| classify | `uv run kronos analyze classify-run` (호스트) | `logs/classify.log` |
| dashboard | `uv run kronos dashboard` (호스트, 127.0.0.1:8501) | `logs/dashboard.log` |

- 접속: `https://office.dropbear-barb.ts.net` (Tailscale serve) 또는 `http://127.0.0.1:8501`
- 중지: `pkill -f "kronos run"`, `pkill -f "analyze run"`, `pkill -f "classify-run"`, `pkill -f "streamlit run"`
- **PG는 동시성 안전** — 호스트 다중 프로세스가 동시에 붙어도 문제 없음

### 자체 LLM (Ollama) — kronos·mycomai 공유 인프라

- **네이티브 설치**(brew, Docker 아님): macOS Docker는 M1 GPU(Metal) 미지원 → CPU only로 5~10배 느림. GPU 가속 위해 네이티브 필수. Linux+NVIDIA로 이전 시 컨테이너화 검토.
- OpenAI 호환 엔드포인트 `localhost:11434/v1` — kronos는 `llm_base_url` 설정으로 호출.
  mycomai는 기존 `LLMProvider` 추상화에 provider 추가로 동일 서버 공유 가능(미연동).
- 모델: `qwen2.5:3b-instruct` (Q4, ~2GB). 16GB RAM 여유 위해 소형 선택. 정확도 부족 시 7B로.
- 카테고리 분류 백필 규모: 종목 매칭 뉴스 ~112K, ~1.1s/건 → 약 35시간 소진 예정(최신순).

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

- [x] 자체(로컬) LLM 기반 카테고리 분류 — Ollama+Qwen2.5-3B, 종목 매칭 뉴스 대상 (가동, 백로그 소진 중)
- [x] 대시보드 카테고리 탭 (분포·추세·종목별·피드)
- [ ] 카테고리 백로그 소진 완료 확인 (~35h 예상, 최신순)
- [ ] 라벨링 샘플 100건 수동 평가 (감성·카테고리 정확도) — 정확도 부족 시 7B 승격
- [ ] 모델 비교 뷰 (룰 이벤트 vs 감성 vs LLM 카테고리)
- [ ] Docker 레지스트리 회복 후 컨테이너 재빌드 → 스택 컨테이너화 복귀 (Ollama는 네이티브 유지)
- [ ] mycomai에 OllamaProvider 연동 (동일 서버 공유, 사용자 확정 후)

## 원격 접근 (개인 인프라, docs 미기재)

- Tailscale: `office.dropbear-barb.ts.net` — SSH(22)/VNC(5900)/dashboard(8501 serve)
