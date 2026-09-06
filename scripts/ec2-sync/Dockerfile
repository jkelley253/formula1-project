FROM ghcr.io/astral-sh/uv:0.11.23 AS uv
FROM python:3.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/packages/lambda-common/pyproject.toml ./packages/lambda-common/pyproject.toml
COPY backend/packages/lambda-common/src ./packages/lambda-common/src
COPY backend/services/drivers/pyproject.toml ./services/drivers/pyproject.toml
COPY backend/services/drivers/src ./services/drivers/src
RUN uv sync --locked --no-dev --no-editable --package formula1-drivers-service
COPY backend/services/drivers/sql/001_create_drivers.sql /setup/001_create_drivers.sql
COPY scripts/ec2-sync/setup_database.py /setup/setup_database.py
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "drivers_service.handlers.ec2_sync"]
