"""자체 LLM 기반 뉴스 카테고리 분류.

OpenAI 호환 추론 서버(Ollama 등)에 HTTP로 붙어 한국 주식 뉴스 제목을
사전 정의된 카테고리로 분류한다. 순수 로직(프롬프트 구성·응답 파싱·카테고리
정규화)과 네트워크 백엔드를 분리해 서버 없이도 단위 테스트가 가능하다.

같은 추론 서버를 mycomai 등 다른 프로젝트와 공유할 수 있도록 OpenAI /v1
Chat Completions 규격만 사용한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

# 카테고리 분류 결과를 sentiments 테이블에 기록할 때 model 컬럼 prefix.
# 실제 모델명을 붙여 출처를 남긴다 (예: "cat:qwen2.5:3b-instruct").
MODEL_PREFIX = "cat:"


def model_id_for(model_name: str) -> str:
    return f"{MODEL_PREFIX}{model_name}"


# 카테고리 정의: key(저장값) → 한국어 설명(프롬프트용).
CATEGORIES: dict[str, str] = {
    "earnings": "실적 (매출·영업이익·순이익·어닝 서프라이즈/쇼크·잠정실적)",
    "contract": "수주·계약 (공급계약·수주·납품·MOU·파트너십)",
    "ma": "인수합병·지분 (M&A·인수·합병·지분 매각/취득·최대주주 변경)",
    "financing": "자금조달 (유상·무상증자·전환사채·자사주 매입/소각·배당)",
    "regulation": "규제·정책 (정부 규제·인허가·제재·정책 수혜/타격)",
    "product": "신제품·기술 (신제품 출시·기술개발·특허·임상·R&D)",
    "legal": "소송·사건 (소송·횡령·배임·수사·제재·상장폐지 심사)",
    "management": "경영·인사 (대표이사·임원 선임/사임·조직개편·구조조정)",
    "market": "시황·수급 (주가 등락·거래량·외국인/기관 수급·목표주가)",
    "other": "기타 (위 어느 것에도 해당하지 않음)",
}

VALID_CATEGORIES = frozenset(CATEGORIES)


@dataclass(slots=True)
class ClassificationResult:
    category: str  # CATEGORIES의 key 중 하나
    confidence: float  # 0.0 ~ 1.0
    rationale: str  # 한 줄 근거


class CategoryModel(Protocol):
    def classify(self, titles: list[str]) -> list[ClassificationResult]: ...


def normalize_category(raw: str | None) -> str:
    """모델이 뱉은 카테고리 문자열을 유효 key로 정규화. 불명확하면 'other'."""
    if not raw:
        return "other"
    s = raw.strip().lower()
    # 정확 일치 우선
    if s in VALID_CATEGORIES:
        return s
    # 부분 포함 (예: "earnings/실적", "category: contract")
    for key in VALID_CATEGORIES:
        if key in s:
            return key
    # 한국어 키워드 폴백
    ko_map = {
        "실적": "earnings",
        "수주": "contract",
        "계약": "contract",
        "인수": "ma",
        "합병": "ma",
        "지분": "ma",
        "증자": "financing",
        "자사주": "financing",
        "배당": "financing",
        "규제": "regulation",
        "정책": "regulation",
        "신제품": "product",
        "기술": "product",
        "특허": "product",
        "소송": "legal",
        "횡령": "legal",
        "경영": "management",
        "인사": "management",
        "주가": "market",
        "수급": "market",
    }
    for kw, key in ko_map.items():
        if kw in s:
            return key
    return "other"


def build_system_prompt() -> str:
    lines = [
        "너는 한국 주식 시장 뉴스 제목을 분류하는 분석가다.",
        "아래 카테고리 중 제목에 가장 잘 맞는 것 하나를 고른다.",
        "",
        "카테고리:",
    ]
    lines += [f"- {key}: {desc}" for key, desc in CATEGORIES.items()]
    lines += [
        "",
        "반드시 아래 JSON 형식으로만 답한다. 다른 텍스트는 절대 출력하지 않는다.",
        '{"category": "<key>", "confidence": <0~1 실수>, "rationale": "<15자 이내 근거>"}',
        "category 값은 반드시 위 key(영문) 중 하나여야 한다.",
    ]
    return "\n".join(lines)


def build_user_prompt(title: str) -> str:
    return f"뉴스 제목: {title}\n\n위 제목의 카테고리를 JSON으로 분류하라."


def build_batch_system_prompt(*, include_rationale: bool = False) -> str:
    """여러 제목을 한 번에 분류하는 배치용 시스템 프롬프트.

    include_rationale=False면 근거 문장을 요구하지 않아 출력 토큰이 크게
    줄어 처리 속도가 2배 이상 빨라진다 (대량 백필 기본값).
    """
    lines = [
        "너는 한국 주식 시장 뉴스 제목을 분류하는 분석가다.",
        "번호가 매겨진 여러 제목을 각각 아래 카테고리 하나로 분류한다.",
        "",
        "카테고리:",
    ]
    lines += [f"- {key}: {desc}" for key, desc in CATEGORIES.items()]
    if include_rationale:
        schema = (
            '{"results": [{"i": 1, "category": "<key>", "confidence": <0~1>, '
            '"rationale": "<15자 이내>"}, ...]}'
        )
    else:
        schema = '{"results": [{"i": 1, "category": "<key>", "confidence": <0~1>}, ...]}'
    lines += [
        "",
        "반드시 아래 JSON 형식으로만 답한다. 다른 텍스트는 절대 출력하지 않는다.",
        "입력 제목 수와 배열 길이가 정확히 같아야 하며, i는 입력 번호와 일치해야 한다.",
        schema,
        "category 값은 반드시 위 key(영문) 중 하나여야 한다.",
    ]
    return "\n".join(lines)


def build_batch_user_prompt(titles: list[str]) -> str:
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    return f"다음 {len(titles)}개 제목을 각각 분류하라:\n{numbered}"


def _result_from_obj(obj: dict) -> ClassificationResult:
    category = normalize_category(str(obj.get("category", "")))
    rationale = str(obj.get("rationale", "")).strip()[:200]
    try:
        confidence = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return ClassificationResult(
        category=category,
        confidence=round(confidence, 4),
        rationale=rationale,
    )


def parse_response(text: str) -> ClassificationResult:
    """단건 모델 응답 → ClassificationResult. JSON 파싱 실패 시 폴백."""
    obj = _extract_json(text)
    if obj is not None:
        return _result_from_obj(obj)
    # JSON 실패 → 자유 텍스트에서 카테고리만 추정
    return ClassificationResult(
        category=normalize_category(text),
        confidence=0.0,
        rationale=text.strip()[:200],
    )


def parse_batch_response(text: str, n: int) -> list[ClassificationResult] | None:
    """배치 응답 → n개의 ClassificationResult(입력 순서대로).

    길이 불일치·파싱 실패 시 None을 반환해 호출측이 개별 폴백하도록 한다.
    """
    obj = _extract_json(text)
    if obj is None:
        return None
    raw = obj.get("results") if isinstance(obj, dict) else None
    if not isinstance(raw, list):
        return None

    # i(1-based) → 결과 매핑. i가 없으면 등장 순서로 배치.
    by_index: dict[int, ClassificationResult] = {}
    for pos, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        idx = item.get("i")
        try:
            idx = int(idx) if idx is not None else pos + 1
        except (TypeError, ValueError):
            idx = pos + 1
        by_index[idx] = _result_from_obj(item)

    # 하나라도 못 채우면 실패로 간주 (정렬 신뢰성 우선)
    if len(by_index) < n or any(i not in by_index for i in range(1, n + 1)):
        return None
    return [by_index[i] for i in range(1, n + 1)]


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    # 먼저 전체를 시도, 실패하면 최외곽 { } 블록을 추출 (greedy)
    for candidate in (text, *(m.group(0) for m in _JSON_RE.finditer(text))):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


class LlmCategoryClassifier:
    """OpenAI 호환 /v1 Chat Completions 엔드포인트로 분류.

    Ollama(http://localhost:11434/v1) 기본. 여러 제목을 한 호출에 묶어
    처리하고(chunk_size), 배치 응답 파싱이 실패하면 해당 청크를 개별
    호출로 폴백한다. httpx 클라이언트는 지연 생성.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 60.0,
        chunk_size: int = 15,
        include_rationale: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.chunk_size = chunk_size
        self._client = None
        self._system = build_system_prompt()
        self._batch_system = build_batch_system_prompt(include_rationale=include_rationale)

    def _ensure_client(self):
        if self._client is not None:
            return
        import httpx

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=self.timeout)

    def _complete(self, system: str, user: str) -> str:
        self._ensure_client()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        resp = self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _classify_one(self, title: str) -> ClassificationResult:
        return parse_response(self._complete(self._system, build_user_prompt(title)))

    def _classify_chunk(self, titles: list[str]) -> list[ClassificationResult]:
        content = self._complete(self._batch_system, build_batch_user_prompt(titles))
        parsed = parse_batch_response(content, len(titles))
        if parsed is not None:
            return parsed
        # 배치 정렬 실패 → 개별 호출 폴백
        return [self._classify_one(t) for t in titles]

    def classify(self, titles: list[str]) -> list[ClassificationResult]:
        out: list[ClassificationResult] = []
        for i in range(0, len(titles), self.chunk_size):
            out.extend(self._classify_chunk(titles[i : i + self.chunk_size]))
        return out

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
