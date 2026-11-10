# LifeOps insights-api image.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/lifeops

COPY pyproject.toml README.md ./
COPY lifeops_core ./lifeops_core
RUN pip install --no-cache-dir .

# ---------------------------------------------------------------- runtime --
FROM base AS runtime

COPY services/insights_api/insights_app ./insights_app
EXPOSE 8001
CMD ["uvicorn", "insights_app.main:app", "--host", "0.0.0.0", "--port", "8001"]

# ------------------------------------------------------------------- dev --
FROM base AS dev

RUN pip install --no-cache-dir ".[dev]"
CMD ["uvicorn", "insights_app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
