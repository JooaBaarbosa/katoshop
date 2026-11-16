# Contexto de build: raiz do repositório.
FROM python:3.15.2-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs/py/platform libs/py/platform
COPY services/cart services/cart
RUN uv sync --frozen --package cart --no-dev --no-editable

FROM python:3.15.2-slim
RUN useradd --system --uid 10001 --create-home app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["sh","-c","exec uvicorn cart.main:app --host 0.0.0.0 --port 8000"]
