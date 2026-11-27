# GradPath API image (T-020 step 2b): the FastAPI backend as Render runs it, and as CI builds and
# smoke-tests it. Build from the repo root, because the API reads demo_runs/ and
# knowledge_base/index_info.json from there:
#   docker build -f backend/Dockerfile -t gradpath-api .
#   docker run --rm -p 8000:8000 gradpath-api        # demo mode, no keys needed
# Secrets never go into the image: the root .dockerignore sends only the files named there, and
# keys reach the container as environment variables at run time (Render's dashboard, or -e/--env-file).
# The image holds no index: the deployed API reads Qdrant Cloud through QDRANT_URL.

# Exact versions, pinned by tag and digest, so every build starts from the same bytes.
ARG PYTHON_IMAGE=python:3.13.18-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

FROM ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 AS uv

# Stage 1 (builder): install the locked dependencies and warm the tokenizer cache. uv stays here and
# is not shipped in the final image.
FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    HF_HOME=/app/.cache/huggingface
WORKDIR /app/backend

# Dependencies first: this layer is reused from cache while only our code changes.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Then our package. uv installs it editable, so config.py stays at /app/backend/src/gradpath/ and
# its REPO_ROOT (three folders up) is /app, the same layout as the repo.
COPY backend/src ./src
RUN uv sync --locked --no-dev \
    && .venv/bin/python -m compileall -q src

# The Voyage client downloads its tokenizer from the Hugging Face Hub on first use. Fetch it now, so
# the running container never downloads it (Render's free tier restarts often and loses runtime
# files). The model name comes from the app's own settings, so the two can't drift apart. The key
# is a placeholder: tokenizing is local and never calls Voyage.
RUN .venv/bin/python -c "import voyageai; from gradpath.config import Settings; voyageai.Client(api_key='placeholder').tokenize(['warm-up'], model=Settings().embed_model)"

# Stage 2 (runtime): Python, the installed environment, our code and the two data files. No uv,
# no tests, no build tools.
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/backend/.venv/bin:$PATH \
    HF_HOME=/app/.cache/huggingface \
    HF_HUB_OFFLINE=1

# A normal user, not root: if the app is ever compromised, it can't change the image's files.
RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY --from=builder /app/backend/.venv /app/backend/.venv
COPY --from=builder /app/backend/src /app/backend/src
COPY --from=builder --chown=app:app /app/.cache /app/.cache
COPY demo_runs /app/demo_runs
COPY knowledge_base/index_info.json /app/knowledge_base/index_info.json
# The only folder the API writes to (the route log, logs/routes.jsonl).
RUN mkdir -p /app/logs && chown app:app /app/logs

USER app
EXPOSE 8000
# Render sets PORT; 8000 otherwise. One worker only: background plan runs live in this process's
# memory (workflows/runs.py), so a second worker could not see them. --no-proxy-headers: uvicorn
# must not rewrite the client address from X-Forwarded-For; the app reads that header itself,
# trusting only TRUSTED_PROXY_HOPS entries (api/ratelimit.py, SECURITY.md checklist).
CMD ["sh", "-c", "exec uvicorn gradpath.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-proxy-headers"]
