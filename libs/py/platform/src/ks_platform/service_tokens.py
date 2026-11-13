import asyncio
import math
import time
from collections.abc import Callable
from typing import Any

import httpx

from ks_platform.errors import ProblemError

_RENEW_MARGIN_S = 30.0
_MAX_TTL_S = 3600.0


def _unavailable() -> ProblemError:
    return ProblemError(503, "auth.service_token_unavailable", "Token de serviço indisponível")


class ServiceTokenProvider:
    """Obtém e guarda em memória o token de serviço, renovando 30 s antes de expirar."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        *,
        http: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=2.0)
        self._clock = clock
        self._token: str | None = None
        self._renew_at = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    def _fresh(self) -> bool:
        return self._token is not None and self._clock() < self._renew_at

    async def token(self) -> str:
        if self._token is not None and self._fresh():
            return self._token
        async with self._lock:
            if self._token is not None and self._fresh():
                return self._token  # outra chamada concorrente já renovou
            return await self._refresh()

    async def _refresh(self) -> str:
        requested_at = self._clock()
        try:
            response = await self._http.post(
                self._url,
                json={"client_id": self._client_id, "client_secret": self._client_secret},
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            token = body["access_token"]
            raw_ttl = body["expires_in"]
            if not isinstance(token, str) or not token:
                raise ValueError("access_token inválido")
            if isinstance(raw_ttl, bool) or not isinstance(raw_ttl, int | float):
                raise ValueError("expires_in inválido")
            if not math.isfinite(raw_ttl) or raw_ttl <= 0:
                raise ValueError("expires_in inválido")
            expires_in = min(float(raw_ttl), _MAX_TTL_S)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise _unavailable() from exc
        self._token = token
        self._renew_at = requested_at + expires_in - min(_RENEW_MARGIN_S, expires_in / 2)
        return token
