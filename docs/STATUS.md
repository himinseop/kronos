# 프로젝트 상태 (living document)

> 최종 갱신: 2026-07-02. 세션 인수인계용. 매 작업 마무리 시 갱신.

## 현재 단계

- **Phase 1 (수집)**: 완료·운영 중
- **Phase 2 (감성분석)**: 진행 중 — KR-FinBERT 감성 파이프라인 구현 완료(커밋 `325807a`),
  현재 **PostgreSQL 전환 중** (아래 진행 상황 참조)

## ⚠️ 지금 켜져 있는 것 / 꺼야 하는 것

- **collector 컨테이너만 실행 중** (단일 writer → SQLite 손상 위험 없음)
- **sentiment·dashboard 컨테이너는 의도적으로 중지 상태로 둠**
- **절대 하지 말 것**: `docker compose up`으로 3개 컨테이너를 동시에 SQLite(bind mount)에
  붙이지 말 것 → 아래 사고 재발. PG 전환 완료 후에만 전체 기동.

```bash
docker compose ps -a                 # 상태 확인
docker compose logs -f collector     # 수집 로그
docker compose stop collector        # 필요 시 중지
```

## 🔴 2026-07-02 사고 & 복구 기록

- **사고**: sentiment 컨테이너 추가로 collector+sentiment+dashboard 3개가 같은 SQLite를
  Docker bind mount(`./data`)로 동시 접근 → **DB 손상** (`database disk image is malformed`).
- **근본 원인**: Docker Desktop macOS 가상 FS(VirtioFS)가 SQLite WAL의 파일 락을
  보장하지 않음. 다중 프로세스 동시 쓰기에서 발생.
- **복구**: `sqlite3 .recover`로 거의 전량 복구 (news/disclosures/tickers 손실 0,
  sentiments 일부 유실 → 재분석으로 복원 가능). 무결성 `ok`.
- **보존물**:
  - `data/kronos.db.corrupt` — 손상 원본 (PG 이관 검증 후 삭제 가능)
  - `data/backups/kronos-20260701-232106.db.gz` — 복구 직후 백업
  - `data/backups/kronos-20260601-163630.db.gz` — Docker 전환 전 백업

## 결정: PostgreSQL 전환 (사용자 승인)

동시쓰기 안전성을 근본 해결. 로드맵의 원래 Phase 2 계획으로 복귀.

### 진행 상황

- [x] WIP 브랜치 생성: **`feat/postgres-migration`** (psycopg 의존성 + config `database_url`만 담김)
  - ⚠️ 이 브랜치는 `uv lock` 미갱신 상태 — 재개 시 `uv lock` 먼저
- [ ] PG 인프라: compose `postgres` 서비스(named volume `pgdata` — bind mount 금지!),
  healthcheck, `.env`에 POSTGRES_*·DATABASE_URL
- [ ] storage 레이어 PG 전환: `db.py`(psycopg connect/transaction, DSN 기반),
  `schema.py`(PG DDL: BIGSERIAL, TIMESTAMPTZ, now()), `repository.py`(`ON CONFLICT DO NOTHING`)
- [ ] 소비자 SQL 전환 (14개 파일, 대부분 dashboard):
  - `datetime('now','-N day')` → `now() - interval 'N days'`
  - `strftime('%Y-%m-%d %H:00', col)` → `to_char(col, 'YYYY-MM-DD HH24:00')`
  - `date(col)` → `col::date`
  - `CAST(x AS TEXT|INTEGER)` → `x::text` / `x::int`
  - `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
  - SQL 내 `printf(...)` 제거 → Python 포매팅으로
  - 워커 시그니처 `db_path: Path` → DSN 기반 `connect()`
- [ ] 마이그레이션 스크립트: 복구본 `data/kronos.db` → PG.
  ISO 텍스트 timestamp(`YYYY-MM-DDTHH:MM:SS.ffffffZ`) → timestamptz 파싱. 건수 검증.
- [ ] 테스트: dockerized PG 대상 fixture, PG 미가동 시 DB 테스트 skip (순수 로직 테스트는 유지)
- [ ] 빌드·데이터 이관·동시쓰기 무손상 확인·docs 갱신·커밋

### 재개 시 첫 명령

```bash
git checkout feat/postgres-migration
uv lock            # psycopg 반영
# 이후 docs 체크리스트 순서대로
```

## 데이터 현황 (2026-07-02)

| 테이블 | 건수 |
|---|---|
| news | ~126,324 |
| disclosures | ~25,550 |
| sentiments | 11,811 (백로그 소진 중이었음, PG 이관 후 재개) |
| tickers | 3,965 |

## 원격 접근 (개인 인프라, docs 미기재)

- Tailscale: `office.dropbear-barb.ts.net` — SSH(22)/VNC(5900)/dashboard(8501 serve)
- 대시보드는 PG 전환 후 재기동 시 확인
