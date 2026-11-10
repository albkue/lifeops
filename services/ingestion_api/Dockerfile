# LifeOps ingestion-api image.
# Build from the REPO ROOT: docker build -f services/ingestion_api/Dockerfile .
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/lifeops

# Runtime dependencies + shared kernel (installed once, cached between stages)
COPY pyproject.toml README.md ./
COPY lifeops_core ./lifeops_core
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts

# ---------------------------------------------------------------- runtime --
FROM base AS runtime

COPY services/ingestion_api/ingestion_app ./ingestion_app
EXPOSE 8000
CMD ["uvicorn", "ingestion_app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ------------------------------------------------------------------- dev --
FROM base AS dev

RUN pip install --no-cache-dir ".[dev]"
COPY scripts ./scripts
CMD ["pytest", "tests/unit"]
