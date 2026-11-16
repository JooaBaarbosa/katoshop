# Imagem de testes Python em Linux, para máquinas onde a política do Windows
# (Smart App Control) bloqueia extensões nativas do .venv. O código é montado
# em /work; o ambiente virtual fica num volume próprio (/venv).
FROM python:3.15.2-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/venv
# pyright baixa um Node que depende de libatomic.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*
WORKDIR /work
