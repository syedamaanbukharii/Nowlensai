# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder: install the package and its dependencies into a virtualenv.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build deps for any packages without manylinux wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only what's needed to resolve dependencies first (better layer caching).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# ---------------------------------------------------------------------------
# Runtime: copy the venv and source, run as a non-root user.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 nowlens

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=nowlens:nowlens src ./src
COPY --chown=nowlens:nowlens alembic.ini ./
COPY --chown=nowlens:nowlens pyproject.toml README.md ./

USER nowlens
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/live || exit 1

# Use the uvicorn worker via the CLI. Override the command for migrations etc.
CMD ["nowlens", "serve", "--host", "0.0.0.0", "--port", "8000"]
