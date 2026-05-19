# 05. 증권사 API 통합

## 후보 비교

| 항목 | **한국투자증권 KIS** | 키움증권 OpenAPI+ | LS증권(구 이베스트) |
|---|---|---|---|
| 방식 | REST + WebSocket | COM DLL (Windows only) | XingAPI (COM) / REST (일부) |
| OS | macOS / Linux / Windows | **Windows 전용** | Windows 주력 |
| 실시간 시세 | O (WebSocket) | O (이벤트 콜백) | O |
| 주문 | O | O | O |
| 모의투자 | O (계좌 발급) | O | O |
| 문서화 | 공식 문서 양호 | 오래됨, 커뮤니티 의존 | 중간 |
| 커뮤니티 | 활발 | 활발 | 상대적 적음 |
| 파이썬 지원 | 공식 SDK 존재 | `pywinauto`/`PyQt` 우회 | COM 래퍼 필요 |

## 선택: 한국투자증권 KIS Open API

**이유**:
1. **크로스플랫폼**: macOS/Linux에서 동작 → 로컬 개발·서버 운영 모두 가능
2. REST + WebSocket 조합으로 아키텍처가 깔끔
3. 공식 SDK (`mojito` 등 비공식 래퍼도 다수)
4. 모의투자 API가 실거래와 동일 구조

**트레이드오프**:
- 호가 단위 과거 데이터(틱) 조회는 키움이 더 풍부
- 초고빈도 전략에는 부적합 (본 프로젝트 범위 밖이므로 무관)

## KIS API 핵심 요소

### 인증
- **앱키(APP KEY)** + **앱시크릿(APP SECRET)** 발급
- 접근토큰(access token) 1회 발급 후 **24시간 유효**, 만료 전 갱신
- 계좌번호 + 상품코드 함께 관리

### 주요 엔드포인트 (카테고리)
- 국내주식 주문/잔고
- 시세 조회 (현재가, 호가, 분봉, 일봉)
- 체결 내역 조회
- 실시간 체결가 / 호가 (WebSocket)
- 실시간 체결통보 (WebSocket, 본인 주문)

### 주문 관련 주의사항
- **`ORD_DVSN` (주문구분)**: 시장가/지정가/최유리/최우선/IOC/FOK 코드 다름
- **정정/취소** 시 원주문번호(`ORGN_ODNO`) 필요
- 장전·장후 시간외 주문은 별도 엔드포인트
- 단주 매매(1주 미만) 불가

## 설계: Broker Adapter

증권사 종속성을 격리하기 위해 **어댑터 패턴** 사용.

```python
class Broker(Protocol):
    def place_order(self, order: Order) -> OrderAck: ...
    def cancel_order(self, order_id: str) -> CancelAck: ...
    def get_positions(self) -> list[Position]: ...
    def get_balance(self) -> Balance: ...
    def subscribe_quotes(self, symbols: list[str]) -> AsyncIterator[Quote]: ...
    def subscribe_fills(self) -> AsyncIterator[Fill]: ...
```

**장점**:
- 테스트 시 `MockBroker`로 교체
- 향후 다른 증권사 추가 시 구현체만 추가
- 모의투자 ↔ 실전 전환은 설정값으로 제어

## 계정 준비 체크리스트

> **진행 시점**: Phase 4 진입 직전 ([14-roadmap.md](./14-roadmap.md)). Phase 1~3(뉴스·공시 수집·분석·모니터링) 동안에는 KIS 계정 불필요 — 발급 절차에 시일이 걸리므로 Phase 3 후반에 미리 신청해두면 매끄럽다.

- [ ] 한국투자증권 **신규 계좌 개설** (비대면)
- [ ] **KIS Developers** 가입: https://apiportal.koreainvestment.com
- [ ] 앱키/시크릿 발급 (모의투자용 + 실전용 분리)
- [ ] 모의투자 계좌 신청
- [ ] API 이용약관 정독 (특히 **자동매매 허용 범위**)
- [ ] 2FA/OTP 설정

## 주문 레이트 리밋

- REST 초당 호출 제한 있음 (API별 상이, 약관 기준)
- WebSocket 구독 종목 수 제한 (계정당 ~40개 추정, 공식 확인 필요)
- 설계: **구독 풀 관리** — 관심종목만 구독, 불필요한 종목은 unsubscribe

## 실전 전환 시 주의

- 실전 API는 **앱키가 다름** — 절대 모의투자 키와 혼용 금지
- 환경변수/프로파일로 엄격히 분리 (`KIS_ENV=paper|live`)
- 실전 전환 전에 **모의로 최소 2주 이상 무인 운영 검증** 필수 (→ `14-roadmap.md`)
- 실전 1주차는 일일 한도를 **통상의 10%**로 제한
