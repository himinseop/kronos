from __future__ import annotations

import hashlib
import re
import unicodedata

_WS = re.compile(r"\s+")
# 한국어 본문에서 흔히 보이는 전각 공백, em/en dash 등 포함 — 의도적
_PUNCT_CHARS = "　 .,!?\"'()[]{}-—–:;"  # noqa: RUF001
_PUNCT = re.compile("[" + re.escape(_PUNCT_CHARS) + "]")


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKC", title).lower().strip()
    t = _PUNCT.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    return t


def article_hash(title: str, url: str | None) -> str:
    canonical = f"{normalize_title(title)}|{url or ''}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
