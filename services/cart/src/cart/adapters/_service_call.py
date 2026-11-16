"""Chamada HTTP autenticada com token de serviço, com um retry após 401."""

from typing import Any

import httpx
import structlog

from ks_platform.errors import ProblemError
from ks_platform.service_tokens import ServiceTokenProvider

log = structlog.get_logger()


class ServiceUnavailableError(Exception):
    """Token, rede, timeout, 5xx ou 401 repetido: o destino não pôde responder."""


async def call_service(
    http: httpx.AsyncClient,
    tokens: ServiceTokenProvider,
    method: str,
    url: str,
    *,
    target: str,
    json: Any = None,
) -> httpx.Response:
    """Devolve a resposta (qualquer status exceto 401 final e 5xx).

    No primeiro 401 (corrida com a expiração do token) invalida o cache e repete uma vez.
    """
    for attempt in (1, 2):
        try:
            token = await tokens.token()
            response = await http.request(
                method, url, json=json, headers={"Authorization": f"Bearer {token}"}
            )
        except (ProblemError, httpx.HTTPError) as exc:
            log.warning("service_call.failed", target=target, error=type(exc).__name__)
            raise ServiceUnavailableError(target) from exc
        if response.status_code == 401 and attempt == 1:
            tokens.invalidate()
            continue
        if response.status_code == 401 or response.status_code >= 500:
            log.warning("service_call.bad_status", target=target, status=response.status_code)
            raise ServiceUnavailableError(target)
        return response
    raise AssertionError("unreachable")  # pragma: no cover
