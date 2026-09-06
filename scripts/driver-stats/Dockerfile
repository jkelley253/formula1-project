FROM ghcr.io/astral-sh/uv:0.11.23 AS uv
FROM python:3.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/packages/lambda-common/pyproject.toml ./packages/lambda-common/pyproject.toml
COPY backend/packages/lambda-common/src ./packages/lambda-common/src
COPY backend/services/drivers/pyproject.toml ./services/drivers/pyproject.toml
COPY backend/services/driver_stats/pyproject.toml ./services/driver_stats/pyproject.toml
COPY backend/services/driver_stats/src ./services/driver_stats/src
RUN uv sync --locked --no-dev --no-editable --package formula1-driver-stats-service
COPY backend/services/driver_stats/sql/001_create_driver_stats.sql /setup/schema.sql
COPY scripts/driver-stats/setup_database.py /setup/setup_database.py
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "driver_stats_service.handlers.ec2_sync"]
