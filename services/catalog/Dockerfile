# Contexto de build: raiz do repositório.
FROM python:3.15.1-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs/py/platform libs/py/platform
COPY services/catalog services/catalog
RUN uv sync --frozen --package catalog --no-dev --no-editable

FROM python:3.15.1-slim
RUN useradd --system --uid 10001 --create-home app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY services/catalog/alembic.ini ./alembic.ini
COPY services/catalog/migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
RUN mkdir -p /data/media && chown -R app:app /data
VOLUME /data/media
USER app
EXPOSE 8000
CMD ["sh","-c","alembic upgrade head && exec uvicorn catalog.main:app --host 0.0.0.0 --port 8000"]
