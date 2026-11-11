# Contexto de build: raiz do repositório. Uso: pnpm seed (perfil "seed" do compose).
FROM python:3.15.2-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY scripts/seed/pyproject.toml scripts/seed/pyproject.toml
RUN uv sync --frozen --package katoshop-seed --no-dev

FROM python:3.15.2-slim
RUN useradd --system --uid 10001 --create-home app
WORKDIR /app/scripts
COPY --from=build /app/.venv /app/.venv
COPY scripts/seed/__init__.py scripts/seed/__main__.py scripts/seed/archive_test_data.py scripts/seed/client.py scripts/seed/data.py scripts/seed/images.json ./seed/
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
# Cache das fotos baixadas (volume): a segunda execução não baixa de novo.
RUN mkdir -p /app/scripts/seed/.cache && chown -R app:app /app/scripts/seed/.cache
VOLUME /app/scripts/seed/.cache
USER app
CMD ["python", "-m", "seed"]
