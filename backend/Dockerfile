FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# The optional Google Sheets worker bind-mounts its service-account file here.
# Docker Desktop requires the target directory to exist before mounting a file.
RUN mkdir -p /run/secrets

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

CMD ["uvicorn", "triage_processor.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
