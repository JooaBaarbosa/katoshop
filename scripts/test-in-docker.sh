#!/usr/bin/env sh
# Roda comandos Python do workspace (pytest, pyright, ruff) num container Linux.
# Uso: scripts/test-in-docker.sh python -m pytest services/promotions -q
# O testcontainers usa o Docker do host pelo socket; os containers de teste
# ficam acessíveis via host.docker.internal.
set -eu
cd "$(dirname "$0")/.."
docker build -q -t katoshop-test-runner -f scripts/test-runner/Dockerfile scripts/test-runner >/dev/null
MSYS_NO_PATHCONV=1 exec docker run --rm \
  -v "$(pwd):/work" \
  -v katoshop-test-venv:/venv \
  -v katoshop-test-uv-cache:/root/.cache/uv \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal \
  -e TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock \
  --add-host host.docker.internal:host-gateway \
  katoshop-test-runner \
  sh -c 'uv sync --locked --all-packages --quiet && uv run --no-sync "$@"' sh "$@"
