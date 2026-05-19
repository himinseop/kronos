# 11. 운영 (Operations)

## 운영 원칙

- 복잡도보다 **관측 가능성** 우선
- 자동화는 **안전한 방향**(정지·알림)만, 위험한 방향(재주문·자동 복구)은 수동
- 배포는 **재현 가능**해야 함 (같은 코드 · 같은 의존성)

## 배포 형태

### 옵션 A: 로컬 머신 (MVP 권장)
- 개인 PC에서 실행
- macOS: `launchd` / Linux: `systemd`
- 장점: 단순, 제로 비용
- 단점: PC 종료 시 다운, 네트워크 불안정

### 옵션 B: 개인 서버 / VPS
- 작은 클라우드 인스턴스 (월 1~2만원 수준)
- Docker Compose로 단일 호스트 구성
- 장점: 24/7 가용성
- 단점: 보안·유지보수 필요

### 옵션 C: 홈서버 (라즈베리파이 / 미니PC)
- 집 네트워크
- 전기세 외 고정비 없음
- 네트워크 이중화 고려

**MVP**: 옵션 A로 시작 → Phase 3 이후 옵션 B로 이관

## 프로세스 관리

### macOS (`launchd`)
- `~/Library/LaunchAgents/com.kronos.runner.plist` 배치
- `RunAtLoad=true`, `KeepAlive=true`
- 표준 출력은 로그 디렉토리로 리디렉트

### Linux (`systemd`)
- `/etc/systemd/system/kronos.service`
- `Restart=on-failure` + `RestartSec=30`
- `User=kronos` 전용 유저 사용

### Docker (서버 운영 시)
- `docker-compose.yml`: app, postgres, redis(선택)
- 컨테이너 재시작 정책 `unless-stopped`
- 타임존은 `Asia/Seoul` 명시

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

## 원격 접근 (Tailscale)

본인 디바이스(iPad/노트북 등) 어디서든 안전하게 SSH·dashboard에 접근하기 위해 Tailscale 메시 사설망을 사용한다. **공인 인터넷에 포트를 열지 않는다.** 보안 정책 상세는 [12-security.md](./12-security.md) 참조.

### 설치 (macOS 호스트)
1. App Store에서 **Tailscale** 설치 (또는 https://tailscale.com/download/mac 에서 standalone .pkg)
2. 메뉴바 아이콘 → Log in (Google/GitHub 등 OAuth)
3. CLI 사용 시 `/usr/local/bin/tailscale`이 자동 생성됨 (standalone .pkg)
   - App Store 버전은 래퍼 스크립트 필요:
     `printf '#!/bin/sh\nexec /Applications/Tailscale.app/Contents/MacOS/Tailscale "$@"\n' | sudo tee /usr/local/bin/tailscale && sudo chmod +x /usr/local/bin/tailscale`

### Tailnet 1회 설정 (admin 콘솔)
- https://login.tailscale.com/admin/dns 에서 **MagicDNS** + **HTTPS Certificates** 활성화
- 디바이스명 `<host>.<tailnet>.ts.net` 형태로 자동 발급되고 TLS 인증서까지 무료 자동 발급

### SSH 활성화 (Mac 호스트)
- macOS GUI 빌드(App Store/standalone .pkg)는 `tailscale up --ssh` 미지원 — 대신 macOS 표준 sshd 사용
- 시스템 설정 → 일반 → 공유 → **원격 로그인** ON
- `~/.ssh/authorized_keys`에 접속할 디바이스의 공개키 등록 (비밀번호 인증보다 권장)

### Dashboard 노출
```bash
uv run kronos dashboard       # 127.0.0.1:8501 바인딩
tailscale serve --bg 8501     # tailnet에 HTTPS로 프록시 (재부팅 후 자동 복원)
```
- 접속 URL: `https://<host>.<tailnet>.ts.net/`
- 해제: `tailscale serve --https=443 off`
- 현재 상태 확인: `tailscale serve status`

### 클라이언트 (iPad/iPhone/Mac/Windows)
- App Store/Play Store에서 Tailscale 설치 → 같은 계정 로그인
- SSH 클라이언트: iPad는 **Termius**(무료), **Blink Shell**(유료) 추천
- 접속: `ssh we@<host>.<tailnet>.ts.net` 또는 tailnet IP(`100.x.y.z`)
- Dashboard: 브라우저로 `https://<host>.<tailnet>.ts.net/`

### 장애 대응
- Tailscale 데몬이 죽었을 때: 메뉴바 GUI 재시작 또는 `sudo launchctl kickstart -k system/com.tailscale.tailscaled`
- DERP relay만 잡히고 direct connection 불가: 방화벽 NAT 통과 확인 (성능 저하만, 동작은 함)
- 인증서 발급 실패: admin 콘솔 HTTPS Certs 활성 여부 재확인

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
