# KatoShop Fatia 2 (carrinho reativo a eventos e motor de cupons) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A fatia 2 entrega quatro coisas:
- RabbitMQ com outbox no catalog;
- o serviço `cart` (Redis), que reage a eventos de preço, estoque e arquivamento;
- o serviço `promotions` (motor de cupons);
- o carrinho na loja e o CRUD de cupons no admin.

Tudo fica coberto por testes de integração e e2e.

**Architecture:**
- **Eventos:** o catalog grava eventos numa tabela `outbox` na mesma transação da mudança. Um relay no próprio processo publica esses eventos no exchange `catalog.events`.
- **Carrinho:** o `cart` guarda uma cópia dos dados do item no Redis, mantida atualizada pelo consumo desses eventos. Ele consulta o catalog e o promotions por REST interno, autenticado com token de serviço emitido pelo identity.
- **Loja:** os BFFs Next.js chamam `/cart` e `/promotions` pelo Traefik.

**Tech Stack:**
- serviços em Python 3.15.2 + FastAPI 0.162.5, SQLAlchemy 2.1, aio-pika 10.2.3, redis-py 8.1.0 (asyncio);
- infraestrutura RabbitMQ 4.4 (management-alpine) e Redis 8.x (alpine);
- frontends em Next.js 16.4.6 e TypeScript 6.0.3;
- testes com testcontainers 4.15.0 (postgres, rabbitmq, redis) e Playwright.

**Spec:** `docs/superpowers/specs/2026-11-13-katoshop-fatia-2-design.md`. A spec geral (`2026-10-23-katoshop-design.md`) e as decisões R1 a R29 da fatia 1 continuam valendo; estão registradas no README ("Limitações conhecidas") e nos ADRs 0001 a 0007. Leia a spec da fatia 2 inteira antes de qualquer tarefa.

## Global Constraints

- **Versões:** a versão estável mais nova de cada dependência, conferida no registry na hora de fixar, com pin exato (`CLAUDE.md`). Pontos de partida conferidos em 2026-11-13:
  - aio-pika 10.2.3;
  - redis (py) 8.1.0;
  - opentelemetry-instrumentation-aio-pika e opentelemetry-instrumentation-redis 0.66b2 (mesma linha das outras instrumentações);
  - testcontainers 4.15.0 com os extras `rabbitmq` e `redis`;
  - imagem `rabbitmq:4.4.0-management-alpine`;
  - imagem `redis` na última `8.x.y-alpine` estável;
  - uv 0.13.7;
  - TypeScript continua em 6.0.3 (R17).
- **Python:** `requires-python = ">=3.15,<3.16"`, imagem `python:3.15.2-slim`. Os novos serviços copiam a estrutura de `services/catalog` (src layout; pytest com `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"` e `filterwarnings = ["error"]`; dev group com `katoshop-platform[testing]`). Cada um registra seu pacote em `known-first-party` do ruff.
- **Rodar ferramentas no Windows:** `uv run python -m pytest|pyright|ruff`, porque o App Control bloqueia `.venv/Scripts/*.exe`. Cada pacote Python roda os testes em invocação separada.
- **Erros:** problem+json com `code` no formato `<serviço>.<área>.<motivo>`. Dinheiro sempre em `_cents` inteiros. IDs em UUIDv7. Exceção: o `cart_id` de visitante é UUIDv4, aleatório e opaco.
- **Token de serviço:** `aud="service"`, `kind="service"`, `sub=<client_id>` (string), `roles=[]`, TTL de 300 s, emitido pelo identity em `POST /v1/auth/service-token`. Clientes desta fatia: `cart`.
- **Hosts:**
  - o gateway roteia `/cart/*` e `/promotions/v1/admin/*`;
  - ficam fora do Traefik `/v1/promotions/evaluate`, `/v1/internal/*` e `/v1/auth/service-token`;
  - o corpo do `/cart` é limitado a 64 KiB.
- **Mensageria:**
  - exchange `catalog.events` (topic, durável);
  - fila `cart.catalog-events` com bindings `catalog.variant.*.v1` e `catalog.product.archived.v1`;
  - espera de retry `cart.catalog-events.retry` com TTL 1 s, 5 s e 25 s;
  - DLQ `cart.catalog-events.dlq`;
  - o `traceparent` vai nos headers AMQP.
- **UI:** valem todas as regras do `CLAUDE.md`. Sem travessões. Sem urgência ou contador falso; os avisos usam só dados reais. Botões com raio de 2px. Ícones lucide. Textos em pt-BR.
- **Commits:** pequenos, em pt-BR, no formato `tipo(escopo): descrição`, com a linha de atribuição do harness.

## Review Focus

1. **Duas abas adicionando ao mesmo carrinho ao mesmo tempo:** nenhuma das duas inclusões se perde. O Redis usa WATCH/MULTI com até 5 retentativas e devolve 409 `cart.cart.concurrent_update` só se todas falharem. Teste na Tarefa 11.
2. **Evento de uma variante cujo carrinho já expirou** (índice reverso aponta para uma chave inexistente): o consumidor ignora, remove o carrinho órfão do índice e não falha nem manda para a DLQ. Teste na Tarefa 13.
3. **Código de cupom digitado com espaços e minúsculas** (`" bemvindo10 "`): é normalizado com `strip().upper()` e funciona. Código com caracteres fora de `^[A-Z0-9-]{3,32}$` responde 422 `request.validation`, nunca 500. Testes na Tarefa 8 (evaluate e admin) e na Tarefa 12 (`PUT /coupon`).
4. **RabbitMQ fora do ar enquanto o admin altera preço ou estoque:** a escrita no catalog continua funcionando, porque o evento fica na outbox. Quando o broker volta, o relay publica, e o carrinho converge. Teste na Tarefa 4.
5. **`X-Cart-Id` forjado ou de outra pessoa:**
   - ID inexistente: resposta de carrinho vazio, sem criar nada;
   - ID de um carrinho de cliente enviado como visitante: tratado como inexistente;
   - ID com formato inválido: 422 `cart.cart.invalid_id`.

   Teste na Tarefa 12.

---

## Mapa de arquivos

```
libs/py/platform/src/ks_platform/
  auth.py               (+ ServicePrincipal, require_service)
  service_tokens.py     ServiceTokenProvider (cliente com cache)
  events.py             Envelope, new_event()
  outbox.py             outbox_table(), add_event(), OutboxRelay
  messaging.py          Topologia AMQP, publisher, EventConsumer (retry/DLQ)
  testing.py            (+ fixtures rabbitmq_url, redis_url)
services/identity/src/identity/  (+ service-token: domain/tokens.py, api/routes_service.py, settings)
services/catalog/src/catalog/    (+ migração 0003_outbox, eventos no admin_service, relay no lifespan, api/routes_internal.py)
services/promotions/src/promotions/
  main.py settings.py
  domain/coupons.py            regras, avaliação, rateio (puro)
  application/ports.py admin_service.py evaluate_service.py
  adapters/models.py repositories.py
  api/schemas.py routes_admin.py routes_evaluate.py errors.py
  migrations/versions/0001_initial.py
services/cart/src/cart/
  main.py settings.py
  domain/cart.py               modelo, adicionar, merge, eventos, avisos, totais (puro)
  application/cart_service.py ports.py
  adapters/redis_repo.py catalog_client.py promotions_client.py consumer.py
  api/schemas.py routes.py errors.py
apps/storefront/  (+ lib/cart.ts, app/(shop)/carrinho/, ações de carrinho, merge no login/cadastro)
apps/admin/       (+ app/(painel)/cupons/, lib/coupons.ts)
infra/            (+ rabbitmq, redis, cart, promotions no compose; traefik; postgres-init; grafana)
scripts/          (+ export_openapi para cart/promotions; seed de cupom demo)
e2e/tests/        (+ 4 specs da fatia 2)
docs/adr/0008-outbox-e-mensageria.md  0009-token-de-servico.md
```

---

### Task 1: ks_platform, principal de serviço e cliente de token

**Files:**
- Modify: `libs/py/platform/src/ks_platform/auth.py`
- Create: `libs/py/platform/src/ks_platform/service_tokens.py`
- Test: `libs/py/platform/tests/test_service_auth.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ServicePrincipal: client_id: str`.
  - `def require_service() -> Callable[..., Awaitable[ServicePrincipal]]`:
    - sem token → 401 `auth.missing_token`;
    - token de usuário válido (aud diferente de `service`) → 403 `auth.forbidden`;
    - token inválido → 401 `auth.invalid_token`.
  - `TokenVerifier.verify(token, audience)` passa a aceitar `audience="service"`. Nesse caso devolve `ServicePrincipal` quando `kind == "service"` e `sub` é string não vazia de até 64 caracteres. O caminho de `Principal` (storefront e admin) não muda.
  - `class ServiceTokenProvider`:
    - construtor `__init__(self, token_url: str, client_id: str, client_secret: str, *, http: httpx.AsyncClient | None = None, clock: Callable[[], float] = time.monotonic)`;
    - método `async def token(self) -> str`: guarda o token em cache e renova quando faltam ≤ 30 s para `expires_in`. Chamadas concorrentes compartilham uma única renovação (lock). Falha de rede ou 5xx levanta `ProblemError(503, "auth.service_token_unavailable")`.

- [ ] **Step 1: Testes.** Os testes usam chave Ed25519 local, como em `test_auth.py`:
  - `test_require_service_accepts_service_token`: `client_id == "cart"`;
  - `test_require_service_rejects_storefront_token_403`;
  - `test_require_service_missing_token_401`;
  - `test_service_token_with_uuid_sub_still_service`;
  - `test_provider_caches_until_30s_before_expiry`: `expires_in=300` com relógio falso; em t=0 e t=269 faz 1 chamada HTTP, em t=271 faz 2;
  - `test_provider_concurrent_calls_share_refresh`: `gather` de 5 chamadas resulta em 1 HTTP;
  - `test_provider_5xx_raises_503`.
- [ ] **Step 2:** Rodar `uv run python -m pytest libs/py/platform/tests/test_service_auth.py -q`. Esperado: FAIL, por ImportError.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar a suíte do platform. Esperado: PASS (a suíte antiga continua verde).
- [ ] **Step 5:** Commit `feat(platform): principal de serviço e cliente de token com cache`.

### Task 2: identity, emissão de token de serviço

**Files:**
- Modify: `services/identity/src/identity/domain/tokens.py`, `settings.py`, `main.py`
- Create: `services/identity/src/identity/api/routes_service.py`
- Test: `services/identity/tests/api/test_service_token.py`, `tests/unit/test_tokens.py` (casos novos)

**Interfaces:**
- Consumes: `ServicePrincipal` e `TokenVerifier` com aud `service` (Tarefa 1).
- Produces:
  - `SERVICE_TTL = timedelta(seconds=300)` e `issue_service_token(key: SigningKey, client_id: str, now: datetime) -> str`. Claims: `iss`, `sub=client_id`, `aud="service"`, `kind="service"`, `roles=[]`, `iat`, `exp`, `jti`. Mesma checagem de `now` naive.
  - `IdentitySettings.service_clients: dict[str, str]`, vindo do env `IDENTITY_SERVICE_CLIENTS` em JSON `{"cart": "<segredo>"}`, padrão `{}`. Segredo com menos de 32 caracteres impede o startup com erro claro.
  - `POST /v1/auth/service-token` com corpo `{client_id, client_secret}`:
    - sucesso → 200 `{access_token, token_type: "bearer", expires_in: 300}`;
    - credencial errada ou cliente desconhecido → 401 `identity.service.invalid_client` com corpo idêntico nos dois casos;
    - a comparação usa `hmac.compare_digest` sobre o SHA-256 dos dois lados.

- [ ] **Step 1: Testes:**
  - token emitido verificado pelo `TokenVerifier` → `ServicePrincipal("cart")`;
  - `exp - iat == 300`;
  - segredo errado e cliente desconhecido → corpos iguais (ignorando `trace_id`);
  - segredo curto no settings → `create_app` levanta erro;
  - corpo sem `client_secret` → 422.
- [ ] **Step 2:** Rodar `uv run python -m pytest services/identity -q`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. A rota não é roteada no Traefik; isso fica na Tarefa 14. Rodar `pnpm gen:api` e commitar o contrato.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(identity): token de serviço por client credentials`.

### Task 3: ks_platform, envelope, outbox e mensageria

**Files:**
- Create: `libs/py/platform/src/ks_platform/{events.py,outbox.py,messaging.py}`
- Modify: `libs/py/platform/src/ks_platform/testing.py` (fixtures `rabbitmq_url` e `redis_url`), `libs/py/platform/pyproject.toml` (aio-pika, instrumentação aio-pika; extras de testing `testcontainers[postgres,rabbitmq,redis]`)
- Test: `libs/py/platform/tests/test_events.py`, `test_outbox.py`, `test_messaging.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Envelope`, com campos `id: uuid.UUID`, `type: str`, `version: int`, `occurred_at: datetime`, `correlation_id: str | None`, `causation_id: str | None`, `producer: str`, `data: dict[str, Any]`, e os métodos `def to_json(self) -> bytes` e `@classmethod from_json(cls, raw: bytes) -> Envelope`. O `from_json` levanta `ValueError` se o JSON for inválido ou estiver sem campos.
  - `def new_event(type: str, producer: str, data: dict[str, Any], *, correlation_id: str | None = None) -> Envelope`. O `version` vem do sufixo `.vN` do type, e o id é UUIDv7.
  - `def outbox_table(metadata: MetaData) -> Table`, que cria a tabela `outbox` com `id uuid pk`, `type text`, `payload jsonb`, `created_at`, `published_at null`, `attempts int default 0` e índice parcial em `created_at WHERE published_at IS NULL`.
  - `async def add_event(session: AsyncSession, table: Table, event: Envelope) -> None`, que só faz INSERT. Quem chama controla a transação.
  - `class EventPublisher(Protocol)` com `async def publish(self, event: Envelope, routing_key: str) -> None` (só retorna depois do confirm).
  - `class AmqpPublisher(EventPublisher)`, com construtor `__init__(self, url: str, exchange: str)` e os métodos `async def connect()` e `async def close()`. Usa *publisher confirms*, mensagem persistente e o `traceparent` do contexto atual nos headers.
  - `class OutboxRelay`:
    - construtor `__init__(self, session_factory, table: Table, publisher: EventPublisher, *, batch_size: int = 100, interval_s: float = 1.0, retention: timedelta = timedelta(days=7))`;
    - `async def run_once(self) -> int`: lê até `batch_size` linhas com `FOR UPDATE SKIP LOCKED` em ordem de `created_at`, publica cada uma com routing key igual ao `type`, marca `published_at` e apaga as publicadas há mais tempo que `retention`. Em erro de publish, incrementa `attempts`, faz log de aviso, para o lote e devolve quantas publicou;
    - `async def run_forever(self, stop: asyncio.Event) -> None`;
    - expõe a métrica OTel `outbox.backlog` (gauge de linhas não publicadas).
  - `async def declare_consumer_topology(channel, *, exchange: str, queue: str, bindings: list[str], retry_delays_s: tuple[int, ...] = (1, 5, 25)) -> None`. Cria:
    - o exchange topic;
    - a fila principal;
    - uma fila de espera por delay (`<queue>.retry.<n>s`), com TTL e dead-letter de volta para a fila principal;
    - a DLQ `<queue>.dlq`.
  - `class EventConsumer`:
    - construtor `__init__(self, url: str, *, exchange: str, queue: str, bindings: list[str], handler: Callable[[Envelope], Awaitable[None]], retry_delays_s=(1, 5, 25))`;
    - o handler roda dentro de um span filho do `traceparent` recebido;
    - se o handler terminar ok → ack;
    - se levantar exceção → republica na fila de espera da tentativa `n` com o header `x-attempt=n+1` e dá ack. Depois da última espera, vai para a DLQ;
    - mensagem com envelope inválido → DLQ direto, sem retry;
    - métodos `async def start()` e `async def stop()`.
  - Fixtures de `ks_platform.testing`:
    - `rabbitmq_url` (session, `RabbitMqContainer("rabbitmq:4.4.0-management-alpine")`);
    - `redis_url` (session, `RedisContainer` com a mesma tag de imagem do compose).

- [ ] **Step 1: Testes:**
  - envelope: `to_json`/`from_json` fazem ida e volta; `version` é 1 para `x.y.z.v1`; JSON quebrado levanta `ValueError`;
  - outbox com Postgres real:
    - `test_add_event_rolled_back_leaves_no_row`;
    - `test_relay_publishes_and_marks_published` (publisher falso registra a routing key);
    - `test_relay_keeps_rows_when_publisher_fails_then_publishes` (falha na 1ª execução, sucesso na 2ª, e `attempts == 1`);
    - `test_relay_skip_locked_two_relays_no_duplicates` (dois relays concorrentes publicam cada linha uma vez);
    - `test_relay_deletes_rows_older_than_retention`;
  - mensageria com RabbitMQ real:
    - `test_publish_consume_roundtrip_with_traceparent` (o span do consumidor tem o mesmo trace_id do publisher);
    - `test_handler_failure_retries_then_dlq` (com `retry_delays_s=(0, 0, 0)` ou o menor TTL viável, o handler é chamado 4 vezes e a mensagem termina na DLQ);
    - `test_invalid_envelope_goes_straight_to_dlq`.
- [ ] **Step 2:** Rodar a suíte do platform. Esperado: FAIL.
- [ ] **Step 3:** Implementar. Os TTLs das filas de espera ficam parametrizáveis só para os testes.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS, com saída limpa (`filterwarnings=error`).
- [ ] **Step 5:** Commit `feat(platform): envelope, outbox com relay e consumidor com retry e DLQ`.

### Task 4: catalog, outbox e eventos de preço, estoque e arquivamento

**Files:**
- Create: `services/catalog/migrations/versions/0003_outbox.py`, `services/catalog/src/catalog/application/events.py`
- Modify: `services/catalog/src/catalog/adapters/models.py`, `adapters/repositories.py` (expor `uow.outbox`), `application/ports.py`, `application/admin_service.py`, `settings.py`, `main.py`, `pyproject.toml`
- Test: `services/catalog/tests/integration/test_outbox_events.py`, `tests/unit/test_events.py`

**Interfaces:**
- Consumes: `outbox_table`, `add_event`, `new_event`, `OutboxRelay` e `AmqpPublisher` (Tarefa 3).
- Produces:
  - `catalog.application.events`: `price_changed(variant, old_cents, new_cents) -> Envelope`, `stock_changed(variant) -> Envelope` e `product_archived(product) -> Envelope`. Os payloads seguem exatamente a spec §3.4. O `available` é `stock_on_hand - stock_reserved`, mas vale 0 quando a variante está inativa. O `version` é a `version` da variante depois da mudança.
  - `CatalogUnitOfWork.outbox` com `async def add(event: Envelope) -> None`.
  - Pontos de emissão em `AdminCatalogService`, todos dentro da mesma transação da escrita:
    - `update_product`: quando `base_price_cents` muda, gera um `price_changed` para cada variante com `price_cents IS NULL`, com o preço efetivo antigo e o novo;
    - `update_variant`: `price_changed` quando o preço efetivo muda; `stock_changed` quando `active` muda;
    - `adjust_stock`: `stock_changed`;
    - `archive`: `product_archived` com todos os `variant_ids`.
  - Novas settings: `CatalogSettings.amqp_url: str | None = None`. Sem `amqp_url`, o relay não sobe, mas a outbox continua sendo gravada (testes e dev sem broker).
  - O lifespan sobe `OutboxRelay(...).run_forever` como task e para no shutdown.

- [ ] **Step 1: Testes:**
  - unit: payloads de cada evento com os campos exatos; `available` vale 0 na variante inativa;
  - integração:
    - `test_adjust_stock_writes_stock_changed_in_same_tx`;
    - `test_base_price_change_emits_one_event_per_variant_without_own_price` (3 variantes, 1 com preço próprio → 2 eventos);
    - `test_variant_price_change_emits_price_changed_with_old_and_new`;
    - `test_deactivate_variant_emits_stock_changed_zero`;
    - `test_archive_emits_product_archived_with_all_variant_ids`;
    - `test_failed_write_rolls_back_event` (ajuste que deixaria estoque negativo → 422 e nenhuma linha na outbox);
    - **Review Focus 4**: `test_writes_succeed_while_broker_down_and_relay_catches_up` (RabbitMQ parado: o ajuste dá 201 e a linha fica pendente; com o RabbitMQ de volta, `run_once` publica e a fila de teste recebe);
  - o teste de drift do modelo contra a migração continua verde.
- [ ] **Step 2:** Rodar a suíte do catalog. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(catalog): outbox e eventos de preço, estoque e arquivamento`.

### Task 5: catalog, endpoint interno de variante

**Files:**
- Create: `services/catalog/src/catalog/api/routes_internal.py`
- Modify: `services/catalog/src/catalog/main.py`, `api/schemas.py`, `adapters/product_queries.py` (consulta por id)
- Test: `services/catalog/tests/api/test_internal_variants.py`

**Interfaces:**
- Consumes: `require_service` (Tarefa 1).
- Produces:
  - `GET /v1/internal/variants/{variant_id}` exige token de serviço e devolve `InternalVariant {variant_id, sku, product_id, product_slug, product_status, name, color_code, color_name, size_code, unit_price_cents, available, active, image_url, category_slug, collection_slugs, version}`. A `image_url` é a primeira imagem da cor ou a primeira genérica, ou `null`.
  - Variante inexistente → 404 `catalog.variant.not_found`. `variant_id` inválido → 422.

- [ ] **Step 1: Testes:**
  - com token de serviço → 200 com os campos exatos e `collection_slugs` ordenado;
  - token storefront → 403;
  - sem token → 401;
  - produto arquivado → 200 com `product_status: "archived"` (quem decide é o cart);
  - imagem da cor tem preferência sobre a genérica.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar e rodar `pnpm gen:api`.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(catalog): endpoint interno de variante para o carrinho`.

### Task 6: promotions, esqueleto, modelos e migração

**Files:**
- Create: `services/promotions/{pyproject.toml,Dockerfile,alembic.ini}`, `migrations/{env.py,versions/0001_initial.py}`, `src/promotions/{__init__.py,main.py,settings.py}`, `src/promotions/adapters/models.py`, `tests/conftest.py`, `tests/integration/test_migrations.py`, `.github/workflows/ci-promotions.yml`
- Modify: `pyproject.toml` (raiz: known-first-party), `uv.lock`

**Interfaces:**
- Produces:
  - `PromotionsSettings(BaseServiceSettings)` com prefixo `PROMOTIONS_`.
  - `create_app(settings)` com lifespan e dispose, no mesmo padrão do catalog: problem handlers, `install_db_error_handler`, observabilidade, health e `token_verifier`.
  - Tabelas da spec §5.1:
    - `coupons`, com CHECKs `kind IN ('percent','fixed')`, `value > 0`, `(kind <> 'percent' OR value <= 90)`, `code ~ '^[A-Z0-9-]{3,32}$'`, `ends_at > starts_at` quando ambos existem e limites `> 0`; índice único em `code`; `category_slugs text[] NOT NULL DEFAULT '{}'` e o mesmo para `collection_slugs`;
    - `coupon_redemptions`, com `order_id` único e FK RESTRICT para `coupons`.
  - Dockerfile com `exec uvicorn` e usuário não root. O `ci-promotions.yml` copia o `ci-catalog.yml` (com `--locked` e o próprio path).

- [ ] **Step 1: Testes:**
  - `test_upgrade_creates_tables`;
  - `test_checks_reject_invalid_rows` (percent 91, value 0, código minúsculo e `ends_at` antes de `starts_at` levantam IntegrityError);
  - drift do modelo contra a migração vazio;
  - `test_ready_ok`.
- [ ] **Step 2:** Rodar `uv run python -m pytest services/promotions -q`. Esperado: FAIL.
- [ ] **Step 3:** Implementar e rodar `docker build -f services/promotions/Dockerfile .`.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS e build ok.
- [ ] **Step 5:** Commit `feat(promotions): esqueleto, modelos de cupom e migração`.

### Task 7: promotions, domínio de avaliação

**Files:**
- Create: `services/promotions/src/promotions/domain/coupons.py`
- Test: `services/promotions/tests/unit/test_coupons.py`

**Interfaces:**
- Produces:
  - `normalize_code(raw: str) -> str` faz `strip().upper()`. Devolve `ValueError` se o resultado não casar `^[A-Z0-9-]{3,32}$`.
  - `@dataclass(frozen=True) class CouponRule`: `code`, `kind: Literal["percent","fixed"]`, `value: int`, `min_order_cents: int | None`, `starts_at: datetime | None`, `ends_at: datetime | None`, `category_slugs: frozenset[str]`, `collection_slugs: frozenset[str]`, `max_uses_total: int | None`, `max_uses_per_customer: int | None`, `active: bool`.
  - `@dataclass(frozen=True) class LineItem`: `variant_id: str`, `unit_price_cents: int`, `quantity: int`, `category_slug: str`, `collection_slugs: frozenset[str]`.
  - `@dataclass(frozen=True) class Evaluation`: `valid: bool`, `discount_cents: int`, `per_item: dict[str, int]`, `reason: str | None`, `min_order_cents: int | None`.
  - `evaluate(rule: CouponRule, items: list[LineItem], *, now: datetime, customer_id: str | None, uses_total: int, uses_by_customer: int) -> Evaluation`, na ordem de regras e com os códigos exatos da spec §5.2.
  - `allocate(discount_cents: int, eligible: list[LineItem]) -> dict[str, int]`:

```
peso_i = unit_price_cents_i * quantity_i
parte_i = floor(discount * peso_i / soma_pesos)
resto = discount - soma(parte_i)
a variante de maior peso recebe o resto (empate: menor variant_id)
```

- [ ] **Step 1: Testes:**
  - cada motivo da spec, um teste por motivo e na ordem: um cupom inativo e expirado ao mesmo tempo devolve `inactive`;
  - `percent` 10 sobre 29900 → 2990;
  - `fixed` 5000 com elegíveis de 3000 → 3000;
  - restrito a uma coleção, com um item elegível e outro não → desconto só no elegível;
  - `min_order_not_met` com `min_order_cents` na saída;
  - visitante com `max_uses_per_customer` → `login_required`;
  - `uses_total == max_uses_total` → `usage_limit_reached`;
  - bordas de data: `now == starts_at` é válido e `now == ends_at` é expirado;
  - teste com hypothesis: `sum(allocate(d, items).values()) == d` e nenhuma parte negativa nem maior que o peso do item;
  - `normalize_code(" bemvindo10 ") == "BEMVINDO10"` e `normalize_code("ab")` levanta ValueError (Review Focus 3).
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS, com cobertura ≥ 90% em `promotions.domain`.
- [ ] **Step 5:** Commit `feat(promotions): regras e cálculo de cupom com rateio`.

### Task 8: promotions, API de admin e avaliação interna

**Files:**
- Create: `services/promotions/src/promotions/{application/ports.py,application/admin_service.py,application/evaluate_service.py,adapters/repositories.py,api/schemas.py,api/routes_admin.py,api/routes_evaluate.py,api/errors.py}`
- Modify: `main.py`
- Test: `services/promotions/tests/api/test_admin_coupons.py`, `test_evaluate.py`

**Interfaces:**
- Consumes: o domínio da Tarefa 7, `require_permission("promotions.write")` e `require_service()`.
- Produces:
  - Rotas de admin exatamente como na spec §5.3, com corpo `CouponIn` e saída `CouponOut` (todos os campos, mais `uses_count`). Cursor por `(created_at desc, id desc)` usando o mesmo helper da lib do catalog, copiado para `promotions/application/cursor.py` (pequeno, sem dependência cruzada).
  - `POST /v1/promotions/evaluate` com `require_service()`:
    - corpo `EvaluateIn {code, customer_id?, items[1..50]}`, saída `EvaluateOut`;
    - código inexistente ou inválido → 200 `{valid: false, reason}` (o código malformado também vira `not_found`, porque o carrinho só mostra o motivo);
    - os usos vêm da contagem em `coupon_redemptions`.

- [ ] **Step 1: Testes:**
  - CRUD completo;
  - 409 `code_taken`;
  - 409 `version_conflict`;
  - PATCH que tenta mudar `code` → 422;
  - `DELETE` sem resgates → 204, e com um resgate inserido no teste → 409 `has_redemptions`;
  - ativar e desativar;
  - token de cliente → 403 e token de serviço → 403 nas rotas de admin;
  - evaluate: com token de serviço → 200 com desconto; com token de admin → 403; sem token → 401;
  - **Review Focus 3**: `test_evaluate_normalizes_code` (`" bemvindo10 "` → válido) e `test_admin_create_rejects_bad_code_422`;
  - itens vazios → 422.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar. Rodar `pnpm gen:api`, com o promotions adicionado ao `scripts/export_openapi.py`.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(promotions): API de cupons no admin e avaliação interna`.

### Task 9: cart, esqueleto e domínio puro

**Files:**
- Create: `services/cart/{pyproject.toml,Dockerfile}`, `src/cart/{__init__.py,main.py,settings.py}`, `src/cart/domain/cart.py`, `tests/conftest.py`, `tests/unit/test_cart_domain.py`, `.github/workflows/ci-cart.yml`
- Modify: `pyproject.toml` (raiz), `uv.lock`

**Interfaces:**
- Produces:
  - `CartSettings(BaseServiceSettings)` com prefixo `CART_`:
    - `redis_url`;
    - `amqp_url: str | None`;
    - `catalog_url`;
    - `promotions_url`;
    - `identity_token_url`;
    - `client_id = "cart"`;
    - `client_secret`;
    - `guest_ttl_s = 2592000`;
    - `max_lines = 50`;
    - `max_qty = 20`.

    O `database_url` não se aplica. Como `BaseServiceSettings` exige o campo, o cart herda e define o padrão `"unused://"` (documentar).
  - `create_app(settings)` com health em que o ready faz `PING` no Redis.
  - Domínio (puro, sem I/O):
    - `@dataclass class CartItem`: os campos da spec §4.1 mais `notice: Notice | None`;
    - `@dataclass(frozen=True) class Notice`: `code: Literal["price_changed","quantity_reduced","unavailable"]`, `old_price_cents: int | None`, `new_price_cents: int | None`, `quantity: int | None`;
    - `@dataclass class Cart`: `cart_id: str`, `owner: str`, `items: dict[str, CartItem]`, `coupon_code: str | None`, `version: int`.
  - Funções do domínio:
    - `add_item(cart, snapshot: CartItem, quantity: int, *, max_lines: int, max_qty: int) -> None` levanta `CartError(code, **extra)` com `cart.item.unavailable` (snapshot indisponível ou produto inativo), `cart.item.quantity_exceeds_stock` (com `max`), `cart.cart.too_many_lines` e `cart.item.quantity_limit` (acima de 20);
    - `set_quantity(cart, variant_id, quantity)`: 0 remove;
    - `apply_price_changed(item, new_price_cents, version) -> bool`;
    - `apply_stock_changed(item, available, version) -> bool`;
    - `apply_archived(item) -> bool`.

    As três funções `apply_*` devolvem `False` quando o evento é antigo (`version <= item_version`; o `archived` não tem versão e é sempre aplicado). Elas definem o `notice` conforme a spec §4.4, e a volta do estoque limpa o `unavailable` e põe a quantidade em 1.
    - `merge(account: Cart, guest: Cart, *, max_lines, max_qty) -> list[str]`: devolve os variant_ids com quantidade reduzida e aplica as regras da spec §4.3, incluindo a do cupom (chamada pelo service depois de validar);
    - `totals(cart) -> tuple[int, bool]`: `(subtotal_cents, checkout_blocked)`, ignorando os indisponíveis no subtotal.

- [ ] **Step 1: Testes do domínio:**
  - somar ao item existente respeita o disponível;
  - item 21 → `quantity_limit`;
  - 51 linhas → `too_many_lines`;
  - preço novo grava o aviso com o preço antigo e o novo;
  - evento com versão antiga é ignorado;
  - estoque abaixo da quantidade gera `quantity_reduced`, estoque 0 gera `unavailable`, e a volta do estoque gera quantidade 1 sem aviso;
  - o merge soma, limita ao disponível e reporta o que foi reduzido;
  - o subtotal ignora indisponível e `checkout_blocked` fica verdadeiro com item indisponível.
- [ ] **Step 2:** Rodar `uv run python -m pytest services/cart -q`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. Dockerfile e `ci-cart.yml` seguem o padrão dos outros serviços.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS, com cobertura ≥ 90% em `cart.domain`.
- [ ] **Step 5:** Commit `feat(cart): esqueleto e domínio do carrinho`.

### Task 10: cart, clientes de catalog e promotions

**Files:**
- Create: `services/cart/src/cart/adapters/{catalog_client.py,promotions_client.py}`
- Test: `services/cart/tests/unit/test_clients.py`

**Interfaces:**
- Consumes: `ServiceTokenProvider` (Tarefa 1) e os contratos das Tarefas 5 e 8.
- Produces:
  - `class CatalogClient`, com `async def variant(self, variant_id: str) -> CartItem | None`: devolve `None` no 404 e levanta `CartError("cart.catalog.unavailable", status=503)` em 5xx ou timeout de 2 s;
  - `class PromotionsClient`, com `async def evaluate(self, code: str, customer_id: str | None, items: list[CartItem]) -> CouponResult`:
    - `CouponResult {valid, discount_cents, per_item, reason, min_order_cents}`;
    - em 5xx ou timeout devolve `CouponResult(valid=False, reason="promotions.unavailable")`, sem levantar.
  - Os dois clientes mandam `Authorization: Bearer <token de serviço>` e usam `make_http_client`, que propaga o traceparent.

- [ ] **Step 1: Testes** com `httpx.MockTransport`:
  - o snapshot é mapeado corretamente;
  - 404 → `None`;
  - 503 → `CartError` 503;
  - o promotions em timeout → `promotions.unavailable`;
  - o header Bearer está presente.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(cart): clientes de catalog e promotions com token de serviço`.

### Task 11: cart, repositório Redis

**Files:**
- Create: `services/cart/src/cart/adapters/redis_repo.py`, `services/cart/src/cart/application/ports.py`
- Test: `services/cart/tests/integration/test_redis_repo.py`

**Interfaces:**
- Produces:
  - `class CartRepository(Protocol)` e a implementação `RedisCartRepository(redis: Redis, *, guest_ttl_s: int)` com:
    - `async def get(cart_id) -> Cart | None`;
    - `async def cart_for_user(user_id) -> Cart`, que cria se não existir;
    - `async def new_guest() -> Cart`;
    - `async def mutate(cart_id, fn: Callable[[Cart], T]) -> T`: faz WATCH em `cart:{id}` e em `cart:{id}:items`, aplica `fn` e escreve com MULTI incrementando `version`. Também atualiza o índice reverso `variant:{id}:carts` (adiciona e remove) e renova o TTL do visitante. São até 5 tentativas; depois levanta `CartError("cart.cart.concurrent_update", status=409)`;
    - `async def delete(cart_id)`;
    - `async def carts_for_variant(variant_id) -> set[str]` e `async def forget_variant_cart(variant_id, cart_id)`;
    - `async def processed(event_id) -> bool` e `async def mark_processed(event_id)` (SET com TTL de 7 dias, chave `processed_events:{id}`);
    - `async def cached_discount(cart_id, version)` / `async def cache_discount(cart_id, version, value)` com TTL de 30 s.
  - A serialização dos itens é um JSON por campo de hash, com chaves estáveis.

- [ ] **Step 1: Testes** com Redis real (fixture `redis_url`):
  - `test_mutate_increments_version_and_indexes_variant`;
  - `test_guest_ttl_set_and_renewed`;
  - `test_user_cart_has_no_ttl`;
  - `test_remove_item_updates_reverse_index`;
  - **Review Focus 1**: `test_concurrent_mutations_no_lost_update`, em que `gather` de 10 inclusões de SKUs distintos no mesmo carrinho termina com os 10 itens;
  - `test_processed_events_ttl`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar (redis-py asyncio, pin exato).
- [ ] **Step 4:** Rodar de novo. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(cart): repositório Redis com lock otimista e índice reverso`.

### Task 12: cart, serviço e API HTTP

**Files:**
- Create: `services/cart/src/cart/application/cart_service.py`, `services/cart/src/cart/api/{schemas.py,routes.py,errors.py}`
- Modify: `services/cart/src/cart/main.py`
- Test: `services/cart/tests/api/test_cart_api.py`

**Interfaces:**
- Consumes: as Tarefas 9, 10 e 11, e `require_audience("storefront")` como dependência opcional.
- Produces:
  - Rotas exatamente como na spec §4.3. A resposta `CartOut` traz `{cart_id, items: [ItemOut], subtotal_cents, discount_cents, total_cents, coupon: {code, valid, reason, min_order_cents} | null, checkout_blocked}`, e o `ItemOut` inclui `notice` e `line_discount_cents`.
  - Resolução da identidade:
    - token storefront → `cart_for_user`;
    - senão, `X-Cart-Id` que case com um UUIDv4 e aponte para um carrinho `guest:` existente;
    - senão, carrinho vazio (só o `POST /items` cria um novo e devolve `cart_id`).
  - `PUT /v1/cart/coupon`: normaliza o código, avalia e só grava se for válido. Inválido → 422 `cart.coupon.invalid` com `reason` e `min_order_cents`.
  - O `GET` reavalia o cupom com cache de 30 s (spec §4.5).
  - `POST /v1/cart/merge` exige token de cliente e devolve o carrinho resultante.

- [ ] **Step 1: Testes de API**, com Redis real e clientes falsos injetados em `app.state`:
  - o fluxo do visitante cria e devolve `cart_id`;
  - adicionar o mesmo SKU soma;
  - adicionar acima do estoque → 422 com `max`;
  - variante inexistente → 404 `cart.item.not_found`;
  - catalog fora → 503 `cart.catalog.unavailable`;
  - o cupom válido aparece no total;
  - cupom inválido → 422 com o motivo;
  - promotions fora → `GET` 200 com `coupon.reason == "promotions.unavailable"` e desconto 0;
  - o merge soma e apaga o carrinho do visitante;
  - `notices/ack` limpa os avisos;
  - `DELETE items/unavailable`;
  - **Review Focus 5**: `test_unknown_guest_id_returns_empty_without_creating`, `test_user_cart_id_as_guest_header_treated_as_unknown` e `test_malformed_cart_id_422`;
  - **Review Focus 3**: `test_put_coupon_normalizes_code`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar. Adicionar o cart ao `export_openapi.py` e rodar `pnpm gen:api`.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(cart): API do carrinho com cupom e merge`.

### Task 13: cart, consumidor de eventos do catalog

**Files:**
- Create: `services/cart/src/cart/adapters/consumer.py`
- Modify: `services/cart/src/cart/main.py` (o lifespan inicia o `EventConsumer` quando há `amqp_url`)
- Test: `services/cart/tests/integration/test_consumer.py`

**Interfaces:**
- Consumes: `EventConsumer` (Tarefa 3) e o repositório (Tarefa 11).
- Produces:
  - `async def handle_catalog_event(event: Envelope, repo: CartRepository) -> None`:
    - se `repo.processed(event.id)` → retorna;
    - para cada `cart_id` em `carts_for_variant`: faz `mutate` aplicando `apply_*`;
    - carrinho inexistente → `forget_variant_cart`;
    - no fim, `mark_processed`;
    - tipo de evento desconhecido → loga e marca como processado (não vai para a DLQ).
  - Fila, bindings e exchange exatamente como nas Global Constraints.

- [ ] **Step 1: Testes:**
  - com Redis e RabbitMQ reais e o catalog falso:
    - `test_price_event_updates_all_carts_with_notice`;
    - `test_duplicate_event_applied_once`;
    - `test_stale_version_ignored`;
    - `test_archived_marks_unavailable`;
    - **Review Focus 2**: `test_event_for_expired_cart_cleans_index`;
  - ponta a ponta com o catalog real em testcontainers não é necessário; isso fica no e2e.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar de novo. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(cart): consumidor de eventos do catálogo`.

### Task 14: infra, RabbitMQ, Redis, cart, promotions e gateway

**Files:**
- Modify: `infra/compose.yaml`, `infra/traefik/dynamic.yml`, `infra/postgres-init/01-databases.sh`, `infra/otel/collector.yaml` (se necessário), `infra/grafana/dashboards/` (novo `messaging.json`), `.env.example`, `libs/py/platform` (instrumentação aio-pika e Redis em `configure_observability`, ligadas quando os pacotes estiverem instalados)
- Test: verificação ao vivo (passos abaixo) e `libs/py/platform/tests/test_observability.py` (casos novos de instrumentação idempotente)

**Interfaces:**
- Produces:
  - **Serviços novos:**
    - `rabbitmq` com healthcheck `rabbitmq-diagnostics -q ping`, UI em `127.0.0.1:15672` e credenciais do env;
    - `redis` com `--appendonly yes --appendfsync everysec`, volume `redisdata` e healthcheck `redis-cli ping`;
    - `cart` e `promotions` com `mem_limit` (256m o cart, 256m o promotions, 256m o redis e 512m o rabbitmq), usuário não root e healthcheck em python.
  - **Postgres:** banco `promotions` com dono `promotions_svc`.
  - **Variáveis:** `IDENTITY_SERVICE_CLIENTS='{"cart":"..."}'` e `CART_CLIENT_SECRET` com o mesmo valor (dev). Os demais `*_AMQP_URL`, `CART_REDIS_URL`, `CART_CATALOG_URL=http://catalog:8000`, `CART_PROMOTIONS_URL=http://promotions:8000` e `CART_IDENTITY_TOKEN_URL=http://identity:8000/v1/auth/service-token` ficam no `.env.example` com valores de dev.
  - **Traefik:**
    - routers `cart` (`PathPrefix(/cart)`, stripPrefix, buffering com `maxRequestBodyBytes: 65536`) e `promotions-admin` (`PathPrefix(/promotions/v1/admin)`, strip `/promotions`);
    - nenhum router para `/v1/internal`, `/v1/promotions/evaluate` e `/v1/auth/service-token`;
    - um router de bloqueio explícito (priority alta, responde 404) para `/catalog/v1/internal` e `/identity/v1/auth/service-token`, para essas rotas não vazarem pelo router genérico do serviço.
  - **Grafana:** dashboard "KatoShop mensageria" com profundidade de `cart.catalog-events` e da DLQ (métricas de fila do RabbitMQ via plugin prometheus em `:15692`, scrape no Prometheus), taxa de consumo e `outbox.backlog`.

- [ ] **Step 1:** Rodar `pnpm dev:up` antes das mudanças. Esperado: não há cart nem promotions.
- [ ] **Step 2:** Fazer as alterações.
- [ ] **Step 3:** Verificar ao vivo, em ordem:
  - `docker compose ps` mostra tudo healthy;
  - `curl api.katoshop.localhost/cart/health/ready` → ok;
  - `curl api.katoshop.localhost/catalog/v1/internal/variants/<id>` → 404 pelo bloqueio;
  - `curl api.katoshop.localhost/identity/v1/auth/service-token` → 404;
  - `POST` de 70 KiB em `/cart/v1/cart/items` → 413;
  - a UI do RabbitMQ mostra a fila `cart.catalog-events` com consumidor;
  - ajustar o estoque pelo admin publica e o cart consome (log);
  - no Jaeger aparece um trace admin → catalog → (rabbitmq) → cart;
  - o Grafana mostra o painel com dados.

  Depois, `pnpm dev:down` (volumes mantidos).
- [ ] **Step 4:** Registrar as saídas no relatório.
- [ ] **Step 5:** Commit `feat(infra): rabbitmq, redis, cart e promotions no compose e no gateway`.

### Task 15: api-client e loja, carrinho de visitante e adicionar

**Files:**
- Modify: `packages/api-client/src/clients.ts` (`createCartClient`, `createPromotionsClient`), `apps/storefront/lib/api.ts`, `apps/storefront/components/variant-picker.tsx` (ou o componente que tem o botão), `apps/storefront/components/site-header.tsx`, `apps/storefront/app/(shop)/entrar/actions.ts`, `criar-conta/actions.ts`
- Create: `apps/storefront/lib/cart.ts`, `apps/storefront/app/(shop)/cart-actions.ts`
- Test: `apps/storefront/test/cart.test.ts`, `test/cart-actions.test.ts`

**Interfaces:**
- Consumes: o contrato do cart (Tarefa 12) e a sessão (R18).
- Produces:
  - `lib/cart.ts` (server-only):
    - `CART_COOKIE = "ks_cart"`;
    - `async function cartHeaders(): Promise<HeadersInit>`: Bearer se houver sessão, senão `X-Cart-Id` vindo do cookie;
    - `async function getCart(): Promise<CartView>`: só leitura, com `withAuth` sem refresh; em falha devolve um carrinho vazio com `unavailable: true`;
    - `async function cartCount(): Promise<number>`.
  - `addToCartAction(prev, formData)` em uma Server Action com `{variant_id, quantity}`:
    - grava o cookie `ks_cart` (httpOnly, sameSite lax, maxAge 2592000, secure pelo env) quando o cart devolve um `cart_id` novo e não há sessão;
    - devolve `{ok, message?, max?}`, com mensagens pt-BR por código (`cart.item.quantity_exceeds_stock` → "Só temos {max} unidades desse tamanho.");
    - usa `revalidatePath("/carrinho")`.
  - Na página de produto, o botão "Adicionar ao carrinho" fica habilitado quando cor e tamanho válidos estão selecionados. A nota "Carrinho chega na próxima versão" sai, e entra um toast (sonner) "Adicionado ao carrinho" com link "Ver carrinho".
  - O cabeçalho mostra "Carrinho (N)" linkando `/carrinho`, renderizado por requisição.
  - Login e cadastro, depois de gravar os tokens: se houver `ks_cart`, chamam `POST /v1/cart/merge` com o token novo e apagam o cookie. Falha no merge é logada e o cookie fica.

- [ ] **Step 1: Testes Vitest:**
  - `cartHeaders` com e sem sessão;
  - `addToCartAction` grava o cookie só para visitante novo;
  - mensagem de estoque;
  - login com `ks_cart` chama o merge e apaga o cookie;
  - merge falhando mantém o cookie e o login continua ok.
- [ ] **Step 2:** Rodar `pnpm --filter storefront test`. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar `pnpm --filter storefront test typecheck lint build`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(storefront): adicionar ao carrinho, contador e merge no login`.

### Task 16: loja, página do carrinho

**Files:**
- Create: `apps/storefront/app/(shop)/carrinho/{page.tsx,actions.ts}`, `apps/storefront/components/{cart-line.tsx,cart-summary.tsx,coupon-form.tsx,cart-notice.tsx}`, `apps/storefront/lib/cart-messages.ts`
- Test: `apps/storefront/test/cart-messages.test.ts`, `test/cart-page.test.ts`

**Interfaces:**
- Produces:
  - `messageForNotice(notice: Notice): string` com estas mensagens:

    | Aviso | Mensagem |
    |---|---|
    | `price_changed` | "O preço mudou de {old} para {new}." |
    | `quantity_reduced` | "Ajustamos a quantidade para {n}, que é o que temos em estoque." |
    | `unavailable` | "Este item esgotou ou saiu da loja. Remova para continuar." |

  - `messageForCoupon(reason, min?)` com estas mensagens:

    | Motivo | Mensagem |
    |---|---|
    | `not_found` | "Cupom não encontrado." |
    | `inactive` | "Este cupom não está ativo." |
    | `not_started` | "Este cupom ainda não começou a valer." |
    | `expired` | "Este cupom expirou." |
    | `no_eligible_items` | "Nenhum item do carrinho vale para este cupom." |
    | `min_order_not_met` | "Pedido mínimo de {min} para este cupom." |
    | `usage_limit_reached` | "Este cupom atingiu o limite de usos." |
    | `login_required` | "Entre na sua conta para usar este cupom." |
    | `customer_limit_reached` | "Você já usou este cupom." |
    | `promotions.unavailable` | "Não foi possível validar o cupom agora." |

  - Ações: `updateQuantityAction`, `removeItemAction`, `removeUnavailableAction`, `applyCouponAction`, `removeCouponAction` e `ackNoticesAction`. Todas são Server Actions com `{ refresh: true }` quando há sessão (R18) e terminam com `revalidatePath("/carrinho")`.
  - A página `/carrinho` segue a spec §8:
    - os botões − e + têm `aria-label` "Diminuir quantidade" e "Aumentar quantidade" e mostram o valor;
    - o preço aparece em mono limão;
    - "Finalizar compra" fica `disabled`, com a nota "Checkout chega na próxima versão";
    - com `checkout_blocked`, aparece o aviso "Remova os itens indisponíveis para continuar.";
    - o estado vazio mostra "Seu carrinho está vazio." com o CTA "Ver todas as peças" → `/busca`;
    - quando o cart está fora (`unavailable`), aparece a página de erro da marca (R22).
  - O teste de travessão (`legal-content.test.ts`) cobre os arquivos novos.

- [ ] **Step 1: Testes:**
  - cada mensagem com os valores formatados em BRL (normalizar NBSP);
  - `applyCouponAction` com 422 mostra o motivo;
  - a página renderiza o estado vazio e o bloqueado (render de server component com o cart mockado, como nos testes de listagem).
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar `pnpm --filter storefront test typecheck lint build`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(storefront): página do carrinho com avisos e cupom`.

### Task 17: admin, cupons

**Files:**
- Create: `apps/admin/app/(painel)/cupons/{page.tsx,novo/page.tsx,[id]/page.tsx,actions.ts}`, `apps/admin/components/coupon-form.tsx`, `apps/admin/lib/coupons.ts`
- Modify: `apps/admin/lib/nav.ts` (Cupons ativo com `href: "/cupons"`), `apps/admin/lib/problem-messages.ts`, `apps/admin/lib/api.ts`
- Test: `apps/admin/test/coupons.test.ts`, `test/coupon-actions.test.ts`

**Interfaces:**
- Consumes: o contrato do promotions admin (Tarefa 8), `staffAction` e `authed` com o classificador R25.
- Produces:
  - `parseCouponForm(formData) -> {ok: true, body} | {ok: false, fieldErrors}`. Regras:
    - o código é normalizado como na Tarefa 7;
    - o valor percentual vai de 1 a 90 e o fixo é informado em reais e convertido para centavos;
    - as datas são `datetime-local` em America/Sao_Paulo, convertidas para UTC;
    - fim depois do início;
    - categorias e coleções vêm de checkboxes com os slugs carregados do catalog admin.
  - Mensagens:
    - `promotions.coupon.code_taken` → "Já existe um cupom com este código.";
    - `promotions.coupon.version_conflict` → "Este cupom foi alterado por outra pessoa. Recarregue para ver a versão atual.";
    - `promotions.coupon.has_redemptions` → "Este cupom já foi usado e não pode ser excluído. Desative em vez disso.".
  - As páginas lista, novo e editar seguem a spec §9. Toda página chama `requireStaff` e toda ação usa `staffAction`.

- [ ] **Step 1: Testes:**
  - `parseCouponForm`, um caso por campo (incluindo a conversão de reais e de timezone);
  - a ação de criar mostra `code_taken` no campo;
  - a ação sem sessão de staff não chama a API.
- [ ] **Step 2:** Rodar `pnpm --filter admin test`. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar `pnpm --filter admin test typecheck lint build`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(admin): gestão de cupons`.

### Task 18: seed de cupom demo e e2e da fatia 2

**Files:**
- Modify: `scripts/seed/data.py`, `scripts/seed/__main__.py` (upsert de cupom por código via admin do promotions), `scripts/seed/tests/test_manifest.py`
- Create: `e2e/tests/{cart-coupon.spec.ts,cart-price-event.spec.ts,cart-merge.spec.ts,coupon-collection.spec.ts}`
- Modify: `.github/workflows/ci-e2e.yml` (paths: `services/cart/**` e `services/promotions/**`)

**Interfaces:**
- Produces:
  - Cupom demo `BEMVINDO10`, com 10%, pedido mínimo de R$ 150,00 (15000) e sem validade. A descrição diz "Cupom da loja demonstrativa". Upsert idempotente pelo código: o seed só cria e nunca altera o que o admin mudou.
  - Specs (a e2e mantém ritmo humano por causa do R24, com `workers: 1`):
    1. `cart-coupon`: visitante adiciona dois produtos do seed (total acima de R$ 150) → aplica `bemvindo10` em minúsculas → o desconto aparece e o total bate com subtotal menos 10%;
    2. `cart-price-event`: visitante adiciona um item → o admin, numa segunda página logada, muda o preço da variante na aba Variantes → a loja recarrega `/carrinho` até mostrar "O preço mudou de" em até 15 s (critério de 5 s mais folga de CI), com `expect.poll`;
    3. `cart-merge`: cliente criado no spec adiciona 1 unidade e sai → como visitante, adiciona 1 unidade do mesmo SKU → entra → `/carrinho` mostra quantidade 2;
    4. `coupon-collection`: o admin cria um cupom restrito à coleção "Básicos pesados" → um item da coleção recebe desconto e um item de fora recebe "Nenhum item do carrinho vale para este cupom.".
  - O script de arquivamento R26 ganha a limpeza dos cupons `E2E-*`, que são desativados.

- [ ] **Step 1:** Escrever os testes do seed (cupom presente, código válido, sem travessão) e os 4 specs.
- [ ] **Step 2:** Rodar `pnpm test:e2e` com a stack sem as mudanças do seed. Esperado: FAIL.
- [ ] **Step 3:** Implementar o seed e ajustar os seletores a partir dos componentes reais das Tarefas 15 a 17.
- [ ] **Step 4:** Rodar `pnpm dev:up && pnpm seed`, o script de arquivamento e `pnpm test:e2e`. Esperado: os 4 specs novos e os 4 antigos passam; o Lighthouse continua dentro das metas.
- [ ] **Step 5:** Commit `test(e2e): carrinho, evento de preço, merge e cupom por coleção`.

### Task 19: documentação, ADRs e CI final

**Files:**
- Create: `docs/adr/0008-outbox-e-mensageria.md`, `docs/adr/0009-token-de-servico.md`
- Modify: `README.md` (status "fatia 2 de 5", novos serviços e URLs (UI do RabbitMQ), cupom demo, limitações novas), `docs/architecture.md` (eventos, topologia, carrinho e cupons), `docs/img/` (captura do carrinho com cupom)

**Interfaces:**
- Produces:
  - ADR 0008: por que outbox, e não publicação direta; garantia at-least-once e idempotência; retry com DLQ; o relay roda no processo do serviço.
  - ADR 0009: token de serviço por client credentials, comparado com a alternativa de confiar na rede; rotas internas bloqueadas no gateway.
  - Seguem as regras de documentação da fatia 1: sem travessões, sem números inventados e com links conferidos.

- [ ] **Step 1:** Escrever os documentos.
- [ ] **Step 2:** Verificar `grep -rn "—\|–" README.md docs/adr docs/architecture.md` (vazio) e os links relativos.
- [ ] **Step 3:** Fazer push e acompanhar a CI no GitHub. Os 7 workflows (platform, identity, catalog, cart, promotions, web e e2e) precisam ficar verdes. Workflow que não for disparado por path roda com `gh workflow run`.
- [ ] **Step 4:** Conferir os critérios de aceite 1 a 9 da spec §1, um por um, com evidência (comando e saída) no corpo do commit.
- [ ] **Step 5:** Commit `docs: README, arquitetura e ADRs da fatia 2`.
