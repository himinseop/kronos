# 12. 보안

## 위협 모델

자동매매 시스템의 주요 위협:

1. **API 키 유출** → 타인이 내 계좌로 주문
2. **계좌 자격증명 유출** → 직접 출금 · 이체
3. **코드 저장소 유출** → 전략 + 키까지 한 번에
4. **악성 의존성** → 임포트 시 키 탈취
5. **로그 누출** → 민감정보 외부 유출
6. **머신 손실/도난** → 로컬 파일 접근

## 자격증명 관리

### 저장 위치 우선순위

1. **OS 키체인** (권장)
   - macOS: Keychain
   - Linux: `libsecret` / GNOME Keyring
   - `keyring` 파이썬 패키지 활용
2. **환경변수** (`.env` 로컬 파일)
3. **설정 파일** — **절대 비권장**, 특히 git 커밋 금지

### `.env` 사용 시
- 파일 권한 `chmod 600`
- 저장소에는 `.env.example` (더미값)만 커밋
- `.gitignore`에 `.env` 반드시 등록

## `.gitignore` 필수 항목

```gitignore
# 비밀 정보
.env
.env.*
!.env.example
secrets/
configs/live.yaml
configs/*.secret.yaml

# 자격증명
*.pem
*.key
credentials.json

# 데이터베이스
*.db
*.sqlite
data/

# 로그
logs/
*.log

# 파이썬
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# IDE
.idea/
.vscode/
```

## Pre-commit 훅 (비밀 탐지)

- **gitleaks** 또는 **detect-secrets**: 커밋 전 키 문자열 탐지
- **trufflehog**: 히스토리 스캔
- pre-commit 설정 권장:
  ```yaml
  - repo: https://github.com/gitleaks/gitleaks
    hooks: [id: gitleaks]
  ```

## 코드 내 시크릿 접근

```python
# 좋음
import os
APP_KEY = os.environ["KIS_APP_KEY"]

# 더 좋음: pydantic-settings
class Settings(BaseSettings):
    kis_app_key: SecretStr
    kis_app_secret: SecretStr
    model_config = SettingsConfigDict(env_file=".env")
```

- 로깅 시 `SecretStr`이면 자동 마스킹
- 예외 메시지에도 키가 섞이지 않도록 주의

## 실전 / 모의투자 분리

- **별도 앱키** 사용 (공유 금지)
- 실전 설정은 별도 파일 + 별도 환경변수 프리픽스 (`LIVE_KIS_*`, `PAPER_KIS_*`)
- 코드에서 `ENV=live`일 때 추가 **확인 프롬프트** (CLI 시작 시 `--confirm-live` 플래그)

## 로그 마스킹

민감정보는 로그·알림에서 마스킹:

| 항목 | 마스킹 예시 |
|---|---|
| 계좌번호 | `1234-56-****-12` (뒤 4자리만 가림) |
| API 키 | `****` (전면 가림) |
| 주민번호 / 법인번호 | 전면 가림 |
| 전화번호 | 가운데 가림 |

**주문·체결 로그**는 계좌번호 대신 **내부 해시 ID**로 기록.

## 네트워크 보안

### 원격 접근 정책

본 프로젝트의 모든 외부 접근(SSH, dashboard 등)은 **Tailscale 메시 사설망**을 통해서만 허용한다. 공인 인터넷에 직접 포트를 열지 않는다.

| 서비스 | 노출 경로 | 인증 |
|---|---|---|
| SSH (포트 22) | LAN(192.168.0.x) + tailnet(100.x) | SSH 키 |
| Dashboard (Streamlit) | `127.0.0.1:8501` → `tailscale serve`가 HTTPS로 tailnet에만 프록시 | tailnet 디바이스 멤버십 |
| 기타 로컬 서비스 | 기본 `127.0.0.1` 바인딩, 필요 시 `tailscale serve`로 노출 | 동일 |

- **공인망 직접 노출 금지**: 라우터에 포트 포워딩 설정하지 않는다. `tailscale funnel`(공인망 노출 기능)도 사용 안 함
- Tailscale ACL: 본인 계정의 디바이스만. 사용자 추가 시 ACL 명시적 검토
- Tailscale 계정 자체는 OAuth 제공자(Google/GitHub 등) 2FA로 보호

### 로컬 운영
- 방화벽: 인바운드 포트 기본 차단
- 대시보드는 `127.0.0.1`에만 바인딩 (외부 노출 금지)
- Tailscale은 **App Store 또는 standalone(.pkg) GUI 버전** 사용 (`docs/11-operations.md` 참조)
  - 두 GUI 버전 모두 sandbox에서 동작 — `tailscale up --ssh` 서버 기능 미지원
  - 대신 macOS Remote Login(시스템 설정 → 일반 → 공유)을 켜고 표준 sshd가 tailnet 인터페이스에서 listen하도록 함

### SSH 키 정책
- macOS 비밀번호 인증보다 SSH 키 인증 권장
- `~/.ssh/authorized_keys`에 등록된 키만 접속 허용 (필요 시 `/etc/ssh/sshd_config`에서 `PasswordAuthentication no`)
- 키 분실·디바이스 도난 시 즉시 `authorized_keys`에서 해당 줄 삭제

## 의존성 보안

- `pip-audit` 또는 `uv audit`로 CVE 스캔
- 새 라이브러리 추가 시:
  - 다운로드 수, 최근 커밋, 이슈 확인
  - 금융 API 래퍼는 **공식 저장소** 위주
- 월 1회 의존성 업데이트 + 회귀 테스트

## 2FA / 접근 제어

- 한국투자증권 로그인 OTP 설정
- GitHub 계정 2FA (소스 유출 방지)
- 키체인 · 비밀번호 관리자 (1Password/Bitwarden) 마스터 암호 강화

## 디바이스 보안

- 디스크 전체 암호화 (FileVault / LUKS)
- 화면 잠금 자동
- **개인 PC**에 매매 시스템이 있다면 해당 PC에 다른 사람 접근 금지

## 사고 대응 플레이북

### 키 유출 의심 시 **즉시**:
1. 한국투자증권 고객센터 연락 → **계좌 매매 정지**
2. KIS Developers에서 앱키 **폐기 및 재발급**
3. 비밀번호·OTP 재설정
4. 최근 거래 내역 확인 (이상 주문 여부)
5. 시스템 매매 중단, 로그·git 히스토리 분석하여 유출 경로 추적

### 저장소 유출 시
1. git 히스토리에서 비밀 삭제 (BFG/`git filter-repo`)
2. **유출된 모든 자격증명 교체** (히스토리 삭제만으로는 불충분)
3. 저장소 private 상태 재검증

## 정기 점검

- [ ] 월 1회: 의존성 취약점 스캔 (`pip-audit`)
- [ ] 월 1회: 저장소에 비밀 커밋되었는지 스캔 (`gitleaks detect`)
- [ ] 분기 1회: 앱키 로테이션
- [ ] 분기 1회: 접근 권한 리뷰 (불필요한 토큰 폐기)

## 금지 사항

- 본인 계좌 자격증명을 **타인에게 전달하지 않는다**
- **클라우드 IDE**(Replit 등)에 실전 키 업로드 금지
- 공용 Wi-Fi에서 실전 API 호출 금지 (개발은 모의투자로)
- 로그 전체를 외부 SaaS로 전송하기 전 마스킹 검증
