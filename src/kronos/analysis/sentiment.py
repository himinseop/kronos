"""KR-FinBERT 기반 한국어 금융 감성 분석.

모델 백엔드(KrFinBertModel)와 순수 로직(라벨 정규화·점수 계산)을 분리해
torch 없이도 모듈 임포트·단위 테스트가 가능하도록 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MODEL_NAME = "snunlp/KR-FinBert-SC"
MODEL_ID = "kr-finbert-sc"  # sentiments.model 컬럼에 기록할 식별자


@dataclass(slots=True)
class SentimentResult:
    label: str  # 'positive' | 'negative' | 'neutral'
    score: float  # -1.0 ~ 1.0  (P(pos) - P(neg))
    confidence: float  # 최대 클래스 확률 0~1


class SentimentModel(Protocol):
    def predict(self, texts: list[str]) -> list[SentimentResult]: ...


def normalize_label(raw: str) -> str:
    """모델별 라벨 문자열을 positive/negative/neutral로 정규화."""
    s = raw.strip().lower()
    if "pos" in s or "긍정" in s:
        return "positive"
    if "neg" in s or "부정" in s:
        return "negative"
    return "neutral"


def result_from_probs(labels: list[str], probs: list[float]) -> SentimentResult:
    """클래스별 (라벨, 확률) → SentimentResult.

    score = P(positive) - P(negative), label = argmax, confidence = max prob.
    """
    norm = [normalize_label(name) for name in labels]
    p_pos = sum(p for name, p in zip(norm, probs, strict=True) if name == "positive")
    p_neg = sum(p for name, p in zip(norm, probs, strict=True) if name == "negative")
    best_idx = max(range(len(probs)), key=lambda i: probs[i])
    return SentimentResult(
        label=norm[best_idx],
        score=round(p_pos - p_neg, 4),
        confidence=round(probs[best_idx], 4),
    )


class KrFinBertModel:
    """transformers 지연 로딩. 첫 predict 시 모델을 메모리에 올린다."""

    def __init__(self, model_name: str = MODEL_NAME, max_length: int = 256):
        self.model_name = model_name
        self.max_length = max_length
        self._pipe = None
        self._labels: list[str] | None = None

    def _ensure_loaded(self) -> None:
        if self._pipe is not None:
            return
        import torch
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        model.eval()

        id2label = model.config.id2label
        self._labels = [id2label[i] for i in range(len(id2label))]
        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model
        self._pipe = True  # 로딩 완료 마커

    def predict(self, texts: list[str]) -> list[SentimentResult]:
        if not texts:
            return []
        self._ensure_loaded()
        torch = self._torch
        enc = self._tokenizer(
            texts,
            truncation=True,
            max_length=self.max_length,
            padding=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = self._model(**enc).logits
            probs = torch.softmax(logits, dim=-1).tolist()

        assert self._labels is not None
        return [result_from_probs(self._labels, row) for row in probs]
