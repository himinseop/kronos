FROM python:3.11-slim AS base

# uv 바이너리 (고정 버전)
COPY --from=ghcr.io/astral-sh/uv:0.11.15 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    TZ=Asia/Seoul \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# tzdata: KST 로깅/스케줄 일관성
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# 1) 의존성 레이어 (소스 변경과 분리해 캐시 활용)
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# 데이터·로그 마운트 포인트
RUN mkdir -p /app/data /app/logs

# 기본은 수집 스케줄러. dashboard는 compose에서 command override.
CMD ["kronos", "run"]

# ─────────────────────────────────────────────────────────────
# 감성분석 이미지: base + torch/transformers (extra "analysis")
# 무거운 ML 의존성은 sentiment 서비스에만 포함.
FROM base AS analysis

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra analysis

# HF 모델 캐시는 볼륨(hf_cache)로 주입 → 최초 1회 다운로드 후 재사용
ENV HF_HOME=/app/.hf_cache

CMD ["kronos", "analyze", "run"]
