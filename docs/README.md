# Kronos — 뉴스·공시 분석 기반 자동매매 시스템

> 뉴스·공시·감성 데이터로 시장의 흐름을 먼저 이해한 뒤, 검증된 전략으로 자동매매에 진입.
> 대상: 한국 주식(KOSPI/KOSDAQ) → Phase 10에서 미국 시장 확장
> 언어: Python · 운영: 로컬/개인 서버

## 접근 방식

이 프로젝트는 **거래보다 분석을 먼저** 한다:

1. **Phase 1~3 (약 2개월)**: 뉴스·공시 수집 → 감성분석 → 시장 흐름 모니터링
2. **Phase 4~7**: 시세·백테스트 인프라 + 전략 개발 + 주문·리스크 모듈
3. **Phase 8~9**: 모의투자 4주 검증 → 소액 실전
4. **Phase 10~**: 미국 시장 확장, 고도화

전체 일정은 [14-roadmap.md](./14-roadmap.md) 참조.

## 이 디렉토리는?

`docs/`는 **코드 작성 이전** 단계의 준비 문서 모음입니다. 자동매매는 돈이 직접 오가는 시스템이라, 구현 전에 범위·데이터·리스크·법적 제약을 명확히 기록해두는 것이 시행착오와 사고를 크게 줄여줍니다.

각 문서는 **"어떤 선택지가 있고, 무엇을 골랐으며, 왜 그랬는지"** 기록에 집중합니다.

## 읽기 순서 (추천)

### 1) 프로젝트 이해
- [01-vision-and-scope.md](./01-vision-and-scope.md) — 왜 이 프로젝트를 하는가, 성공 기준
- [02-requirements.md](./02-requirements.md) — 해야 할 일 / 하지 않을 일
- [15-glossary.md](./15-glossary.md) — 용어가 낯설면 먼저 훑어보기

### 2) 시스템 설계
- [03-architecture.md](./03-architecture.md) — 컴포넌트와 데이터 흐름
- [04-data-sources.md](./04-data-sources.md) — 시세·재무·공시·뉴스 데이터 출처
- [05-broker-integration.md](./05-broker-integration.md) — 증권사 API 선택
- [10-tech-stack.md](./10-tech-stack.md) — 라이브러리/DB/도구 결정

### 3) 매매 로직
- [06-strategy-design.md](./06-strategy-design.md) — 4가지 스타일 전략 프레임워크
- [07-analysis-engines.md](./07-analysis-engines.md) — 뉴스 NLP + 기업평가
- [08-backtesting.md](./08-backtesting.md) — 백테스팅 도구와 함정
- [09-risk-management.md](./09-risk-management.md) — **가장 중요한 문서. 꼭 읽을 것**

### 4) 운영·보안·법
- [11-operations.md](./11-operations.md) — 배포, 로깅, 장애 대응
- [12-security.md](./12-security.md) — API 키·자격증명 관리
- [13-legal-and-compliance.md](./13-legal-and-compliance.md) — 법적 고려사항

### 5) 실행 계획
- [14-roadmap.md](./14-roadmap.md) — Phase별 마일스톤과 Definition of Done

## 문서 작성 원칙

- **결정 기록**: 선택지 나열 → 선택 → 이유 순으로 작성
- **미결정은 `TBD`로 명시**하고, 무엇이 블로커인지 기록
- 문서는 짧게, 스캔 가능하게
- 본 문서는 살아있는 문서 — 결정이 바뀌면 갱신

## 면책

본 저장소는 **개인용** 매매 자동화를 위한 기록입니다. 투자 조언이 아니며, 타인 자산 운용 시 관련 법령(자본시장법 등) 확인이 필요합니다. 자세한 내용은 [13-legal-and-compliance.md](./13-legal-and-compliance.md)를 참조하세요.
