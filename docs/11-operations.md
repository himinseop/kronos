# 11. 운영 (Operations)

## 운영 원칙

- 복잡도보다 **관측 가능성** 우선
- 자동화는 **안전한 방향**(정지·알림)만, 위험한 방향(재주문·자동 복구)은 수동
- 배포는 **재현 가능**해야 함 (같은 코드 · 같은 의존성)

## 배포 형태

### 옵션 A: Docker Compose (현재 채택)
- 로컬 머신(미니PC/맥)에서 `docker compose up -d`로 전체 스택 기동
- `collector`(수집 스케줄러) + `dashboard`(Streamlit) 단일 이미지, 추후 `postgres` 추가
- 재시작 정책 `restart: unless-stopped` → 프로세스가 죽으면 자동 복원
- 재부팅 복원: **Docker Desktop "Start when you sign in"** 설정 시 자동 (macOS는 `AutoStart`)
- 장점: 환경 일관성, 단일 명령 관리, 재부팅 복원, Phase 2 PG 추가가 자연스러움
- 단점: Docker Desktop 상시 실행 필요

### 옵션 B: 호스트 직접 실행 (Docker 미사용 환경)
- macOS: `launchd` / Linux: `systemd`로 프로세스 관리
- `scripts/install-launchd.sh`로 `com.kronos.runner`(KeepAlive) + `com.kronos.backup`(일 1회) 등록
- Docker가 부담스러운 가벼운 호스트(라즈베리파이 등)나 단일 프로세스만 필요할 때

**현재 운영**: 옵션 A (Docker Compose). 옵션 B 스크립트는 대안으로 저장소에 유지.

## 프로세스 관리

### Docker (현재)
- `docker-compose.yml`: `collector`, `dashboard` (Phase 2에서 `postgres` 추가)
- 재시작 정책 `unless-stopped`, 타임존 `TZ=Asia/Seoul` 환경변수 명시
- SQLite는 `./data` 볼륨 마운트로 컨테이너 간 공유 + 호스트 영속
- dashboard는 `127.0.0.1:8501`로만 publish (외부 노출은 Tailscale serve가 담당)
- 주요 명령:
  - `docker compose up -d --build` — 빌드 + 기동
  - `docker compose logs -f collector` — 수집 로그
  - `docker compose ps` / `docker compose down` — 상태 / 중지

### macOS (`launchd`, 대안)
- `~/Library/LaunchAgents/com.kronos.runner.plist`, `RunAtLoad=true`, `KeepAlive=true`
- `scripts/install-launchd.sh`가 템플릿을 렌더링해 등록

### Linux (`systemd`, 대안)
- `/etc/systemd/system/kronos.service`, `Restart=on-failure` + `RestartSec=30`

## 단일 인스턴스 보장

**중복 실행은 중복 주문을 부른다.**

- 파일락: `fcntl.flock`으로 `/var/run/kronos.lock` 잠금
- 또는 systemd/launchd 단일 유닛으로 강제
- 시작 시 **PID 파일 확인 → 기존 프로세스 살아있으면 실패**

## 장중 스케줄

| 시각 | 작업 |
|---|---|
| 08:00 | 전일 데이터 검증, 당일 유니버스 확정, 시세 구독 준비 |
| 08:30~09:00 | 동시호가 모니터링 (매매 최소화) |
| 09:00 | 장 시작, 실시간 매매 엔진 가동 |
| 09:00~15:20 | 장중 운영, 주기적 헬스체크 |
| 15:20~15:30 | 동시호가 (인트라데이 포지션 청산) |
| 15:30 | 장 마감 |
| 16:00 | 일일 리포트 생성, 텔레그램 전송 |
| 17:00 | 종목 데이터 배치 수집 (일봉, 수급) |
| 23:00 | DART·뉴스 정리, 전략 성과 집계 |

비거래일(주말·휴장)은 장중 엔진 비활성화, 배치만 유지

## 헬스체크

주기적으로 확인:
- Broker API 응답 시간
- 시세 WebSocket 연결 상태
- DB 쓰기 가능 여부
- 디스크 여유 공간
- 메모리 사용량

실패 시: 알림 → 임계 이상이면 매매 중단

## 로깅

### 구조
```
logs/
├── app.log              # 애플리케이션 전체
├── orders.log           # 주문·체결 append-only (절대 삭제 금지)
├── signals.log          # 전략 신호
├── risk.log             # 리스크 엔진 결정
└── errors.log
```

### 정책
- **주문·체결 로그는 append-only, 최소 7년 보관** (세무 자료)
- 매일 로그 로테이션 (gzip 압축)
- 중요 이벤트는 구조화 JSON (`structlog`)
- 민감정보 마스킹 (→ [12-security.md](./12-security.md))

## 모니터링 / 알림

### 텔레그램 봇 (기본)
- 체결 알림 (옵션, 빈도 높으면 피곤)
- 리스크 이벤트 (손절 발동, 서킷브레이커)
- 일일 요약 (장 마감 후)
- 시스템 장애

### 대시보드 (Streamlit)

**Phase 1부터 도입**. 단계별로 탭을 확장한다.

- **수집 모니터링** (Phase 1~)
  - 소스별 시간대별 수집 건수, 오늘 합계
  - 수집기 마지막 성공 시각, 연속 실패 수, API 호출 한도 사용률
  - 최근 뉴스·공시 피드 (종목·소스·기간·키워드 필터)
  - 공시 유형 분포, 중복률, 종목 매칭 성공률, 미매칭 샘플
- **감성·분류** (Phase 2~)
  - 피드에 감성 점수·라벨·카테고리 컬럼
  - 분석 큐 상태, LLM 토큰·비용 사용량
- **시장 흐름** (Phase 3~)
  - 섹터×일자 감성 히트맵
  - Top Movers (감성 z-score 급등락)
  - 종목 상세: 감성 추세, 뉴스·공시 타임라인, 재무 요약
- **매매 운영** (Phase 6~)
  - 현재 포지션·PnL
  - 최근 주문·신호
  - 전략별 성과
  - API 헬스 상태

## 장애 대응 플레이북

### 증상: 주문이 체결 안 됨
1. Broker API 수동 테스트 (잔고 조회 호출)
2. 네트워크 상태 확인
3. API 키 만료/차단 여부
4. 문제 지속 시 **매매 중단**, 수동 확인 후 재개

### 증상: 시세 데이터 누락
1. WebSocket 재연결 시도
2. 일정 시간 재연결 실패 시 매매 중단
3. 장 마감 후 누락 구간 배치 수집

### 증상: 프로세스 죽음
1. systemd/launchd가 재시작
2. **재시작 시 상태 복원**: 증권사 잔고와 내부 포지션 정합성 검증
3. 불일치 시 매매 중단 + 알림

### 증상: 이상 주문 발생
1. **즉시 매매 정지**
2. 증권사 API로 진행 중 주문 전량 취소
3. 사후 분석 → 수정 → 재가동 (수동 승인)

## 백업

- DB: 일 1회 덤프 (`sqlite .backup` 또는 `pg_dump`), 외부 저장소 동기화
- 설정 파일: git 관리
- 로그: 월 단위 아카이브

## 배포 프로세스

1. `main` 브랜치에서 `git tag vX.Y.Z`
2. 스테이징(모의투자 환경)에서 **최소 1일 무인 실행**
3. 주말 점검: 실전 환경에 배포, 모니터링 강화
4. 배포 전 **매매 중단 상태에서 재시작**

**절대 금지**: 장중 배포, 설정 변경 후 검증 없이 실행

## 업그레이드 시 점검

- 파이썬 / 주요 라이브러리 메이저 업데이트 후: 백테스트 회귀 테스트 + 모의투자 1주
- 증권사 API 스펙 변경 알림 체크 (KIS 공지사항)
- OS 업데이트 후 스케줄러·락 파일 동작 확인
