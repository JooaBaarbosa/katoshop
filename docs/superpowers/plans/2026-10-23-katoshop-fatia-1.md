# KatoShop Fatia 1 (vitrine navegável) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar a fatia 1 do KatoShop. Ela inclui:
- a fundação do monorepo;
- os serviços identity e catalog;
- o gateway e a observabilidade;
- a loja navegável e o admin de catálogo;
- o seed com fotos reais creditadas e o e2e.

Tudo sobe com `docker compose up`.

**Architecture:**
- **Backend:** dois serviços FastAPI (identity, catalog), cada um com banco Postgres próprio, atrás do Traefik. Cada serviço valida o JWT EdDSA sozinho, usando as chaves públicas do identity através da lib compartilhada `ks_platform`.
- **Frontend:** duas apps Next.js funcionam como BFF. O navegador só fala com o Next, que guarda os tokens em cookies httpOnly e chama o gateway no servidor com um cliente tipado gerado do OpenAPI.
- **Observabilidade:** OpenTelemetry → Collector → Jaeger (traces) e Prometheus (métricas) → Grafana.

**Tech Stack:**
- **Backend:** Python 3.15.1, uv, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, Pydantic v2, PyJWT (EdDSA), argon2-cffi, structlog, OpenTelemetry, pytest + testcontainers.
- **Frontend:** Next.js 16 + React 19, TypeScript 7, Tailwind 4, shadcn/ui, openapi-typescript/openapi-fetch, Vitest, Playwright.
- **Infra:** Traefik 3.7, Postgres 18.6, Jaeger 2, Prometheus 3, Grafana 13.

**Spec:** `docs/superpowers/specs/2026-10-23-katoshop-design.md`. Leia as seções 4, 6 e 8 antes de qualquer tarefa. Este plano decide os nomes e as interfaces que a spec deixa em aberto.

## Global Constraints

- Versões exatas da seção 5 da spec. Dependências de apoio conferidas em 2026-10-23:

  | Pacote | Versão |
  |---|---|
  | pillow | 13.0.0 |
  | python-multipart | 0.0.32 |
  | opentelemetry-exporter-otlp-proto-grpc | 1.45.1 |
  | opentelemetry-instrumentation-sqlalchemy, -httpx, -asyncpg | 0.66b1 |
  | asgi-lifespan | 2.1.0 |
  | vitest | 5.0.5 |
  | @vitejs/plugin-react | 6.1.2 |
  | @testing-library/react | 16.3.3 |
  | jsdom | 30.1.3 |
  | @vercel/otel | 2.1.3 |
  | eslint | 10.13.0 |
  | eslint-config-next | 16.4.3 |
  | prettier | 3.9.10 |
  | @lhci/cli | 0.15.1 |
  | actions/upload-artifact | v7.0.2 |

  Antes de fixar, rode a consulta ao registry de novo. Se houver estável mais nova, use a nova e anote no commit.
- Python `requires-python = ">=3.15,<3.16"`, `.python-version` `3.15.1`, imagem base `python:3.15.1-slim`. Node 24.22.1, com `"packageManager": "pnpm@12.15.0"`.
- **Nome de import da lib compartilhada:** `ks_platform` (distribuição `katoshop-platform`, pasta `libs/py/platform`). Nunca `platform`, que colide com a stdlib.
- **API:**
  - prefixo `/v1`, JSON em snake_case;
  - erros `application/problem+json` com `code` estável no formato `<serviço>.<área>.<motivo>`;
  - dinheiro em inteiros `_cents`;
  - IDs UUIDv7 (`uuid.uuid7()` da stdlib 3.14+);
  - `timestamptz` em UTC;
  - paginação por cursor com `limit` padrão 24 e máximo 100.
- **JWT:**
  - `iss = "katoshop-identity"`, `aud ∈ {"storefront","admin"}`, algoritmo `EdDSA`;
  - claims `sub`, `aud`, `exp`, `iat`, `jti`, `roles` (lista), `kind` (`customer`|`staff`);
  - header `kid`;
  - access token de 900 s.
- **Permissão de escrita no catálogo:** `catalog.write`. O papel `admin` concede `*`.
- **Hosts:** `katoshop.localhost` (loja), `admin.katoshop.localhost` (admin), `api.katoshop.localhost` (gateway; prefixos `/identity` e `/catalog` removidos pelo Traefik).
- **UI (regras do `CLAUDE.md` e da spec seção 6):**
  - sem botão pílula (raio 2px), sem gradiente roxo e sem emoji como ícone (usar lucide-react);
  - sem travessão (— ou –) em texto de UI ou documentação pública;
  - sem avaliações, métricas ou contadores falsos;
  - transições ≤150 ms com `prefers-reduced-motion` respeitado;
  - fotos reais creditadas;
  - rodapé da loja com "Loja demonstrativa, nenhuma compra é real";
  - selo "dados demo" no admin.
- **Textos de UI** em pt-BR. Código e identificadores em inglês.
- **Commits** pequenos por tarefa, mensagem em pt-BR no formato `tipo(escopo): descrição`, com a linha de atribuição exigida pelo harness.
- **Testes de integração** usam Docker (testcontainers com `postgres:18.6-alpine`). O Docker Desktop precisa estar rodando.

## Review Focus

1. **Busca com entrada "estranha"** (`q` vazio, só espaços, `"&|!"`, aspas, 200 caracteres): sem 500. `q` vazio equivale a sem busca, e `q` com mais de 200 caracteres retorna 422 `catalog.search.query_too_long`. Teste na Tarefa 14.
2. **Cursor de paginação adulterado, truncado ou gerado com outra ordenação:** retorna 422 `catalog.pagination.invalid_cursor`, nunca 500. Teste na Tarefa 14.
3. **Dois ajustes de estoque simultâneos na mesma variante:** nenhum se perde e o saldo nunca fica negativo (lock `SELECT ... FOR UPDATE`). Teste na Tarefa 12.
4. **Duas abas renovando o mesmo refresh token ao mesmo tempo:** o usuário não deve ser deslogado. Reuso dentro de 10 s do primeiro uso emite um novo par na mesma família, sem revogar; depois de 10 s, revoga a família. Teste na Tarefa 8.
5. **Enumeração de contas no login:** email inexistente, senha errada e conta bloqueada devolvem a mesma resposta 401 `identity.auth.invalid_credentials`. Email inexistente também verifica um hash fictício, para não vazar pelo tempo de resposta. Teste na Tarefa 9.

---

## Mapa de arquivos

```
katoshop/
  pyproject.toml                      workspace uv (membros libs/py/platform, services/*)
  .python-version  LICENSE  README.md  .editorconfig  .env.example
  package.json  pnpm-workspace.yaml  turbo.json
  libs/py/platform/src/ks_platform/
    settings.py  errors.py  health.py  auth.py  observability.py  http.py  db.py  testing.py
  services/identity/src/identity/
    main.py  settings.py  cli.py
    domain/passwords.py  domain/lockout.py  domain/tokens.py  domain/data/common-passwords.txt
    application/ports.py  application/auth_service.py
    adapters/models.py  adapters/repositories.py  adapters/signing.py
    api/routes_auth.py  api/routes_me.py  api/routes_jwks.py  api/schemas.py
  services/catalog/src/catalog/
    main.py  settings.py
    domain/slugs.py  domain/variants.py  domain/stock.py  domain/publishing.py  domain/images.py  domain/settings_schema.py
    application/ports.py  application/admin_service.py
    adapters/models.py  adapters/repositories.py  adapters/product_queries.py  adapters/storage_local.py
    api/routes_public.py  api/routes_admin.py  api/routes_media.py  api/schemas.py
  services/*/migrations/  services/*/tests/{unit,integration,api}/  services/*/Dockerfile
  packages/config/  packages/ui/  packages/api-client/
  apps/storefront/  apps/admin/
  e2e/                                Playwright + Lighthouse CI
  infra/compose.yaml  infra/traefik/  infra/postgres-init/  infra/otel/  infra/prometheus/  infra/grafana/
  scripts/gen_keys.py  scripts/export_openapi.py  scripts/seed/
  docs/adr/0001..0006
  .github/workflows/ci-platform.yml  ci-identity.yml  ci-catalog.yml  ci-web.yml  ci-e2e.yml
```

---

### Task 1: Fundação do monorepo

**Files:**
- Create: `pyproject.toml`, `.python-version`, `LICENSE` (MIT, "Copyright (c) 2026 KatoShop contributors"), `.editorconfig`, `.env.example`, `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `packages/config/{tsconfig.base.json,eslint.config.mjs,prettier.config.mjs,package.json}`, `libs/py/platform/pyproject.toml`, `libs/py/platform/src/ks_platform/__init__.py`, `libs/py/platform/tests/test_smoke.py`, `.github/workflows/ci-platform.yml`
- Modify: `.gitignore` (adicionar `infra/secrets/`, `.turbo/`, `.next/`, `test-results/`, `playwright-report/`, `.lighthouseci/`, `media-data/`)

**Interfaces:**
- Produces:
  - workspace uv com `[tool.uv.workspace] members = ["libs/py/platform", "services/*"]`;
  - ruff (`line-length = 100`, `target-version = "py315"`, regras `E,F,I,B,UP,S,ASYNC`) e pyright na raiz;
  - pnpm workspace com `apps/*`, `packages/*`, `e2e`;
  - scripts raiz `dev:up`, `dev:down`, `seed`, `gen:api`, `test:e2e`. Cada um é preenchido na tarefa que entrega o alvo; aqui ficam como `echo "pendente"`.

- [ ] **Step 1:** Escrever `libs/py/platform/tests/test_smoke.py` com `def test_package_imports(): import ks_platform; assert ks_platform.__name__ == "ks_platform"`.
- [ ] **Step 2:** Rodar `uv sync --all-packages && uv run pytest libs/py/platform -q`. Esperado: o pacote ainda não está configurado, então o comando falha.
- [ ] **Step 3:** Criar os arquivos da lista. Em `ci-platform.yml`, disparar em `push`/`pull_request` com `paths: [libs/py/platform/**, pyproject.toml, uv.lock]`. Os passos são `actions/checkout@v7.0.1`, `astral-sh/setup-uv@v10.3.2` com Python 3.15.1, `uv sync --all-packages`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright libs/py/platform` e `uv run pytest libs/py/platform -q`.
- [ ] **Step 4:** Rodar `uv sync --all-packages && uv run pytest libs/py/platform -q && uv run ruff check . && pnpm install`. Esperado: `1 passed`, ruff sem erros e o pnpm instala sem erro.
- [ ] **Step 5:** Commit `chore: fundação do monorepo (uv + pnpm + turbo, licença MIT)`.

### Task 2: ks_platform, settings, erros problem+json e health

**Files:**
- Create: `libs/py/platform/src/ks_platform/{settings.py,errors.py,health.py}`
- Test: `libs/py/platform/tests/test_errors.py`, `test_health.py`

**Interfaces:**
- Produces:
  - `class BaseServiceSettings(BaseSettings)`: `service_name: str`, `database_url: str`, `jwks_url: str`, `otel_endpoint: str | None = None`, `log_level: str = "INFO"`. Cada serviço define o prefixo de env em `model_config`.
  - `class ProblemError(Exception)`: `__init__(self, status: int, code: str, title: str, detail: str | None = None, errors: dict[str, list[str]] | None = None)`.
  - `install_problem_handlers(app: FastAPI) -> None`. Corpo da resposta: `{"type": "about:blank", "title", "status", "detail", "code", "trace_id", "errors"?}` com `media_type="application/problem+json"`. Mapeamentos:
    - `RequestValidationError` → 422 `request.validation` com `errors` indexado pelo caminho do campo (`"body.email"`);
    - `HTTPException` → mesmo status com `code = "http.<status>"`;
    - exceção não tratada → 500 `internal.error`, sem detalhe interno.
  - `health_router(ready_check: Callable[[], Awaitable[bool]]) -> APIRouter` com `GET /health/live` → 200 `{"status":"ok"}` e `GET /health/ready` → 200, ou 503 `{"status":"unavailable"}`.

- [ ] **Step 1:** Escrever os testes com uma app FastAPI mínima e `httpx.AsyncClient(transport=ASGITransport(app))`:
  - `test_problem_error_rendered`: rota que levanta `ProblemError(409, "x.y.z", "Conflito")` → status 409, header `content-type` começa com `application/problem+json` e `body["code"] == "x.y.z"`;
  - `test_validation_error_maps_fields`: POST com body sem `email` → 422, `code == "request.validation"`, `"body.email" in body["errors"]`;
  - `test_unhandled_error_hides_details`: rota com `raise RuntimeError("segredo")` → 500, `"segredo" not in response.text`;
  - `test_ready_returns_503_when_check_fails`.
- [ ] **Step 2:** Rodar `uv run pytest libs/py/platform -q`. Esperado: FAIL por `ImportError`.
- [ ] **Step 3:** Implementar `settings.py`, `errors.py` e `health.py` com as assinaturas acima. O `trace_id` vem de `opentelemetry.trace.get_current_span().get_span_context().trace_id` formatado em 32 hex, ou `None` quando inválido.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(platform): problem+json, settings base e health`.

### Task 3: ks_platform, verificação de JWT e principal

**Files:**
- Create: `libs/py/platform/src/ks_platform/auth.py`
- Test: `libs/py/platform/tests/test_auth.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Principal`: `user_id: UUID`, `audience: Literal["storefront","admin"]`, `kind: Literal["customer","staff"]`, `roles: frozenset[str]`, com `def has_permission(self, perm: str) -> bool`.
  - `ROLE_PERMISSIONS: dict[str, frozenset[str]] = {"admin": frozenset({"*"})}`.
  - `class JwksKeyProvider`: `__init__(self, jwks_url: str, fetch: Callable[[str], Awaitable[dict]] | None = None, ttl_seconds: int = 300, min_refetch_seconds: int = 30)` e `async def get_key(self, kid: str) -> Ed25519PublicKey`. Com `kid` desconhecido, refaz o fetch uma vez, respeitando `min_refetch_seconds`; se continuar desconhecido, levanta `ProblemError(401, "auth.invalid_token", ...)`.
  - `class TokenVerifier`: `__init__(self, keys: JwksKeyProvider, issuer: str = "katoshop-identity")` e `async def verify(self, token: str, audience: str) -> Principal`.
  - Dependências FastAPI:
    - `def require_audience(audience: str) -> Callable[..., Awaitable[Principal]]` lê `Authorization: Bearer` e usa `request.app.state.token_verifier`. Sem token: 401 `auth.missing_token`. Inválido, expirado ou com audiência errada: 401 `auth.invalid_token`;
    - `def require_permission(perm: str, audience: str = "admin")`: 403 `auth.forbidden` se faltar a permissão.
- Consumes: `ProblemError` (Tarefa 2).

- [ ] **Step 1:** Escrever os testes. Eles geram um par Ed25519 com `cryptography`, montam o JWKS (`{"keys":[{"kty":"OKP","crv":"Ed25519","x":<b64url>,"kid":"k1","alg":"EdDSA","use":"sig"}]}`) e usam um `fetch` falso que conta as chamadas.
  - `test_valid_token_returns_principal`: roles `["admin"]` → `principal.has_permission("catalog.write") is True`;
  - `test_expired_token_rejected` → `ProblemError` com status 401;
  - `test_wrong_audience_rejected`: token `storefront` verificado com `audience="admin"` → 401;
  - `test_unknown_kid_refetches_once`: a primeira resposta do fetch não tem `k2`, a segunda tem → sucesso e `fetch_calls == 2`;
  - `test_unknown_kid_refetch_is_throttled`: dois tokens com `kid` inexistente em sequência → o segundo não dispara fetch novo;
  - `test_customer_role_lacks_permission`: roles `[]` → `require_permission("catalog.write")` responde 403 numa rota de teste.
- [ ] **Step 2:** Rodar `uv run pytest libs/py/platform/tests/test_auth.py -q`. Esperado: FAIL.
- [ ] **Step 3:** Implementar com `jwt.decode(token, key, algorithms=["EdDSA"], audience=audience, issuer=issuer, options={"require": ["exp","iat","sub","aud","iss","jti"]})`. O fetch padrão usa `httpx.AsyncClient(timeout=2.0)`.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(platform): verificação de JWT EdDSA com cache de JWKS`.

### Task 4: ks_platform, observabilidade, cliente HTTP, banco e testing

**Files:**
- Create: `libs/py/platform/src/ks_platform/{observability.py,http.py,db.py,testing.py}`
- Test: `libs/py/platform/tests/test_observability.py`, `test_http.py`

**Interfaces:**
- Produces:
  - `configure_logging(service_name: str, level: str) -> None`. structlog em JSON, com processador que injeta `trace_id`/`span_id` do span atual e um filtro que troca por `"[redacted]"` os valores de chaves `password`, `token`, `refresh_token`, `access_token` e `authorization`.
  - `configure_observability(app: FastAPI, settings: BaseServiceSettings, engine: AsyncEngine | None = None) -> None`. Define `TracerProvider` e `MeterProvider` com exportador OTLP gRPC para `settings.otel_endpoint` (no-op quando `None`) e instrumenta FastAPI, httpx, SQLAlchemy e asyncpg.
  - `make_http_client(base_url: str, timeout_s: float = 2.0) -> httpx.AsyncClient`. Faz um retry só para `GET` em `httpx.ConnectError`.
  - `make_engine(url: str) -> AsyncEngine` e `make_session_factory(engine) -> async_sessionmaker[AsyncSession]` (`expire_on_commit=False`).
  - `ks_platform.testing`:
    - fixture pytest `postgres_url` (escopo de sessão, `PostgresContainer("postgres:18.6-alpine", driver="asyncpg")`);
    - `def run_migrations(alembic_ini: Path, url: str) -> None`;
    - fixture `asgi_client(app) -> httpx.AsyncClient` usando `asgi_lifespan.LifespanManager`.
  - Os serviços registram `pytest_plugins = ["ks_platform.testing"]` no `conftest.py`.

- [ ] **Step 1:** Escrever os testes:
  - `test_log_contains_trace_id`: dentro de um span, `structlog.get_logger().info("x")` → o JSON capturado tem `trace_id` com 32 hex;
  - `test_log_redacts_secrets`: `log.info("x", password="abc", refresh_token="def")` → `"abc"` e `"def"` não aparecem na saída;
  - `test_http_client_propagates_traceparent`: `httpx.MockTransport` captura o header `traceparent` dentro de um span;
  - `test_http_client_retries_get_once_on_connect_error`: o transporte falha uma vez e depois responde 200 → 2 chamadas. Com POST → 1 chamada e a exceção é propagada.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar. A propagação usa `opentelemetry.propagate.inject` num event hook `request` do httpx, para não depender só da instrumentação.
- [ ] **Step 4:** Rodar `uv run pytest libs/py/platform -q && uv run pyright libs/py/platform`. Esperado: PASS e 0 erros.
- [ ] **Step 5:** Commit `feat(platform): logs JSON com trace, OTel, cliente HTTP e utilitários de teste`.

### Task 5: identity, esqueleto do serviço, modelos e migração

**Files:**
- Create: `services/identity/{pyproject.toml,Dockerfile,alembic.ini}`, `services/identity/migrations/{env.py,versions/0001_initial.py}`, `src/identity/{__init__.py,main.py,settings.py}`, `src/identity/adapters/models.py`, `tests/conftest.py`, `tests/integration/test_migrations.py`, `.github/workflows/ci-identity.yml`

**Interfaces:**
- Produces:
  - `class IdentitySettings(BaseServiceSettings)`: prefixo `IDENTITY_`, `signing_key_path: Path`, `bootstrap_admin_email: str | None`, `bootstrap_admin_password: str | None`, `cookie_secure: bool = False`.
  - `create_app(settings: IdentitySettings | None = None) -> FastAPI`. Registra os handlers de problema, a observabilidade e o health (o ready faz `SELECT 1`), e guarda `app.state.session_factory`.
  - Tabelas conforme a spec 8.2: `users`, `roles`, `user_roles`, `refresh_tokens`, `signing_keys`. Detalhes:
    - `users.email` com índice único em `lower(email)`;
    - `refresh_tokens.token_hash` único e índice em `family_id`;
    - `refresh_tokens.first_used_at timestamptz null` (para a janela de 10 s);
    - a migração insere o papel `admin`.
  - Dockerfile multi-stage: `uv sync --frozen --package identity`, depois `CMD ["sh","-c","alembic upgrade head && uvicorn identity.main:app --host 0.0.0.0 --port 8000"]`, com usuário não root.

- [ ] **Step 1:** Escrever `test_migrations.py`:
  - `test_upgrade_creates_tables`: `run_migrations` contra `postgres_url`, depois `inspect` → as 5 tabelas existem, e `SELECT key FROM roles` devolve `["admin"]`;
  - `test_ready_ok` via `asgi_client` → 200.
- [ ] **Step 2:** Rodar `uv run pytest services/identity -q`. Esperado: FAIL.
- [ ] **Step 3:** Implementar os arquivos. O `env.py` do Alembic usa `IDENTITY_DATABASE_URL` em modo async. `ci-identity.yml` replica o `ci-platform.yml` com `paths: [services/identity/**, libs/py/platform/**, uv.lock]`.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(identity): esqueleto do serviço, modelos e migração inicial`.

### Task 6: identity, domínio de senha e bloqueio

**Files:**
- Create: `src/identity/domain/{passwords.py,lockout.py}`, `src/identity/domain/data/common-passwords.txt`
- Test: `tests/unit/test_passwords.py`, `test_lockout.py`

**Interfaces:**
- Produces:
  - `validate_password(password: str, email: str) -> list[str]`. Devolve códigos em ordem fixa: `"too_short"` (< 10 caracteres), `"too_common"` (na lista, comparação case-insensitive), `"contains_email"` (contém a parte local do email com 4 caracteres ou mais).
  - `hash_password(password: str) -> str` com `argon2.PasswordHasher()` nos parâmetros padrão (Argon2id).
  - `verify_password(hash: str, password: str) -> bool`.
  - `DUMMY_HASH: str`, calculado uma vez na importação.
  - `@dataclass(frozen=True) class LoginState`: `failed_logins: int`, `locked_until: datetime | None`.
  - `MAX_FAILURES = 5`, `LOCK_DURATION = timedelta(minutes=15)`.
  - `is_locked(s, now) -> bool`, `register_failure(s, now) -> LoginState` (a 5ª falha define `locked_until = now + 15 min` e zera o contador) e `register_success(s) -> LoginState`.
  - Lista de senhas: "10k-most-common.txt" do SecLists (licença MIT), com crédito no cabeçalho do arquivo.

- [ ] **Step 1:** Escrever os testes:
  - `validate_password("curta", "a@b.com") == ["too_short"]`;
  - `validate_password("password123", "a@b.com") == ["too_common"]`;
  - `validate_password("joaosilva-forte-1", "joaosilva@x.com") == ["contains_email"]`;
  - `verify_password(hash_password("s3nh4-longa!"), "s3nh4-longa!") is True`;
  - quatro falhas → `is_locked(...) is False`, a quinta → `True`;
  - `is_locked(s, now + timedelta(minutes=15, seconds=1)) is False`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(identity): política de senha, Argon2id e bloqueio de conta`.

### Task 7: identity, chaves de assinatura, emissão de tokens e JWKS

**Files:**
- Create: `src/identity/domain/tokens.py`, `src/identity/adapters/signing.py`, `src/identity/api/routes_jwks.py`, `scripts/gen_keys.py`
- Test: `tests/unit/test_tokens.py`, `tests/api/test_jwks.py`

**Interfaces:**
- Produces:
  - `ACCESS_TTL = timedelta(seconds=900)`.
  - `REFRESH_TTL = {"storefront": timedelta(days=30), "admin": timedelta(hours=12)}`.
  - `REUSE_GRACE = timedelta(seconds=10)`.
  - `@dataclass(frozen=True) class SigningKey`: `kid: str`, `private_key: Ed25519PrivateKey`, com `def public_jwk(self) -> dict`.
  - `load_signing_key(path: Path) -> SigningKey`. O `kid` são os 16 primeiros hex do SHA-256 da chave pública raw.
  - `issue_access_token(key: SigningKey, user_id: UUID, audience: str, kind: str, roles: list[str], now: datetime) -> str`.
  - `new_refresh_token() -> tuple[str, str]`: devolve `(raw, sha256_hex)`, com `raw = secrets.token_urlsafe(32)`.
  - `GET /.well-known/jwks.json` → `{"keys": [key.public_jwk()]}` com `Cache-Control: public, max-age=300`.
  - No startup, o `create_app` faz upsert da chave em `signing_keys` (`kid`, `public_jwk`, `private_key_ref = str(path)`, `active = true`).
  - `scripts/gen_keys.py`:
    - escreve `infra/secrets/identity-signing-key.pem` (PKCS8, sem senha);
    - cria o `.env` a partir do `.env.example`, se não existir;
    - não sobrescreve uma chave existente sem `--force`.

- [ ] **Step 1:** Escrever os testes:
  - `test_access_token_verifies_with_platform_verifier`: emitir, depois `TokenVerifier` (Tarefa 3) com `fetch` que devolve o JWKS → `Principal.kind == "staff"` e `roles == {"admin"}`;
  - `test_access_token_expires_in_900s`: `exp - iat == 900`;
  - `test_refresh_token_hash_matches`: `sha256(raw) == hash`, e duas chamadas geram valores diferentes;
  - `test_jwks_endpoint_serves_active_key` → 200, um único item, `kid` igual ao da chave carregada e `"d" not in key` (sem chave privada).
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(identity): chaves Ed25519, emissão de access token e JWKS`.

### Task 8: identity, serviço de autenticação e rotação de refresh

**Files:**
- Create: `src/identity/application/{ports.py,auth_service.py}`, `src/identity/adapters/repositories.py`
- Test: `tests/integration/test_auth_service.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class TokenPair`: `access_token: str`, `refresh_token: str`, `expires_in: int`, `refresh_expires_at: datetime`.
  - `class AuthError(Exception)` com `code: str`. Os códigos são:
    - `identity.auth.invalid_credentials`;
    - `identity.auth.email_taken`;
    - `identity.auth.weak_password` (com a lista de violações);
    - `identity.auth.invalid_refresh`;
    - `identity.auth.refresh_reused`.
  - `class AuthService`, construído com `__init__(self, users: UserRepository, tokens: RefreshTokenRepository, key: SigningKey, clock: Callable[[], datetime])`. Métodos:

    | Método | Assinatura |
    |---|---|
    | `register` | `async def register(self, email: str, password: str, name: str) -> TokenPair` (audiência `storefront`) |
    | `login` | `async def login(self, email: str, password: str, audience: Literal["storefront","admin"]) -> TokenPair` |
    | `refresh` | `async def refresh(self, raw: str) -> TokenPair` |
    | `logout` | `async def logout(self, raw: str) -> None` |
    | `ensure_bootstrap_admin` | `async def ensure_bootstrap_admin(self, email: str, password: str) -> None` (idempotente; cria `staff` com papel `admin` se não existir nenhum staff) |

  - Regras:
    - email normalizado com `strip().lower()`;
    - `storefront` exige `kind == "customer"` e `admin` exige `kind == "staff"`; qualquer divergência vira `invalid_credentials`;
    - com usuário inexistente, verifica `DUMMY_HASH` antes de falhar;
    - conta bloqueada também responde `invalid_credentials`;
    - `UserRepository` e `RefreshTokenRepository` são `Protocol` em `ports.py`, implementados em `repositories.py` com SQLAlchemy;
    - o refresh roda numa transação com `SELECT ... FOR UPDATE` na linha do token.
  - Algoritmo do `refresh`:

```
token = repo.get_by_hash(sha256(raw)) FOR UPDATE
se não existe, ou expirado, ou família revogada: invalid_refresh
se token.replaced_by é nulo e revoked_at é nulo:
    marca first_used_at = now, cria sucessor na mesma família, token.replaced_by = sucessor.id
senão se token.first_used_at e now - token.first_used_at <= REUSE_GRACE:
    cria outro sucessor na mesma família (corrida de abas), não revoga
senão:
    revoga todos os tokens da família (revoked_at = now) e levanta refresh_reused
```

- [ ] **Step 1:** Escrever os testes de integração com o banco migrado e um relógio controlável:
  - `test_register_then_login_customer`;
  - `test_register_normalizes_email`: cadastrar `"Ana@X.com"` e depois `login("ana@x.com")` funciona; cadastrar `"ana@x.com"` de novo → `email_taken`;
  - `test_weak_password_rejected_with_codes`;
  - `test_customer_cannot_login_as_admin` → `invalid_credentials`;
  - `test_refresh_rotates`: o token antigo deixa de valer depois da janela;
  - `test_refresh_reuse_within_grace_issues_new_pair` (Review Focus 4): dois refresh do mesmo raw com 5 s de diferença → ambos ok e a família continua ativa;
  - `test_refresh_reuse_after_grace_revokes_family`: com 11 s de diferença → `refresh_reused`, e o sucessor emitido antes também falha com `invalid_refresh`;
  - `test_logout_revokes_family`;
  - `test_bootstrap_admin_idempotent`: chamado duas vezes → exatamente 1 staff.
- [ ] **Step 2:** Rodar `uv run pytest services/identity/tests/integration -q`. Esperado: FAIL.
- [ ] **Step 3:** Implementar `ports.py`, `repositories.py` e `auth_service.py`.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(identity): serviço de autenticação com rotação e detecção de reuso`.

### Task 9: identity, API HTTP

**Files:**
- Create: `src/identity/api/{schemas.py,routes_auth.py,routes_me.py}`, `src/identity/cli.py`
- Modify: `src/identity/main.py` (rotas e bootstrap do admin no lifespan)
- Test: `tests/api/test_auth_api.py`, `test_me_api.py`

**Interfaces:**
- Produces (corpos em snake_case):

  | Rota | Corpo | Resposta |
  |---|---|---|
  | `POST /v1/auth/register` | `{email, password, name}` | 201 `TokenPairOut {access_token, refresh_token, expires_in, refresh_expires_at, user: UserOut}` |
  | `POST /v1/auth/login` | `{email, password}` | 200 `TokenPairOut` |
  | `POST /v1/auth/staff/login` | `{email, password}` | 200 `TokenPairOut` |
  | `POST /v1/auth/refresh` | `{refresh_token}` | 200 `TokenPairOut` |
  | `POST /v1/auth/logout` | `{refresh_token}` | 204 |
  | `GET /v1/me` | (audiência `storefront` ou `admin`) | `UserOut {id, email, name, kind, roles}` |
  | `PATCH /v1/me` | `{name?, email?, new_password?, current_password?}` | trocar email ou senha exige `current_password` correto, senão 422 `identity.me.current_password_required` ou 401 `identity.auth.invalid_credentials` |

  - Mapeamento de erro: `AuthError` → `ProblemError`. Status:
    - 401: `invalid_credentials`, `invalid_refresh`, `refresh_reused`;
    - 409: `email_taken`;
    - 422: `weak_password`, com `errors = {"body.password": [códigos]}`.
  - `cli.py` com `python -m identity.cli create-staff --email E --password P` (para operação manual).

- [ ] **Step 1:** Escrever os testes via `asgi_client`:
  - `test_register_login_me_flow`;
  - `test_login_responses_identical_for_unknown_wrong_and_locked` (Review Focus 5): três cenários → mesmo status 401 e corpos iguais, ignorando `trace_id`;
  - `test_staff_login_audience_admin`: decodificar sem verificar → `aud == "admin"`;
  - `test_customer_token_forbidden_on_admin_only_route`: rota de teste com `require_audience("admin")` → 401;
  - `test_patch_me_password_requires_current`;
  - `test_weak_password_422_field_errors`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar as rotas, os schemas (`EmailStr`, `name` com 1 a 120 caracteres) e o lifespan que chama `ensure_bootstrap_admin` quando as duas variáveis `IDENTITY_BOOTSTRAP_ADMIN_*` existem.
- [ ] **Step 4:** Rodar `uv run pytest services/identity -q && uv run pyright services/identity`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(identity): API de cadastro, login, refresh, logout e perfil`.

### Task 10: catalog, esqueleto, modelos e migração

**Files:**
- Create: `services/catalog/{pyproject.toml,Dockerfile,alembic.ini}`, `migrations/{env.py,versions/0001_initial.py}`, `src/catalog/{__init__.py,main.py,settings.py}`, `src/catalog/adapters/models.py`, `tests/conftest.py`, `tests/integration/test_migrations.py`, `.github/workflows/ci-catalog.yml`

**Interfaces:**
- Produces:
  - `class CatalogSettings(BaseServiceSettings)`: prefixo `CATALOG_`, `media_root: Path = Path("/data/media")`, `public_base_url: str = "http://api.katoshop.localhost/catalog"`.
  - Tabelas da spec 8.3, mais as definições abaixo (o plano decide o que a spec deixou aberto):
    - `products.min_price_cents int null`: menor preço efetivo entre as variantes ativas, recalculado pela aplicação sempre que preço ou variantes mudam. Serve à listagem, ao filtro e à ordenação por preço;
    - `products.search_vector`: `GENERATED ALWAYS AS` com `setweight(to_tsvector('portuguese', immutable_unaccent(name)),'A') || setweight(to_tsvector('portuguese', immutable_unaccent(coalesce(category_name_cache,''))),'B') || setweight(to_tsvector('portuguese', immutable_unaccent(coalesce(description,''))),'C')`;
    - `products.category_name_cache text`: o nome da categoria copiado na escrita, porque coluna gerada não pode fazer join;
    - função SQL `immutable_unaccent(text)` (wrapper `IMMUTABLE` de `public.unaccent`) e índice GIN em `search_vector`;
    - `variants`: `CHECK (stock_on_hand >= stock_reserved AND stock_reserved >= 0)` e índice em `(product_id, active)`;
    - `storefront_settings (id smallint primary key check (id = 1), data jsonb not null, updated_at)`.
  - A migração insere os dados de referência:
    - tamanhos `PP,P,M,G,GG,XG,XGG` (position 1..7);
    - cores `PRT` Preto `#111111`, `BRC` Branco `#F4F4F0`, `CNZ` Cinza mescla `#8C8C88`, `OFW` Off-white `#E8E3D6`, `VRD` Verde musgo `#4A5236`, `AZM` Azul marinho `#1E2A44`, `MRR` Marrom `#5A4030`.

- [ ] **Step 1:** Escrever os testes:
  - `test_upgrade_creates_tables_and_reference_data`: 7 tamanhos e 7 cores;
  - `test_search_vector_ignores_accents`: inserir produto "Moletom Básico" → `search_vector @@ websearch_to_tsquery('portuguese', immutable_unaccent('basico'))` encontra;
  - `test_stock_check_constraint`: `UPDATE variants SET stock_on_hand = -1` → `IntegrityError`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar, com `create_app` no mesmo padrão do identity e `app.state.token_verifier = TokenVerifier(JwksKeyProvider(settings.jwks_url))`. `ci-catalog.yml` segue o padrão da Tarefa 5.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(catalog): esqueleto, modelos, busca em português e dados de referência`.

### Task 11: catalog, domínio puro

**Files:**
- Create: `src/catalog/domain/{slugs.py,variants.py,stock.py,publishing.py,images.py,settings_schema.py}`
- Test: `tests/unit/test_slugs.py`, `test_variants.py`, `test_stock.py`, `test_publishing.py`, `test_images.py`, `test_settings_schema.py`

**Interfaces:**
- Produces:
  - `slugify(text: str) -> str`: NFKD, remove acentos, minúsculas, `[^a-z0-9]+` vira `-` e as pontas são aparadas. String vazia levanta `ValueError`.
  - `@dataclass(frozen=True) class NewVariant`: `sku: str`, `color_code: str`, `size_code: str`.
  - `generate_variant_grid(product_id: UUID, colors: list[str], sizes: list[str], existing: set[tuple[str, str]]) -> list[NewVariant]`:
    - `sku = f"KS-{product_id.hex[-6:].upper()}-{color}-{size}"`;
    - pula combinações em `existing` e entradas duplicadas;
    - mantém a ordem cores × tamanhos recebida.
  - `class StockReason(StrEnum)`: `INITIAL="initial"`, `ADJUSTMENT="adjustment"`, `DAMAGE="damage"`, `RETURN="return"`. `MANUAL_REASONS` contém os quatro.
  - `class StockError(Exception)` com `code`:
    - `catalog.stock.zero_delta`;
    - `catalog.stock.would_go_negative`;
    - `catalog.stock.invalid_reason`.
  - `apply_adjustment(on_hand: int, reserved: int, delta: int, reason: str) -> int`: devolve o novo `on_hand`. Falha se `delta == 0`, se `on_hand + delta < reserved` ou se o motivo não está em `MANUAL_REASONS`.
  - `available(on_hand: int, reserved: int) -> int`: devolve `max(on_hand - reserved, 0)`.
  - `effective_price(base_price_cents: int, variant_price_cents: int | None) -> int`.
  - `@dataclass(frozen=True) class PublishCheck`: `active_variant_prices: list[int]`, `image_count: int`.
  - `publish_blockers(c: PublishCheck) -> list[str]`, em ordem fixa:
    - `"no_active_variant"`;
    - `"no_image"`;
    - `"no_price"` (alguma variante ativa com preço efetivo ≤ 0).
  - `detect_image_type(head: bytes) -> Literal["jpg","png","webp"] | None`, pelos magic bytes:
    - `FF D8 FF` → `jpg`;
    - `89 50 4E 47 0D 0A 1A 0A` → `png`;
    - `RIFF....WEBP` → `webp`.
  - `MAX_IMAGE_BYTES = 8 * 1024 * 1024`.
  - `storage_key(data: bytes, ext: str) -> str` devolve `f"products/{sha256(data).hexdigest()}.{ext}"`.
  - `STORAGE_KEY_RE = r"^products/[0-9a-f]{64}\.(jpg|png|webp)$"`.
  - `class StorefrontSettings(BaseModel)`:
    - `hero: Hero {title (1..80), subtitle (1..200), cta_label (1..30), cta_href (começa com "/"), image_key (STORAGE_KEY_RE)}`;
    - `secondary_cta: Cta {label, href}`;
    - `featured_collection_slugs: list[str]` (máximo 3);
    - `policies: Policies {shipping_text, returns_text, pix_discount_percent: int 0..20, max_installments: int 1..12, demo_notice: str}`.

- [ ] **Step 1:** Escrever os testes:
  - `slugify("Moletom Zip Heavy Básico!") == "moletom-zip-heavy-basico"`;
  - `generate_variant_grid` com 2 cores × 3 tamanhos e `existing={("PRT","M")}` → 5 itens, e o SKU do primeiro é `KS-XXXXXX-PRT-P`, com os 6 últimos hex do id;
  - `apply_adjustment(5, 0, -6, "adjustment")` → `would_go_negative`;
  - `apply_adjustment(5, 2, -3, "damage") == 2`;
  - `apply_adjustment(5, 0, 0, "adjustment")` → `zero_delta`;
  - `apply_adjustment(5, 0, 1, "sale")` → `invalid_reason`;
  - `publish_blockers(PublishCheck([], 0)) == ["no_active_variant", "no_image"]`;
  - `publish_blockers(PublishCheck([0, 12900], 1)) == ["no_price"]`;
  - `detect_image_type(b"%PDF-1.7...") is None`;
  - `StorefrontSettings` rejeita `cta_href="https://x"` e `pix_discount_percent=50`.
- [ ] **Step 2:** Rodar `uv run pytest services/catalog/tests/unit -q`. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar. Esperado: PASS, com cobertura ≥ 90% em `catalog.domain` (`--cov=catalog.domain --cov-fail-under=90`; adicionar `pytest-cov` na versão estável atual).
- [ ] **Step 5:** Commit `feat(catalog): domínio de slug, grade de variantes, estoque, publicação e imagens`.

### Task 12: catalog, API do admin (catálogo e estoque)

**Files:**
- Create: `src/catalog/application/{ports.py,admin_service.py}`, `src/catalog/adapters/repositories.py`, `src/catalog/api/{schemas.py,routes_admin.py}`
- Test: `tests/api/test_admin_products.py`, `test_admin_stock.py`, `test_admin_taxonomy.py`

**Interfaces:**
- Consumes: domínio da Tarefa 11 e `require_permission("catalog.write")` da Tarefa 3.
- Produces. Todas as rotas ficam em `/v1/admin` e exigem `catalog.write`.

  **Taxonomia e produtos:**

  | Rota | Comportamento |
  |---|---|
  | `GET/POST /categories`, `PATCH/DELETE /categories/{id}` | DELETE com produtos vinculados → 409 `catalog.category.in_use` |
  | `GET/POST /collections`, `PATCH/DELETE /collections/{id}` | — |
  | `PUT /collections/{id}/products` | corpo `{product_ids: [...]}` define a ordem |
  | `GET /products` | `?q=&status=&category=&slug=&cursor=&limit=`, devolve `{items: [AdminProductRow {id, slug, name, status, category, min_price_cents, variant_count, total_available, updated_at}], next_cursor}` |
  | `POST /products` | `{name, slug?, description, category_id, base_price_cents, attributes}` → 201 `AdminProduct` (completo, com `variants`, `images`, `version`). Sem slug, usa `slugify(name)`. Slug repetido → 409 `catalog.product.slug_taken` |
  | `PATCH /products/{id}` | exige `version` no corpo. Divergência → 409 `catalog.product.version_conflict` |
  | `POST /products/{id}/variants/generate` | `{colors, sizes}` → 200 `AdminProduct`. Cor ou tamanho inexistente → 422 |
  | `PATCH /variants/{id}` | `{price_cents?: int \| null, active?: bool, version}` |
  | `POST /products/{id}/publish` | 422 `catalog.product.not_publishable` com `errors = {"product": blockers}` |
  | `POST /products/{id}/archive` | — |

  **Estoque:**
  - `POST /variants/{id}/stock-adjustments` com `{delta, reason, note?}` → 201 `{movement, variant}`. Roda com `SELECT ... FOR UPDATE` na variante, e o `actor_id` é o `principal.user_id`;
  - `GET /variants/{id}/stock-movements?cursor=` traz os mais novos primeiro;
  - `GET /overview` → `{products_by_status: {draft, active, archived}, out_of_stock_variants: int, recent_movements: [10 itens]}`.

  **Vitrine:** `GET/PUT /storefront/settings`, com corpo `StorefrontSettings`. Essa rota é usada pelo seed nesta fatia; a tela de edição é da fatia 4.

  **Regras gerais:**
  - mudanças em preço base ou em variantes recalculam `min_price_cents` na mesma transação;
  - mudar a categoria atualiza `category_name_cache`.

- [ ] **Step 1:** Escrever os testes de API. Os tokens vêm de uma fixture `admin_token`/`customer_token`, que assina com uma chave de teste e injeta um `TokenVerifier` com `fetch` falso. Testes:
  - `test_create_product_generates_slug_and_draft_status`;
  - `test_duplicate_slug_409`;
  - `test_patch_with_stale_version_409`;
  - `test_generate_variants_idempotent`: chamado duas vezes → mesma contagem;
  - `test_min_price_recomputed_on_variant_price_change`;
  - `test_publish_blocked_lists_reasons` e `test_publish_ok_sets_published_at`;
  - `test_stock_adjustment_records_movement_with_actor`;
  - `test_stock_adjustment_negative_422`;
  - `test_concurrent_stock_adjustments_serialize` (Review Focus 3): estoque 5 e `asyncio.gather` de dois ajustes `-3` → um 201, um 422, estoque final 2 e exatamente 1 movimento novo;
  - `test_category_in_use_409`;
  - `test_customer_token_403` e `test_no_token_401`;
  - `test_storefront_settings_put_validates`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar `ports.py` (protocolos dos repositórios), `admin_service.py` (casos de uso, transação por chamada), `repositories.py` e as rotas. Para concorrência, cada requisição usa a própria sessão (`async with session_factory() as s, s.begin()`).
- [ ] **Step 4:** Rodar `uv run pytest services/catalog -q`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(catalog): API de admin para produtos, variantes, estoque e taxonomia`.

### Task 13: catalog, imagens (upload, armazenamento e entrega)

**Files:**
- Create: `src/catalog/adapters/storage_local.py`, `src/catalog/api/routes_media.py`
- Modify: `src/catalog/api/routes_admin.py`, `src/catalog/application/admin_service.py`, `src/catalog/application/ports.py`
- Test: `tests/integration/test_storage_local.py`, `tests/api/test_admin_images.py`, `tests/api/test_media.py`

**Interfaces:**
- Produces:
  - `class ImageStorage(Protocol)`: `async def save(self, key: str, data: bytes) -> None` e `async def read(self, key: str) -> bytes | None`.
  - `LocalImageStorage(root: Path)`. Valida a chave contra `STORAGE_KEY_RE` (senão `ValueError`) e grava de forma atômica (arquivo temporário + `os.replace`).
  - `POST /v1/admin/products/{id}/images` (multipart: `file`, `alt`, `color_code?`, `credit_author?`, `credit_source_url?`, `license?`) → 201 `AdminImage`:
    - lê no máximo `MAX_IMAGE_BYTES + 1` bytes; acima disso → 413 `catalog.image.too_large`;
    - tipo detectado `None` → 415 `catalog.image.unsupported_type`;
    - dimensões lidas com Pillow (`Image.open(...).size`); imagem corrompida → 415;
    - mesma `storage_key` já presente no produto → 200 com a imagem existente (idempotente para o seed);
    - `alt` vazio → 422.
  - `PATCH /v1/admin/images/{id}` (`alt`, `color_code`, `position`, créditos) e `DELETE /v1/admin/images/{id}`.
  - `GET /v1/media/{storage_key:path}` → bytes com o content-type correto e `Cache-Control: public, max-age=31536000, immutable`. Chave inválida ou ausente → 404.
  - `AdminImage` e as imagens públicas expõem `url = f"{public_base_url}/v1/media/{storage_key}"`.

- [ ] **Step 1:** Escrever os testes:
  - `test_rejects_path_traversal_key` (`"products/../../etc/passwd"`);
  - `test_upload_jpeg_ok_records_dimensions` (fixture: JPEG 64×48 gerado com Pillow em memória);
  - `test_upload_pdf_renamed_jpg_415`;
  - `test_upload_over_8mb_413`;
  - `test_upload_same_bytes_twice_returns_existing`;
  - `test_media_served_with_immutable_cache`;
  - `test_media_unknown_key_404`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(catalog): upload validado de imagens, disco local e entrega com cache`.

### Task 14: catalog, API pública (listagem, busca, facetas e detalhe)

**Files:**
- Create: `src/catalog/adapters/product_queries.py`, `src/catalog/api/routes_public.py`
- Test: `tests/integration/test_product_queries.py`, `tests/api/test_public_api.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ProductFilter`: `category: str | None`, `collection: str | None`, `sizes: tuple[str, ...]`, `colors: tuple[str, ...]`, `price_min: int | None`, `price_max: int | None`, `q: str | None`, `sort: Literal["relevance","newest","price_asc","price_desc"]`.
  - Cursor: `base64url(json.dumps({"s": sort, "k": sort_value, "id": str(id)}))`. Na decodificação:
    - qualquer falha de parse ou de schema → `ProblemError(422, "catalog.pagination.invalid_cursor")`;
    - `s` diferente do `sort` atual → o mesmo erro.
  - Regras do filtro:
    - `q` vazio ou só espaços vira `None`;
    - `len(q) > 200` → 422 `catalog.search.query_too_long`;
    - `relevance` sem `q` vira `newest`.
  - `async def list_products(session, f: ProductFilter, cursor: str | None, limit: int) -> Page[ProductCard]`. Só produtos `active`. Ordens de desempate:
    - `newest`: `published_at desc, id desc`;
    - preço: `min_price_cents` + `id`;
    - `relevance`: `ts_rank_cd(search_vector, query) desc, id desc`.
  - `ProductCard {slug, name, min_price_cents, image: {url, alt} | None, colors: [{code, name, hex}], sold_out: bool}`. `sold_out` vale `True` quando todas as variantes ativas têm `available == 0`.
  - O filtro de tamanho e cor usa `EXISTS (variante ativa com available > 0 e size/color em ...)`. O filtro de preço usa `min_price_cents`.
  - `async def facets(session, f: ProductFilter) -> Facets {sizes: [{code, label, count}], colors: [{code, name, hex, count}], categories: [{slug, name, count}], price: {min, max}}`. Cada dimensão é contada com todos os **outros** filtros aplicados, menos o dela (padrão de multisseleção). A ordem dos tamanhos segue `position`.
  - Rotas públicas:
    - `GET /v1/products` (parâmetros repetíveis `size`, `color`) → `{items, next_cursor}`, com `Cache-Control: public, max-age=30`;
    - `GET /v1/products/facets`;
    - `GET /v1/products/{slug}` → `ProductDetail {slug, name, description, attributes, category, min_price_cents, colors, sizes, variants: [{sku, color_code, size_code, price_cents, available: bool}], images: [{url, alt, color_code, width, height, credit_author, credit_source_url, license}]}`. Inativo ou inexistente → 404 `catalog.product.not_found`;
    - `GET /v1/categories`;
    - `GET /v1/collections` e `GET /v1/collections/{slug}`;
    - `GET /v1/storefront/settings`;
    - `GET /v1/credits` → lista de `{product_name, image_url, credit_author, credit_source_url, license}` para a página `/creditos`.

- [ ] **Step 1:** Escrever os testes de integração. Uma fixture cria 6 produtos ativos, 1 rascunho e variantes com estoque misto. Testes:
  - `test_lists_only_active`;
  - `test_search_accent_insensitive` (`q="moletom basico"` acha "Moletom Básico");
  - `test_search_multiword_and`: com os produtos "Moletom Zip Preto", "Moletom Cinza" e "Camiseta Preta" na fixture, `q="moletom preto"` → só "Moletom Zip Preto" (critério de aceite 3);
  - `test_size_and_color_filters_combine`;
  - `test_sold_out_variant_not_matched_by_size_filter`;
  - `test_facets_exclude_own_dimension`: filtrando `size=M`, a faceta de tamanhos ainda conta P e G;
  - `test_keyset_pagination_stable`: paginar com `limit=2` → união igual à lista completa, sem repetição;
  - `test_price_sort_and_range`;
  - `test_odd_queries_never_500` (Review Focus 1): para `q` em `["", "   ", "&|!", '"aspas', "x"*200]` → 200, e `"x"*201` → 422;
  - `test_bad_cursor_422` (Review Focus 2): `"lixo"`, base64 de JSON incompleto e cursor de `price_asc` usado com `newest`;
  - `test_detail_inactive_404`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar com SQLAlchemy Core. A busca usa `websearch_to_tsquery('portuguese', immutable_unaccent(:q))`, que já tolera operadores e aspas.
- [ ] **Step 4:** Rodar `uv run pytest services/catalog -q && uv run pyright services/catalog`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(catalog): API pública com busca, filtros, facetas e paginação keyset`.

### Task 15: Infraestrutura local (compose, gateway e observabilidade)

**Files:**
- Create:
  - `infra/compose.yaml` (incluído pela raiz `compose.yaml` com `include: [infra/compose.yaml]`);
  - `infra/traefik/{traefik.yml,dynamic.yml}`, `infra/postgres-init/01-databases.sh`, `infra/otel/collector.yaml`, `infra/prometheus/prometheus.yml`;
  - `infra/grafana/provisioning/{datasources/datasources.yml,dashboards/dashboards.yml}`, `infra/grafana/dashboards/red-services.json`.
- Modify: `.env.example`, `package.json` (scripts `dev:up` = `python scripts/gen_keys.py && docker compose up -d --build`, `dev:down` = `docker compose down`)

**Interfaces:**
- Produces:
  - **Serviços e perfis do compose:**
    - `postgres` (volume `pgdata`, healthcheck `pg_isready`);
    - `identity` e `catalog` (`depends_on: postgres: condition: service_healthy`; o catalog monta o volume `media-data` em `/data/media`);
    - `traefik` (portas `${KATOSHOP_HTTP_PORT:-80}:80` e `8081:8080` para o dashboard; aliases de rede `api.katoshop.localhost`, `katoshop.localhost`, `admin.katoshop.localhost`, para o Next resolver os mesmos hosts por dentro);
    - perfil `observability` com `otel-collector`, `jaeger` (UI em `:16686`), `prometheus` (`:9090`, flag `--web.enable-otlp-receiver`) e `grafana` (`:3001`, admin anônimo só leitura);
    - `storefront` e `admin` entram na Tarefa 20/22, e `seed` na Tarefa 23;
    - `mem_limit` em todos os serviços, somando no máximo 6 GB.
  - **Postgres:** o `01-databases.sh` cria os bancos `identity` e `catalog` com os usuários `identity_svc` e `catalog_svc` (senhas via env) e `REVOKE CONNECT ... FROM PUBLIC`. Cada usuário é dono do seu banco, e `unaccent` é criado no `catalog`.
  - **Traefik:** roteadores `Host(api.katoshop.localhost) && PathPrefix(/identity)` e `PathPrefix(/catalog)` com middleware `stripPrefix`. O middleware `auth-ratelimit` (`average: 10`, `burst: 20`, por IP) é aplicado ao roteador `PathPrefix(/identity/v1/auth)`. Tracing via `tracing.otlp.grpc.endpoint=otel-collector:4317`.
  - **Collector:** recebe OTLP em 4317/4318. Traces vão para `jaeger:4317`; métricas vão por `otlphttp` para `http://prometheus:9090/api/v1/otlp`.
  - **Dashboard RED:** painéis por serviço com `http_server_request_duration_seconds` (taxa, % de 5xx, p50/p95). O nome final da métrica deve ser confirmado no Prometheus na hora da verificação.
  - **Variáveis de ambiente:** `IDENTITY_JWKS_URL` e `CATALOG_JWKS_URL` = `http://identity:8000/.well-known/jwks.json`, e `*_OTEL_ENDPOINT=http://otel-collector:4317`. O `.env.example` traz `IDENTITY_BOOTSTRAP_ADMIN_EMAIL=admin@katoshop.localhost` e `IDENTITY_BOOTSTRAP_ADMIN_PASSWORD=katoshop-demo-2026`.

- [ ] **Step 1:** Rodar `pnpm dev:up` antes de criar os arquivos. Esperado: falha, porque não há compose.
- [ ] **Step 2:** Criar os arquivos.
- [ ] **Step 3:** Rodar `pnpm dev:up && docker compose --profile observability up -d`. Esperado: todos os containers ficam `healthy`/`running` em `docker compose ps`.
- [ ] **Step 4:** Verificar:
  - `curl -s http://api.katoshop.localhost/identity/health/ready` → `{"status":"ok"}`;
  - `curl -s http://api.katoshop.localhost/catalog/v1/products` → `{"items":[],"next_cursor":null}`;
  - 25 POSTs rápidos em `/identity/v1/auth/login` → pelo menos um 429;
  - no Jaeger (`http://localhost:16686`), um trace do GET de produtos com spans `traefik` → `catalog` → `SELECT`;
  - no Grafana, o dashboard "KatoShop RED" tem dados.

  Registrar a saída no commit.
- [ ] **Step 5:** Commit `feat(infra): compose com Traefik, Postgres por serviço e stack de observabilidade`.

### Task 16: Contrato OpenAPI e pacote api-client

**Files:**
- Create: `scripts/export_openapi.py`, `packages/api-client/{package.json,tsconfig.json,src/index.ts,src/session.ts,src/errors.ts}`, `packages/api-client/openapi/{identity,catalog}.json`, `packages/api-client/src/generated/{identity,catalog}.ts`, `packages/api-client/test/{errors.test.ts,session.test.ts}`
- Modify: `package.json` (`gen:api` = `uv run python scripts/export_openapi.py && pnpm --filter @katoshop/api-client gen`), `.github/workflows/ci-web.yml` (criar)

**Interfaces:**
- Produces:
  - `export_openapi.py`: importa `identity.main:create_app` / `catalog.main:create_app` sem banco (as settings vêm de variáveis fictícias), grava o JSON ordenado (`sort_keys=True`, indent 2).
  - `@katoshop/api-client`:
    - `createIdentityClient(baseUrl: string, accessToken?: string)` e `createCatalogClient(baseUrl: string, accessToken?: string)`, que retornam `openapi-fetch` tipado;
    - `class ApiProblem extends Error { status: number; code: string; errors?: Record<string, string[]>; traceId?: string }`;
    - `function unwrap<T>(r: { data?: T; error?: unknown; response: Response }): T`, que lança `ApiProblem`.
  - `session.ts`: `createSession(opts: { cookiePrefix: "ks" | "ka"; audience: "storefront" | "admin"; identityBaseUrl: string; secure: boolean })` devolve um objeto com:
    - `getAccessToken(): Promise<string | null>` (lê `next/headers` `cookies()`);
    - `setTokens(pair)`: cookies `<prefix>_at` (maxAge 900) e `<prefix>_rt` (até `refresh_expires_at`), `httpOnly`, `sameSite: "lax"`, `path: "/"`;
    - `clear()`;
    - `withAuth<T>(fn: (token: string) => Promise<T>): Promise<T>`: em `ApiProblem.status === 401`, faz um único refresh, regrava os cookies e repete. Se o refresh falhar, limpa os cookies e lança `ApiProblem` 401.

  O acesso a cookies fica por trás de uma interface `CookieStore` injetável, para facilitar o teste.
  - `ci-web.yml`, nos caminhos `apps/**`, `packages/**`, `services/*/src/**/api/**`:
    - `pnpm install --frozen-lockfile`;
    - `pnpm gen:api`, seguido de `git diff --exit-code packages/api-client` (quebra de contrato falha aqui);
    - `pnpm turbo lint typecheck test build`.

- [ ] **Step 1:** Escrever os testes Vitest:
  - `unwrap` com resposta problem+json → lança `ApiProblem` com `code` e `errors`;
  - `withAuth` com `CookieStore` falso: o primeiro `fn` lança 401, o refresh (fetch mockado) devolve um par novo → `fn` é chamado de novo com o token novo e os cookies são regravados;
  - `withAuth` com o refresh falhando → os cookies são limpos e lança 401.
- [ ] **Step 2:** Rodar `pnpm --filter @katoshop/api-client test`. Esperado: FAIL.
- [ ] **Step 3:** Implementar, e rodar `pnpm gen:api` para gerar o OpenAPI e os tipos.
- [ ] **Step 4:** Rodar `pnpm --filter @katoshop/api-client test typecheck` e `pnpm gen:api && git diff --exit-code packages/api-client` (o segundo depois do commit dos gerados). Esperado: PASS e diff vazio.
- [ ] **Step 5:** Commit `feat(api-client): contrato OpenAPI versionado, cliente tipado e sessão BFF`.

### Task 17: Design system (packages/ui)

**Files:**
- Create: `packages/ui/{package.json,tsconfig.json,components.json}`, `src/styles/{tokens.css,globals-store.css,globals-admin.css}`, `src/fonts.ts`, `src/lib/{money.ts,cn.ts}`, `src/components/{button.tsx,logo.tsx,badge.tsx,input.tsx,label.tsx,dialog.tsx,select.tsx,checkbox.tsx,table.tsx,tabs.tsx,toast.tsx,skeleton.tsx}`, `src/brand/{favicon.svg,logo-dark.svg,logo-light.svg}`, `scripts/build-icons.mjs`, `test/money.test.ts`, `test/button.test.tsx`

**Interfaces:**
- Produces:
  - **Tokens:** `tokens.css` com `@theme` do Tailwind 4 contendo exatamente os tokens da tabela da spec 6 (`--color-bg`, `--color-surface`, `--color-border`, `--color-fg`, `--color-muted`, `--color-accent`, `--color-accent-on-light`, `--color-admin-bg`, `--color-admin-sidebar`), mais `--radius: 2px` e `--duration-fast: 150ms`. Também uma regra `@media (prefers-reduced-motion: reduce)` que zera transições.
  - **Fontes:** `fonts.ts` exporta `anton`, `inter` e `jetbrainsMono` via `next/font/google` (auto-hospedadas no build) como variáveis CSS `--font-display`, `--font-sans` e `--font-mono`.
  - **Dinheiro (`money.ts`):**
    - `formatBRL(cents: number): string` usa `Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL"})`;
    - `installments(cents: number, max: number): { count: number; eachCents: number }` usa `count = max` e `eachCents = Math.ceil(cents / max)`;
    - `pixPrice(cents: number, percent: number): number` usa `Math.round(cents * (100 - percent) / 100)`.
  - **Componentes:**
    - `Button` com variantes `primary` (fundo accent, texto bg), `secondary` (borda fg), `ghost`, tamanhos `md|lg` e `rounded-[var(--radius)]` sem exceção;
    - `Logo({ tone: "dark" | "light", className })` renderiza o SVG do logo C (KATOSHOP em Anton + traço sob o K: `#D7FF3A` no escuro, `#9DBF00` no claro);
    - os componentes shadcn são gerados pelo CLI e ajustados ao raio de 2px.
  - **Ícones:** `build-icons.mjs` gera, a partir do `favicon.svg`, `favicon.ico` (32), `apple-touch-icon.png` (180), `icon-192.png` e `icon-512.png`, usando `sharp` (versão estável atual), em `src/brand/generated/`.

- [ ] **Step 1:** Escrever os testes:
  - `formatBRL(29900) === "R$ 299,00"`;
  - `installments(29900, 3)` → `{count: 3, eachCents: 9967}`;
  - `pixPrice(29900, 5) === 28405`;
  - `Button` renderizado não tem nenhuma classe `rounded-full` e, com `variant="primary"`, tem a classe `bg-accent`.
- [ ] **Step 2:** Rodar `pnpm --filter @katoshop/ui test`. Esperado: FAIL.
- [ ] **Step 3:** Implementar os tokens e componentes e gerar os ícones (`pnpm --filter @katoshop/ui build:icons`).
- [ ] **Step 4:** Rodar `pnpm --filter @katoshop/ui test typecheck lint`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(ui): design system KatoShop (tokens SARJETA, logo, favicon, componentes)`.

### Task 18: Loja, base, autenticação e conta

**Files:**
- Create:
  - `apps/storefront/{package.json,next.config.ts,tsconfig.json,instrumentation.ts,Dockerfile,.env.example}`;
  - `app/layout.tsx`, `app/(shop)/layout.tsx`, `components/{site-header.tsx,site-footer.tsx}`;
  - `lib/{api.ts,session.ts}`;
  - `app/entrar/{page.tsx,actions.ts}`, `app/criar-conta/{page.tsx,actions.ts}`, `app/conta/{page.tsx,actions.ts}`;
  - `test/auth-actions.test.ts`.
- Modify: `infra/compose.yaml` (serviço `storefront` com env `API_URL=http://api.katoshop.localhost`, rota Traefik `Host(katoshop.localhost)`)

**Interfaces:**
- Consumes: `createSession`, `createIdentityClient`, `createCatalogClient` e `ApiProblem` (Tarefa 16); `Button`, `Logo` e os tokens (Tarefa 17).
- Produces:
  - `lib/session.ts` exporta `session = createSession({cookiePrefix: "ks", audience: "storefront", ...})`.
  - `lib/api.ts` exporta `catalog()` e `identity()` com a base `${API_URL}/catalog` e `${API_URL}/identity`.
  - Server actions:
    - `loginAction(prev, formData)`, `registerAction(prev, formData)`, `logoutAction()`, `updateProfileAction(prev, formData)`;
    - retornam `{ ok: false, fieldErrors?: Record<string, string>, formError?: string }` ou fazem `redirect("/conta")`.
  - Mensagens pt-BR por `code`:
    - `identity.auth.invalid_credentials` → "Email ou senha incorretos.";
    - `identity.auth.email_taken` → "Já existe uma conta com este email.";
    - `too_short` → "Use pelo menos 10 caracteres.";
    - `too_common` → "Essa senha é muito comum.";
    - `contains_email` → "A senha não pode conter seu email.".
  - `/conta` é dinâmica e redireciona para `/entrar?next=/conta` sem sessão.
  - **Header:** `Logo`, a navegação por categorias (vinda de `GET /v1/categories`), busca, Conta e "Carrinho" desabilitado com `title="Disponível na próxima versão"`.
  - **Footer:**
    - políticas vindas de `storefront/settings`;
    - links Privacidade, Termos e Créditos;
    - o `policies.demo_notice` ("Loja demonstrativa, nenhuma compra é real").
  - `instrumentation.ts`: `registerOTel({ serviceName: "storefront" })`, com `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`.

- [ ] **Step 1:** Escrever os testes Vitest das actions, com cliente e sessão mockados:
  - credencial inválida → `formError === "Email ou senha incorretos."`;
  - senha fraca → `fieldErrors.password` contém "Use pelo menos 10 caracteres.";
  - sucesso → `setTokens` chamado e `redirect("/conta")`.
- [ ] **Step 2:** Rodar `pnpm --filter storefront test`. Esperado: FAIL.
- [ ] **Step 3:** Implementar as páginas e actions. Os formulários usam `useActionState`, `<label>` explícito, `aria-invalid` e `aria-describedby` nos erros.
- [ ] **Step 4:** Rodar `pnpm --filter storefront test typecheck lint build`. Depois, com o compose de pé, abrir `http://katoshop.localhost/criar-conta`, criar uma conta e ver `/conta` com o nome. Esperado: PASS e fluxo ok.
- [ ] **Step 5:** Commit `feat(storefront): base da loja, cadastro, login e conta via BFF`.

### Task 19: Loja, catálogo (home, listagens, busca e produto)

**Files:**
- Create:
  - `app/(shop)/page.tsx`, `app/(shop)/c/[categoria]/page.tsx`, `app/(shop)/colecoes/[slug]/page.tsx`, `app/(shop)/busca/page.tsx`, `app/(shop)/p/[slug]/page.tsx`;
  - `components/{product-card.tsx,product-grid.tsx,filters-panel.tsx,sort-select.tsx,load-more.tsx,pdp-gallery.tsx,variant-picker.tsx,size-guide-dialog.tsx,price-block.tsx}`;
  - `lib/{filters.ts,pdp.ts}`, `content/size-guide.ts`, `app/sitemap.ts`, `app/robots.ts`;
  - `test/{filters.test.ts,pdp.test.ts}`.

**Interfaces:**
- Produces:
  - `lib/filters.ts`:
    - `type CatalogFilters = { size: string[]; color: string[]; priceMin?: number; priceMax?: number; sort: "relevance"|"newest"|"price_asc"|"price_desc"; q?: string }`;
    - `parseFilters(sp: Record<string, string | string[] | undefined>): CatalogFilters`. Preço na URL em reais inteiros (`preco_min=100`), convertido para centavos. Valores inválidos são ignorados;
    - `toSearchParams(f: CatalogFilters): URLSearchParams`. Nomes na URL: `tamanho`, `cor`, `preco_min`, `preco_max`, `ordem`, `q`.
  - `lib/pdp.ts`:
    - `sizeStates(detail: ProductDetail, color: string): { code: string; label: string; state: "available" | "sold_out" | "absent" }[]` na ordem dos tamanhos do detalhe;
    - `imagesForColor(images, color)`: imagens da cor primeiro, depois as genéricas (`color_code === null`), preservando `position`;
    - `findVariant(detail, color, size)`.
  - **Home:** hero com `settings.hero` (título em Anton, subtítulo, CTA primário `Button primary` e secundário `secondary`, imagem `priority`), as coleções de `featured_collection_slugs`, a grade "Novidades" (8 itens, `newest`) e uma faixa de políticas. Revalidação de 60 s (`export const revalidate = 60`).
  - **Listagens:**
    - `FiltersPanel` vira coluna fixa em ≥1024px e `Dialog` "Filtrar" no mobile, com contadores das facetas;
    - "Carregar mais" usa `next_cursor` via server action que devolve os próximos cards.
  - **Página de produto:**
    - cor e tamanho vêm da URL (`?cor=PRT&tamanho=M`), assim o estado é compartilhável e funciona sem JS para a escolha de cor;
    - tamanho `sold_out` aparece riscado, com `aria-disabled` e o texto acessível "esgotado";
    - `PriceBlock` mostra `formatBRL`, "ou {count}x de {each} sem juros" e "{percent}% off no Pix: {pix}", a partir de `policies`;
    - o botão primário "Adicionar ao carrinho" fica `disabled`, com a nota "Carrinho chega na próxima versão";
    - o guia de medidas usa `content/size-guide.ts`: tabela de medidas por categoria (camisetas, moletons, calças) em cm, marcada como "medidas da loja demo";
    - metadata e Open Graph com a primeira imagem, JSON-LD `Product` com `offers` (`price`, `priceCurrency: "BRL"`, `availability`) e sem `aggregateRating`.
  - `sitemap.ts` lista a home, as categorias, as coleções e todos os produtos ativos (paginando a API).

- [ ] **Step 1:** Escrever os testes:
  - `parseFilters({tamanho: ["M","G"], cor: "PRT", preco_min: "100", ordem: "xyz"})` → `{size: ["M","G"], color: ["PRT"], priceMin: 10000, sort: "newest"}`;
  - `toSearchParams(parseFilters(x))` faz o caminho de ida e volta;
  - `sizeStates` com G sem estoque na cor PRT e XG inexistente → `G: "sold_out"` e `XG: "absent"`;
  - `imagesForColor` ordena as da cor antes das genéricas.
- [ ] **Step 2:** Rodar `pnpm --filter storefront test`. Esperado: FAIL.
- [ ] **Step 3:** Implementar as páginas e componentes. Imagens via `next/image` com `remotePatterns` para `api.katoshop.localhost/catalog/v1/media/**` e `sizes` declarado em cada uso.
- [ ] **Step 4:** Rodar `pnpm --filter storefront test typecheck lint build`. Com o compose e dados de seed (criar à mão via admin API se a Tarefa 23 ainda não existir), conferir em `katoshop.localhost`: filtros, busca, carregar mais, troca de cor e esgotado. Esperado: PASS e comportamento visto no navegador.
- [ ] **Step 5:** Commit `feat(storefront): home, listagens com filtros, busca e página de produto`.

### Task 20: Loja, páginas legais, créditos, erros e ícones

**Files:**
- Create: `app/privacidade/page.tsx`, `app/termos/page.tsx`, `app/creditos/page.tsx`, `content/{privacidade.md,termos.md}`, `app/not-found.tsx`, `app/error.tsx`, `app/manifest.ts`, `app/icon.svg`, `app/apple-icon.png` (copiados de `packages/ui/src/brand/generated`)
- Test: `test/legal-content.test.ts`

**Interfaces:**
- Produces:
  - **Privacidade:** `/privacidade` traz o texto modelo baseado na LGPD (controlador fictício "KatoShop (loja demonstrativa)", dados coletados: nome, email, endereço a partir da fatia 3; finalidade; base legal; direitos do titular; contato `privacidade@katoshop.localhost`), com o aviso "Modelo para loja demonstrativa".
  - **Termos:** `/termos` com cadastro, preços, trocas em 30 dias, foro e o mesmo aviso de modelo.
  - **Créditos:** `/creditos` consome `GET /v1/credits` e lista autor, link de origem e licença de cada foto.
  - **Erros:** `not-found` e `error` usam a identidade da marca. O `error` mostra "Código para suporte: {digest}" e um botão "Tentar de novo".
  - **Manifest:** nome "KatoShop", `theme_color #0E0E0E`, ícones 192/512.

- [ ] **Step 1:** Escrever `legal-content.test.ts`: ler `content/*.md` e as strings de UI em `app/**` e `components/**` e garantir que nenhum contém `—` ou `–`. O teste fica na suíte como guarda permanente da regra.
- [ ] **Step 2:** Rodar. Esperado: FAIL (arquivos ausentes).
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar `pnpm --filter storefront test build`. Esperado: PASS. Conferir no navegador que o favicon aparece na aba e que os três links do rodapé abrem.
- [ ] **Step 5:** Commit `feat(storefront): privacidade, termos, créditos, páginas de erro e ícones`.

### Task 21: Admin, base, login, layout e visão geral

**Files:**
- Create:
  - `apps/admin/{package.json,next.config.ts,tsconfig.json,instrumentation.ts,Dockerfile}`;
  - `app/layout.tsx`, `app/entrar/{page.tsx,actions.ts}`, `app/(painel)/layout.tsx`, `app/(painel)/page.tsx`;
  - `components/{sidebar.tsx,demo-badge.tsx,page-header.tsx}`;
  - `lib/{api.ts,session.ts,guard.ts}`, `proxy.ts`, `test/guard.test.ts`.
- Modify: `infra/compose.yaml` (serviço `admin`, rota `Host(admin.katoshop.localhost)`)

**Interfaces:**
- Produces:
  - `lib/session.ts` exporta `session = createSession({cookiePrefix: "ka", audience: "admin", ...})`.
  - `proxy.ts` (o middleware do Next 16) redireciona para `/entrar` se o cookie `ka_rt` estiver ausente, em qualquer rota fora de `/entrar` e dos assets.
  - `lib/guard.ts` exporta `requireStaff(): Promise<Me>`, que chama `GET /v1/me` com `withAuth`. Se `kind !== "staff"`, limpa a sessão e redireciona para `/entrar?erro=acesso`.
  - **Sidebar:**
    - itens ativos: Visão geral, Produtos, Categorias, Coleções;
    - itens desabilitados com o rótulo "Fatia N": Pedidos (3), Cupons (2), Frete (3), Clientes (4), Vitrine (4), Saúde do sistema (4), Auditoria (4);
    - o link ativo usa fundo accent;
    - `DemoBadge` ("dados demo") fica no topo de toda página do painel.
  - **Visão geral:** consome `GET /v1/admin/overview` e mostra cards de produtos por status, variantes sem estoque e a tabela dos últimos movimentos.

- [ ] **Step 1:** Escrever o teste de `requireStaff`, com cliente mockado: `kind: "customer"` → `session.clear` chamado e `redirect("/entrar?erro=acesso")`; `kind: "staff"` → devolve `me`.
- [ ] **Step 2:** Rodar `pnpm --filter admin test`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. O login usa `POST /v1/auth/staff/login`.
- [ ] **Step 4:** Rodar `pnpm --filter admin test typecheck lint build`. Com o compose de pé, entrar com `admin@katoshop.localhost` / `katoshop-demo-2026` e ver a visão geral. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(admin): login de funcionário, layout com barra lateral e visão geral`.

### Task 22: Admin, gestão de catálogo

**Files:**
- Create:
  - `app/(painel)/produtos/{page.tsx,novo/page.tsx,[id]/page.tsx,[id]/actions.ts}`;
  - `app/(painel)/produtos/[id]/variantes/[vid]/estoque/{page.tsx,actions.ts}`;
  - `app/(painel)/categorias/{page.tsx,actions.ts}`, `app/(painel)/colecoes/{page.tsx,[id]/page.tsx,actions.ts}`;
  - `components/{product-form.tsx,variant-grid.tsx,variant-generator.tsx,image-manager.tsx,publish-checklist.tsx,stock-adjust-form.tsx,data-table.tsx,reorder-list.tsx}`;
  - `lib/problem-messages.ts`, `test/{problem-messages.test.ts,reorder.test.ts}`.

**Interfaces:**
- Produces:
  - `lib/problem-messages.ts` exporta `messageFor(code: string): string`, com pelo menos:
    - `catalog.product.version_conflict` → "Este produto foi alterado por outra pessoa. Recarregue para ver a versão atual.";
    - `catalog.product.slug_taken` → "Já existe um produto com este endereço.";
    - `catalog.stock.would_go_negative` → "O estoque não pode ficar negativo.";
    - `catalog.image.too_large` → "A imagem passa de 8 MB.";
    - `catalog.image.unsupported_type` → "Envie JPG, PNG ou WebP.";
    - `catalog.category.in_use` → "Há produtos nesta categoria.";
    - os blockers `no_active_variant`, `no_image` e `no_price` com textos pt-BR;
    - fallback "Algo deu errado. Código para suporte: {traceId}".
  - `reorder-list.tsx` exporta a função pura `move<T>(items: T[], from: number, to: number): T[]`. O componente usa drag-and-drop nativo mais os botões "Mover para cima" e "Mover para baixo" (acessíveis por teclado). É usado em fotos e em produtos da coleção.
  - **`/produtos`:** `DataTable` (TanStack Table) com busca, filtro por status e categoria e paginação por cursor.
  - **`/produtos/[id]`:** abas Dados, Variantes, Fotos, Publicação.
    - **Dados:** formulário com `version` oculto. No 409, mostra a mensagem com o botão "Recarregar".
    - **Variantes:** grade cor × tamanho com preço (vazio = base), ativo e estoque disponível, e um link para o livro razão. O gerador permite multisseleção de cores e tamanhos.
    - **Fotos:** upload múltiplo, alt obrigatório, cor e créditos (autor, URL, licença), reordenação.
    - **Publicação:** checklist a partir dos blockers e botões Publicar ou Arquivar.
  - **Estoque:** tabela de movimentos (data, delta com sinal, motivo, nota, autor) e um formulário de ajuste com motivo (`adjustment`, `damage`, `return`, `initial`).

- [ ] **Step 1:** Escrever os testes:
  - `messageFor("catalog.product.version_conflict")` contém "alterado por outra pessoa";
  - código desconhecido → fallback com o `traceId`;
  - `move(["a","b","c"], 0, 2)` → `["b","c","a"]`;
  - `move` com índice fora do intervalo devolve uma cópia inalterada.
- [ ] **Step 2:** Rodar `pnpm --filter admin test`. Esperado: FAIL.
- [ ] **Step 3:** Implementar as páginas, actions e componentes. O upload de fotos vai por uma server action que repassa o `FormData` para a API, com o limite de corpo do Next ajustado para 9 MB em `next.config.ts` (`serverActions.bodySizeLimit`).
- [ ] **Step 4:** Rodar `pnpm --filter admin test typecheck lint build`. No navegador: criar um produto, gerar a grade, ajustar o estoque, enviar uma foto, publicar e ver na loja em até 60 s. Esperado: PASS e fluxo ok.
- [ ] **Step 5:** Commit `feat(admin): produtos, variantes, fotos, publicação, estoque, categorias e coleções`.

### Task 23: Seed demo com fotos reais creditadas

**Files:**
- Create: `scripts/seed/{__init__.py,__main__.py,client.py,data.py,images.json}`, `scripts/seed/tests/test_manifest.py`, `scripts/seed/Dockerfile`
- Modify: `infra/compose.yaml` (serviço `seed` no perfil `seed`), `package.json` (`seed` = `docker compose --profile seed run --rm seed`)

**Interfaces:**
- Produces:
  - **`images.json`:** lista de `{id, source_url, download_url, author, license, sha256, alt, used_by: [product_slug], color_code?}`.
    - **Curadoria:** 30 a 40 fotos reais de roupas (camiseta, moletom, calça, bermuda, boné, meia, bolsa) do Unsplash (Unsplash License) ou do Pexels (Pexels License), com pelo menos uma foto por produto e uma foto de hero (pessoa vestindo streetwear em contexto urbano).
    - **Proibido:** imagens geradas por IA. Rejeitar fotos com tag ou descrição "AI generated", contas que publicam arte gerada e conteúdo Unsplash+ pago.
    - **Hash:** registrar o `sha256` do arquivo baixado no momento da curadoria.
  - **`data.py`:** 4 categorias, as 3 coleções "Drop Inverno 26", "Básicos pesados" e "Rua à noite" e cerca de 24 produtos.
    - Cada produto tem nome, descrição, atributos (material, gramatura, modelagem, cuidados), preço base entre R$ 69 e R$ 429, cores, tamanhos e estoque por variante.
    - Pelo menos 6 variantes ficam com estoque 0 e 2 produtos ficam totalmente esgotados.
    - Os nomes e as cores são escritos para bater com o que aparece nas fotos.
  - Ainda em `data.py`, as `StorefrontSettings`:
    - hero "Streetwear para andar, não para guardar" e "Camisetas, moletons e calças em tecido pesado, do P ao XGG";
    - CTA "Ver o drop atual" → `/colecoes/drop-inverno-26` e secundário "Todas as peças" → `/busca`;
    - `pix_discount_percent=5`, `max_installments=3`;
    - textos de frete e troca, e `demo_notice="Loja demonstrativa, nenhuma compra é real"`.
  - **`python -m seed`:**
    1. faz login como admin;
    2. faz upsert por slug (via `GET /v1/admin/...?slug=`) de categorias, coleções e produtos, gera variantes e define o estoque com movimento `initial` só se a variante for nova;
    3. baixa cada imagem para o cache `scripts/seed/.cache/` (gitignored), confere o `sha256` (divergência aborta com mensagem clara) e faz upload com créditos;
    4. publica os produtos e grava as settings.

    Rodar duas vezes não duplica nada.

- [ ] **Step 1:** Escrever `test_manifest.py`:
  - todo produto de `data.py` tem pelo menos uma imagem em `images.json`;
  - toda imagem tem `author`, `source_url` em `unsplash.com` ou `pexels.com`, `license` em `{"Unsplash License","Pexels License"}` e `sha256` com 64 hex;
  - nenhum texto de `data.py` contém `—` ou `–`.
- [ ] **Step 2:** Rodar `uv run pytest scripts/seed -q`. Esperado: FAIL.
- [ ] **Step 3:** Fazer a curadoria das fotos (é tarefa de julgamento: abrir cada foto, confirmar que é uma fotografia real e combina com o produto), escrever `data.py` e implementar o cliente e o `__main__`.
- [ ] **Step 4:** Rodar `uv run pytest scripts/seed -q`, depois `pnpm seed` duas vezes. Conferir no admin a contagem (24 produtos ativos) e na loja `/creditos` com todas as fotos listadas. Esperado: PASS, contagens iguais nas duas execuções e loja populada.
- [ ] **Step 5:** Commit `feat(seed): loja demo com fotos reais creditadas e seed idempotente`.

### Task 24: E2E, Lighthouse e CI completa

**Files:**
- Create: `e2e/{package.json,playwright.config.ts,lighthouserc.json}`, `e2e/tests/{admin-to-store.spec.ts,browse-filter.spec.ts,customer-auth.spec.ts,customer-blocked-from-admin.spec.ts}`, `.github/workflows/ci-e2e.yml`
- Modify: `package.json` (`test:e2e` = `pnpm --filter e2e test`)

**Interfaces:**
- Consumes: o compose completo com seed (Tarefas 15 a 23).
- Produces:
  1. `admin-to-store`: entra no admin, cria "Camiseta E2E {timestamp}" em Camisetas, gera PRT×(P,M), ajusta o estoque de P para 3, envia a foto (o teste baixa a imagem de um produto do seed via `/v1/media/...` e a reenvia), publica e, na loja, faz polling em `/busca?q=E2E {timestamp}` até 70 s até o card aparecer;
  2. `browse-filter`: em `/c/moletons`, marca o tamanho M e a cor PRT → todos os cards mostram cor preta; abre um produto que tenha um tamanho esgotado → o botão desse tamanho tem `aria-disabled="true"`;
  3. `customer-auth`: cria conta → `/conta` mostra o nome → sair → `/conta` redireciona para `/entrar`;
  4. `customer-blocked-from-admin`: com credenciais de cliente no login do admin → mensagem "Email ou senha incorretos." e permanece em `/entrar`.

  - `lighthouserc.json`: preset desktop em `http://katoshop.localhost/` e numa página de produto do seed, com asserções `categories:accessibility >= 0.95` e `categories:performance >= 0.9`.
  - `ci-e2e.yml` (em `pull_request` e `push` para `main`):
    - `python scripts/gen_keys.py`;
    - `docker compose up -d --build --wait`;
    - `pnpm seed`;
    - `pnpm exec playwright install --with-deps chromium`;
    - `pnpm test:e2e`;
    - `pnpm --filter e2e lhci`;
    - upload do relatório com `actions/upload-artifact@v7.0.2` em caso de falha.

- [ ] **Step 1:** Escrever os 4 specs.
- [ ] **Step 2:** Rodar `pnpm test:e2e` com o compose sem seed. Esperado: FAIL (produtos ausentes).
- [ ] **Step 3:** Rodar `pnpm seed`, criar `playwright.config.ts` (`baseURL` da loja, `projects` chromium, `retries: 1` só na CI) e o `lighthouserc.json`.
- [ ] **Step 4:** Rodar `pnpm test:e2e && pnpm --filter e2e lhci`. Esperado: 4 passed e as asserções do Lighthouse ok. Se a performance ficar abaixo de 0,9, corrigir a causa (tamanho de imagem, fontes, JS) antes de seguir; não afrouxar a meta.
- [ ] **Step 5:** Commit `test(e2e): fluxos de admin, loja e auth com Playwright e Lighthouse na CI`.

### Task 25: Documentação (README e ADRs)

**Files:**
- Create: `docs/adr/{0001-microsservicos-banco-por-servico.md,0002-saga-orquestrada.md,0003-rabbitmq.md,0004-estoque-no-catalog.md,0005-bff-cookies-httponly.md,0006-validacao-jwt-por-servico.md}`, `docs/architecture.md`
- Modify: `README.md`

**Interfaces:**
- Produces:
  - **ADRs** no formato Contexto / Decisão / Consequências / Alternativas consideradas, com 1 página cada, tirados das seções 2 e 3 da spec e das decisões deste plano. Os desvios entram como consequências no ADR correspondente:
    - `min_price_cents` denormalizado;
    - janela de 10 s no reuso de refresh;
    - `PUT /storefront/settings` usado só pelo seed;
    - disco local no lugar do MinIO.
  - **`docs/architecture.md`:** o diagrama da spec 3, a tabela de responsabilidades e a lista de eventos previstos.
  - **README:**
    - o que é (1 parágrafo direto);
    - status da fatia (1 de 5);
    - pré-requisitos (Docker Desktop, Node 24 + pnpm 12, uv);
    - `pnpm install && pnpm dev:up && pnpm seed`;
    - URLs (loja, admin, Jaeger, Grafana, dashboard do Traefik);
    - credencial demo do admin;
    - como rodar os testes;
    - mapa de pastas e links para os ADRs;
    - roadmap das fatias;
    - licença MIT e créditos das fotos.

    Os GIFs entram na fatia 5. Aqui fica uma screenshot da home e uma da página de produto em `docs/img/`.

- [ ] **Step 1:** Escrever os arquivos.
- [ ] **Step 2:** Verificar:
  - `grep -rn "—\|–" README.md docs/adr docs/architecture.md` → nenhum resultado;
  - todos os links relativos do README apontam para arquivos existentes (`pnpm dlx markdown-link-check README.md`, ou checagem manual).
- [ ] **Step 3:** Seguir o README do zero numa cópia limpa (`git clone` para uma pasta temporária, `pnpm install && pnpm dev:up && pnpm seed`). Esperado: a loja abre populada em até 5 min (critério de aceite 1).
- [ ] **Step 4:** Commit `docs: README da fatia 1, arquitetura e ADRs 0001 a 0006`.
- [ ] **Step 5:** Conferir os critérios de aceite 1 a 9 da spec 8.1, um por um, anotando a evidência (comando e saída, ou screenshot) na descrição do commit final ou no PR.
