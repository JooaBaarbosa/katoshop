# KatoShop: design geral e fatia 1

- **Data:** 2026-10-23
- **Status:** aguardando revisão
- **Escopo deste documento:** a arquitetura e as convenções que valem para todas as fatias, a identidade visual e o detalhamento completo da fatia 1. As fatias 2 a 5 recebem specs próprias.

## 1. Visão

KatoShop é um template genérico de e-commerce em microsserviços. Ele é apresentado com uma loja demo de streetwear.

O objetivo principal é servir de **portfólio de arquitetura**. A ideia é mostrar a recrutadores e revisores técnicos:
- microsserviços com banco por serviço;
- mensageria com outbox;
- uma saga de checkout com compensação;
- observabilidade ponta a ponta;
- testes em várias camadas.

O código também deve ser bom o bastante para virar produto no futuro.

**Critérios de sucesso:**
1. Um recrutador entende o projeto em 5 minutos pelo README, pelos GIFs e pelo vídeo.
2. Um revisor técnico encontra decisões documentadas em ADRs, fronteiras claras entre os serviços e testes que provam o comportamento.
3. `docker compose up` sobe tudo localmente, com dados demo, sem nenhuma conta externa. O modo sandbox real é opcional.

**Não objetivos:**
- multi-loja (multi-tenant);
- internacionalização;
- deploy em cloud;
- app mobile;
- nota fiscal;
- marketplace com vários vendedores;
- recursos de IA.

## 2. Decisões tomadas no brainstorming

| Tema | Decisão |
|---|---|
| Objetivo | Portfólio de arquitetura |
| Arquitetura | 7 microsserviços completos, banco por serviço, Docker Compose |
| Comunicação | Gateway + REST síncrono para leituras, eventos no RabbitMQ para mudanças de estado, saga orquestrada pelo serviço de Pedidos (abordagem A) |
| Integrações | Ports & adapters. Provider fake determinístico e provider sandbox real: Mercado Pago (Pix + cartão) e Melhor Envio |
| Mercado | Brasil: BRL, pt-BR, CEP, CPF |
| Nicho demo | Moda/streetwear |
| Frontend | Duas apps Next.js (loja e admin) em monorepo pnpm/Turborepo, design system compartilhado |
| Execução | Somente local (Docker Compose). Apresentação por README, GIFs e vídeo |
| Admin | CRUD dos 7 domínios, dashboard de KPIs, RBAC, auditoria, saúde do sistema, gestão da vitrine |
| Entrega | Incremental por fatias verticais, cada uma apresentável |
| Marca | KatoShop, direção visual SARJETA, logo monocromático com traço limão, admin claro com barra lateral escura |

## 3. Arquitetura geral

```
                    navegador
                        |
        +---------------+----------------+
        |                                |
  apps/storefront (Next.js)        apps/admin (Next.js)
  katoshop.localhost               admin.katoshop.localhost
        |   (BFF: chamadas no servidor, token em cookie httpOnly)
        +---------------+----------------+
                        |
               Traefik (api.katoshop.localhost)
                        |
   +--------+--------+--+------+---------+----------+------------+
   |        |        |         |         |          |            |
identity catalog   cart     orders   payments   shipping    promotions
   |        |        |         |         |          |            |
   +--------+--- Postgres (um banco por serviço) ---+------------+
                     Redis (carrinho)   RabbitMQ (eventos, fatia 2+)
                        |
       OpenTelemetry Collector -> Jaeger / Prometheus -> Grafana
```

### 3.1 Responsabilidade de cada serviço

| Serviço | Responsável por | Fatia |
|---|---|---|
| identity | Clientes, funcionários, login, tokens, papéis/permissões, endereços | 1 (RBAC completo na 4) |
| catalog | Produtos, variantes (SKU), categorias, coleções, imagens, **estoque por SKU**, busca, configuração da vitrine | 1 (edição da vitrine na 4) |
| cart | Carrinho de visitante e de cliente logado, merge no login, revalidação de preço/estoque | 2 |
| promotions | Cupons, regras de desconto, limites de uso | 2 |
| orders | Pedido, máquina de estados, **orquestração da saga de checkout** | 3 |
| payments | Cobrança Pix/cartão, webhooks, estornos | 3 |
| shipping | Cotação por CEP, etiqueta, rastreio | 3 |

O estoque fica no catalog para não criar um 8º serviço. As operações de reserva (`reserve`, `release`, `commit`) chegam na fatia 3 como comandos da saga. Na fatia 1 o modelo já separa `stock_on_hand` e `stock_reserved`.

### 3.2 Regras de comunicação

- **Leitura entre serviços:** REST síncrono, com timeout curto (2s), retry só em operação idempotente e circuit breaker simples na lib `platform`.
- **Mudança de estado que outros precisam saber:** evento publicado via transactional outbox. A linha do evento entra na mesma transação da mudança e um relay publica no RabbitMQ.
- **Consumidores:** sempre idempotentes, com tabela `processed_events(event_id)`, fila de falhas (DLQ) e reprocessamento pelo admin (fatia 4).
- **Checkout (fatia 3):** saga orquestrada pelo orders. Passos: reservar estoque → aplicar cupom → cotar e fixar frete → cobrar → confirmar pedido. Cada passo tem uma compensação: liberar estoque, devolver uso do cupom, estornar. O estado da saga é persistido no banco do orders.
- **Nenhum serviço acessa o banco de outro.** Cada serviço tem um usuário Postgres com permissão só no próprio banco.

### 3.3 Eventos previstos

Nome no formato `<serviço>.<entidade>.<fato>.v<versão>`. Lista inicial, detalhada nas specs das fatias:
- `catalog.variant.price_changed.v1`, `catalog.variant.stock_changed.v1`, `catalog.product.archived.v1` (fatia 2, consumidos pelo cart);
- `orders.order.placed.v1`, `orders.order.confirmed.v1`, `orders.order.cancelled.v1` (fatia 3);
- `payments.payment.approved.v1`, `payments.payment.failed.v1`, `payments.refund.completed.v1` (fatia 3);
- `shipping.shipment.created.v1`, `shipping.shipment.status_changed.v1` (fatia 3);
- `promotions.coupon.redeemed.v1` (fatia 3).

Envelope padrão: `id` (UUIDv7), `type`, `version`, `occurred_at`, `correlation_id`, `causation_id`, `producer`, `data`.

## 4. Convenções

### 4.1 Estrutura do monorepo

```
katoshop/
  services/<svc>/            identity, catalog, cart, orders, payments, shipping, promotions
    pyproject.toml
    src/<svc>/api/           rotas FastAPI, schemas Pydantic, dependências
    src/<svc>/domain/        entidades e regras puras, sem I/O
    src/<svc>/application/   casos de uso (orquestram domínio + portas)
    src/<svc>/adapters/      repositórios SQLAlchemy, storage, providers, broker
    migrations/              Alembic
    tests/unit|integration|api
    Dockerfile
  libs/py/platform/          lib compartilhada (ver 4.3)
  apps/storefront/           Next.js, loja
  apps/admin/                Next.js, painel
  packages/ui/               design system: tokens, componentes, ícones, logo, favicon
  packages/api-client/       cliente TS gerado do OpenAPI de cada serviço
  packages/config/           tsconfig, eslint e prettier compartilhados
  infra/                     compose, traefik, postgres-init, otel, prometheus, grafana
  docs/adr/                  decisões de arquitetura (ADR)
  docs/superpowers/          specs e planos
  scripts/                   seed, geração de chaves, geração do cliente TS
```

### 4.2 Backend (Python)

- Python 3.14 (`requires-python = ">=3.14,<3.15"`). Workspace uv com um pacote por serviço e a lib `platform`.
- FastAPI, Pydantic v2, SQLAlchemy 2 async com asyncpg, Alembic.
- Camadas: `api` → `application` → `domain`, com `adapters` implementando portas definidas em `application`. O domínio não importa FastAPI nem SQLAlchemy.
- **API:**
  - versionada em `/v1`;
  - JSON em snake_case;
  - erros em `application/problem+json` (RFC 9457), com um campo `code` estável;
  - paginação por cursor (keyset) com `limit` máximo de 100;
  - header `Idempotency-Key` aceito em todo POST que cria recurso.
- **Dinheiro:** inteiro em centavos, campo com sufixo `_cents`, moeda fixa BRL.
- **IDs:** UUIDv7. Slugs para URLs públicas.
- **Datas:** UTC, `timestamptz`.
- **Concorrência:** coluna `version` para lock otimista em agregados editáveis (produto, variante).
- **Saúde:** `GET /health/live` e `GET /health/ready`. O ready checa o banco.
- **Configuração:** pydantic-settings, variáveis com prefixo do serviço e `.env.example` versionado.
- **Logs:** JSON (structlog) com `trace_id`, `span_id`, `correlation_id`. Nunca logar senha, token ou CPF completo.
- **Qualidade:** ruff (lint + format), pyright em modo strict no `domain` e `application`.

### 4.3 Lib `platform`

Tem um pacote só e entra cedo, crescendo por fatia:
- **fatia 1:** setup de OpenTelemetry (traces, métricas, logs), verificação de JWT com cache das chaves públicas do identity, dependências FastAPI `current_principal` / `require_permission`, handlers de problem+json, cliente HTTP com timeout e propagação de contexto, settings base;
- **fatia 2:** envelope de evento, outbox (tabela + relay), consumidor idempotente, DLQ.

### 4.4 Frontend (TypeScript)

- Next.js com App Router, React, TypeScript strict, Tailwind CSS e shadcn/ui, todos dentro de `packages/ui`.
- **BFF:** o navegador só fala com o Next. O Next guarda os tokens em cookies httpOnly no próprio domínio e chama o gateway no servidor (Server Components e Server Actions) com `Authorization: Bearer`.
- **Cliente da API:** `openapi-typescript` + `openapi-fetch` gerados do OpenAPI de cada serviço. O OpenAPI fica versionado em `packages/api-client/openapi/`. A CI regenera e falha se houver diferença.
- **Validação de formulários:** zod. Ícones: lucide-react.
- **Acessibilidade:** contraste AA, foco visível, navegação por teclado e `prefers-reduced-motion` respeitado.

### 4.5 Segurança (vale para tudo)

- Senhas com Argon2id.
- Access token JWT EdDSA (Ed25519), 15 minutos, com `kid` e chaves públicas expostas em `/.well-known/jwks.json` pelo identity.
- Refresh token opaco de 256 bits, guardado como hash, rotativo e com detecção de reuso por família. Reuso revoga a família inteira.
- Audiências separadas: `storefront` e `admin`. Um token de cliente nunca abre o admin.
- Rate limit no Traefik para as rotas de auth. Bloqueio de conta por 15 minutos após 5 falhas seguidas.
- Uploads validados por conteúdo real (magic bytes), não pela extensão.
- CSRF: cookies `SameSite=Lax` + Server Actions do Next, que checam a origem.

### 4.6 Observabilidade

- OpenTelemetry nos 7 serviços e nos 2 Next.js, com propagação W3C `traceparent` ponta a ponta.
- O Collector envia traces para o Jaeger e métricas para o Prometheus.
- O Grafana sobe provisionado com um dashboard RED por serviço (taxa, erros, duração) e com o painel de saúde do Postgres.

### 4.7 Testes

- **Unitário:** TDD no `domain` e no `application`. Meta de cobertura de 90% nessas camadas.
- **Integração:** repositórios e adapters contra Postgres real com testcontainers.
- **API:** httpx contra a app FastAPI com banco real.
- **Contrato:** o OpenAPI gerado é comparado com o versionado, e o typecheck do frontend roda contra o cliente gerado. Uma quebra de contrato quebra a CI.
- **E2E:** Playwright contra o compose completo.
- **CI no GitHub Actions:**
  - jobs Python por serviço, disparados por filtro de caminho;
  - job do frontend (lint, typecheck, build);
  - job e2e que sobe o compose.

### 4.8 Documentação

- README com o que é, GIFs, arquitetura, como rodar e mapa de decisões.
- ADRs curtos em `docs/adr/`. ADRs da fatia 1:
  - 0001 microsserviços com banco por serviço;
  - 0002 orquestração da saga em vez de coreografia;
  - 0003 RabbitMQ;
  - 0004 estoque dentro do catalog;
  - 0005 BFF com cookies httpOnly;
  - 0006 cada serviço valida o JWT.
- Sem travessões na documentação pública (regra do `CLAUDE.md`).

## 5. Versões fixadas

Versões estáveis conferidas em 2026-10-23 nos registries oficiais (PyPI, npm, Docker Hub, nodejs.org, GitHub Releases). Elas ficam fixadas nos lockfiles e nas tags de imagem. Na hora da implementação, cada versão é conferida de novo e atualizada se houver estável mais nova.

| Tecnologia | Versão |
|---|---|
| Python | 3.14.9 |
| uv | 0.13.5 |
| FastAPI | 0.161.1 |
| Uvicorn | 0.54.0 |
| Pydantic | 2.14.1 |
| pydantic-settings | 2.16.1 |
| SQLAlchemy | 2.1.6 |
| asyncpg | 0.32.0 |
| Alembic | 1.20.1 |
| argon2-cffi | 25.1.0 |
| PyJWT | 2.15.1 |
| httpx | 0.28.1 |
| structlog | 26.1.0 |
| opentelemetry-sdk | 1.45.1 (instrumentações 0.66b1, única linha publicada pelo projeto) |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 |
| testcontainers | 4.15.0 |
| hypothesis | 6.170.8 |
| ruff / pyright | 0.17.2 / 1.1.414 |
| Node.js | 24.22.1 (LTS ativo) |
| pnpm / Turborepo | 12.15.0 / 2.11.10 |
| TypeScript | 7.0.2 |
| Next.js / React | 16.4.3 / 19.3.1 |
| Tailwind CSS | 4.3.3 |
| shadcn (CLI) | 4.22.1 |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 |
| zod | 4.6.7 |
| lucide-react | 1.61.0 |
| @tanstack/react-table | 9.3.1 |
| Recharts | 3.10.1 (fatia 4) |
| Playwright | 1.64.1 |
| Postgres (imagem) | 18.6-alpine |
| Traefik | 3.7.16 |
| OpenTelemetry Collector contrib | 0.163.2 |
| Jaeger | 2.22.0 |
| Prometheus | v3.15.1 |
| Grafana | 13.2.4 |
| RabbitMQ | 4.4.0-management-alpine (fatia 2) |
| Redis | 8.10.2-alpine (fatia 2) |
| actions/checkout, setup-node, setup-uv, pnpm/action-setup | v7.0.1, v7.1.0, v10.3.2, v6.1.0 |

Observações:
- O Node 26 é a linha "Current", ainda não LTS. Por isso usamos a LTS ativa.
- O Python 3.15.1 já está estável, mas o `CLAUDE.md` fixa a linha 3.14. Ver a seção 10.

## 6. Identidade visual

**Marca:** KatoShop. Loja demo de streetwear.

**Logo:** a palavra KATOSHOP em Anton, uma cor só (branco quente no fundo escuro, preto no fundo claro), com um traço curto verde-limão sob o K. **Favicon:** o K com o traço, em SVG e PNG 32/180/192/512, mais `manifest.webmanifest`.

| Token | Valor | Uso |
|---|---|---|
| `--bg` (loja) | `#0E0E0E` | fundo da loja |
| `--surface` (loja) | `#1E1E1E` | cards, placeholders de imagem |
| `--border` (loja) | `#2A2A2A` | divisórias |
| `--fg` | `#F4F4F0` | texto principal na loja |
| `--muted` | `#A9A9A4` | texto secundário |
| `--accent` | `#D7FF3A` | só ações primárias e preços |
| `--accent-on-light` | `#9DBF00` | acento sobre fundo claro (sempre com texto escuro, nunca para texto pequeno) |
| `--admin-bg` | `#F7F7F4` | fundo do admin |
| `--admin-sidebar` | `#0E0E0E` | barra lateral do admin |

**Tipografia:**
- Anton nos títulos, sempre em caixa alta;
- Inter no texto e na interface;
- JetBrains Mono nos preços, SKUs e números de pedido.

As fontes ficam auto-hospedadas via `next/font`.

**Formas e movimento:**
- raio de 2px em botões e cards, nunca pílula;
- bordas de 1px;
- transições de até 150ms, só em hover, foco e abertura de painel;
- sem animação de entrada em scroll e sem cursor customizado.

**Regras do `CLAUDE.md` aplicadas à KatoShop:**
- **Sem avaliações de produto.** A fatia 1 não tem reviews. Se entrarem no futuro, serão só de compras reais.
- **Sem números de prova social.** Nada de "mais de X clientes" nem contadores de pessoas vendo.
- **Estoque só o real:** tamanho esgotado aparece riscado, nada além disso.
- **Hero direto:** diz o que é, para quem e o que se compra. Texto da demo: "Streetwear para andar, não para guardar" + "Camisetas, moletons e calças em tecido pesado, do P ao XGG".
- **Políticas de frete e troca** aparecem como configuração da loja demo, editável.
- **Fotos de produto reais**, de banco com licença livre (Unsplash/Pexels). Cada imagem guarda autor, URL de origem e licença. A página `/creditos` lista todas. Nada de imagem gerada por IA.
- **Páginas legais:** `/privacidade` (texto baseado na LGPD, marcado como modelo) e `/termos`, linkadas no rodapé.
- **Dados de seed** marcados como demo: rodapé da loja com "Loja demonstrativa, nenhuma compra é real" e selo "dados demo" no admin.
- **Domínio próprio:** fora de escopo enquanto for só local. Em dev, `katoshop.localhost`.

## 7. Roadmap de fatias

| Fatia | Conteúdo | Apresentável como |
|---|---|---|
| 1 | Fundação, identity, catalog, loja navegável, admin de catálogo, observabilidade | "Loja navegável com microsserviços e tracing" |
| 2 | RabbitMQ + outbox, cart (Redis), promotions (motor de regras de cupom), carrinho na loja, cupons no admin | "Carrinho reativo a eventos e motor de cupons" |
| 3 | orders + saga, payments (fake + Mercado Pago sandbox), shipping (fake + Melhor Envio sandbox), checkout completo, webhooks | "Checkout com saga, compensação e pagamentos reais em sandbox" |
| 4 | Admin completo: KPIs, RBAC, auditoria, saúde do sistema (filas, DLQ, reprocesso), edição da vitrine, gestão de pedidos | "Painel de operação completo" |
| 5 | Dashboards Grafana finais, teste de carga (k6), README, GIFs, vídeo | "Pronto para LinkedIn" |

## 8. Fatia 1 em detalhe

### 8.1 Objetivo e critérios de aceite

Um visitante navega pela loja, filtra, busca e abre produtos. Também cria conta, entra e sai. Um funcionário entra no admin, cadastra um produto com variantes e fotos, e o produto aparece na loja. Tudo isso fica visível como trace único no Jaeger.

Critérios de aceite:
1. `docker compose up` em máquina limpa sobe tudo e roda o seed em menos de 5 minutos (sem contar download de imagens Docker).
2. `katoshop.localhost` mostra a home com hero, coleções em destaque e produtos com fotos reais creditadas.
3. Os filtros de tamanho, cor, faixa de preço e categoria funcionam juntos, com contadores corretos. A busca "moletom preto" encontra os moletons pretos.
4. A página de produto troca as fotos ao trocar a cor e mostra esgotado por tamanho conforme o estoque real.
5. Cadastro, login, logout e refresh funcionam. Um token de cliente recebe 403 em qualquer rota do admin.
6. No admin: criar produto → gerar a grade de variantes (cores × tamanhos) → ajustar estoque com motivo → enviar fotos → publicar. O produto aparece na loja em até 60s.
7. Uma requisição da loja aparece no Jaeger como um trace com spans do Next, do Traefik, do catalog e do Postgres.
8. A CI fica verde: lint, typecheck, testes unitários, de integração, de API e de contrato, e o e2e.
9. Lighthouse na home e na página de produto (desktop): Acessibilidade ≥ 95 e Performance ≥ 90.

### 8.2 Serviço identity

**Modelo de dados:**
- `users`:
  - `id`, `email` (único, minúsculo), `password_hash`, `name`, `kind` (`customer` | `staff`), `status` (`active` | `disabled`);
  - `failed_logins`, `locked_until`, `created_at`, `updated_at`.
- `roles` (`id`, `key`, `name`) e `user_roles`. Na fatia 1 existe só `admin` (todas as permissões de staff).
- `refresh_tokens` (`id`, `user_id`, `family_id`, `token_hash`, `audience`, `expires_at`, `revoked_at`, `replaced_by`, `created_at`).
- `signing_keys` (`kid`, `public_jwk`, `private_key_ref`, `active`, `created_at`). Em dev, a chave privada vem de arquivo gerado por `scripts/gen-keys`.

**Endpoints:**

| Método e rota | Descrição |
|---|---|
| `POST /v1/auth/register` | cria cliente, devolve tokens (audiência `storefront`) |
| `POST /v1/auth/login` | login de cliente |
| `POST /v1/auth/staff/login` | login de funcionário (audiência `admin`) |
| `POST /v1/auth/refresh` | troca o refresh token. Um token reusado revoga a família |
| `POST /v1/auth/logout` | revoga a família atual |
| `GET /v1/me` / `PATCH /v1/me` | perfil (nome; email e senha com senha atual) |
| `GET /.well-known/jwks.json` | chaves públicas |

**Regras:**
- Senha com mínimo de 10 caracteres, checada contra uma lista local de senhas comuns.
- Mensagem de erro de login genérica, sem revelar se o email existe.
- Tempos: access de 15 min; refresh de 30 dias (cliente) ou 12 h (funcionário).
- O seed cria o funcionário `admin@katoshop.localhost`, com a senha impressa no log do seed e documentada no README como credencial de demo.

### 8.3 Serviço catalog

**Modelo de dados:**
- `categories` (`id`, `slug`, `name`, `parent_id`, `position`).
- `sizes` (`code`, `label`, `position`): PP, P, M, G, GG, XG, XGG, ordenáveis.
- `colors` (`code`, `name`, `hex`).
- `products`:
  - `id`, `slug`, `name`, `description`, `category_id`;
  - `status` (`draft` | `active` | `archived`), `base_price_cents`;
  - `attributes` (jsonb: material, gramatura, modelagem, cuidados);
  - `search_vector` (tsvector gerado, dicionário `portuguese` + `unaccent`);
  - `version`, `published_at`, timestamps.
- `variants`:
  - `id`, `product_id`, `sku` (único), `color_code`, `size_code`;
  - `price_cents` (nulo usa o preço base);
  - `stock_on_hand`, `stock_reserved` (sempre 0 na fatia 1), `version`, `active`;
  - restrição única em (`product_id`, `color_code`, `size_code`).
- `stock_movements`: livro razão imutável (`id`, `variant_id`, `delta`, `reason` (`initial` | `adjustment` | `damage` | `return`, mais `reservation` / `release` / `sale` na fatia 3), `note`, `actor_id`, `created_at`). O saldo de `stock_on_hand` só muda junto com um movimento, na mesma transação.
- `product_images`:
  - `id`, `product_id`, `color_code` (nulo = todas as cores);
  - `storage_key`, `width`, `height`, `alt` (obrigatório), `position`;
  - `credit_author`, `credit_source_url`, `license`.
- `collections` (`id`, `slug`, `name`, `description`, `featured`, `position`) e `collection_products` (`collection_id`, `product_id`, `position`).
- `storefront_settings`: linha única com jsonb validado por schema. Guarda o hero (título, subtítulo, rótulo e destino do CTA, imagem), as coleções em destaque e as políticas de frete e troca exibidas. Somente leitura pela API na fatia 1; o seed preenche.

**Endpoints públicos** (sem auth, com cache HTTP curto):

| Método e rota | Descrição |
|---|---|
| `GET /v1/products` | lista paginada só com produtos `active`. Filtros: `category`, `collection`, `size` (vários), `color` (vários), `price_min`, `price_max`, `q`, `sort` (`relevance`, `newest`, `price_asc`, `price_desc`), `cursor`, `limit` |
| `GET /v1/products/facets` | contagem por tamanho, cor e categoria para os mesmos filtros |
| `GET /v1/products/{slug}` | detalhe com variantes, disponibilidade por variante (`available = stock_on_hand - stock_reserved > 0`) e imagens por cor |
| `GET /v1/categories`, `GET /v1/collections`, `GET /v1/collections/{slug}` | navegação |
| `GET /v1/storefront/settings` | conteúdo da home |
| `GET /v1/media/{storage_key}` | serve a imagem com `Cache-Control: public, max-age=31536000, immutable` (a chave contém o hash do conteúdo) |

**Endpoints do admin** (`/v1/admin/...`, exigem audiência `admin` e a permissão adequada):
- CRUD de categorias, coleções (incluindo a ordem dos produtos) e produtos (`PATCH` exige `version`; se divergir, retorna 409);
- `POST /v1/admin/products/{id}/variants/generate` com `{colors[], sizes[]}`: cria as combinações que faltam, gera SKUs e não toca nas existentes;
- `PATCH /v1/admin/variants/{id}` (preço, ativo);
- `POST /v1/admin/variants/{id}/stock-adjustments` com `{delta, reason, note}`, gerando um movimento no livro razão. O saldo não pode ficar negativo; se ficasse, retorna 422;
- `GET /v1/admin/variants/{id}/stock-movements`;
- `POST /v1/admin/products/{id}/images` (multipart: JPEG, PNG ou WebP até 8 MB, checado por magic bytes; guarda dimensões), `PATCH` (alt, cor, posição, créditos) e `DELETE`;
- `POST /v1/admin/products/{id}/publish` e `/archive`. Publicar exige pelo menos uma variante ativa, uma imagem e preço > 0. Se faltar algo, retorna 422 com a lista do que falta.

**Armazenamento de imagens:** a porta `ImageStorage` tem um adapter de disco local (volume Docker). Um adapter S3 fica para quando houver deploy. O MinIO não é usado: o projeto deixou de publicar imagens Docker da edição comunitária.

**Busca:** `search_vector` com pesos (nome A, categoria B, descrição C) e `websearch_to_tsquery('portuguese', unaccent(q))`. Os filtros de variante usam `EXISTS` sobre `variants`. A paginação é keyset pela chave de ordenação + `id`.

### 8.4 Gateway e infraestrutura da fatia 1

- **Traefik:**
  - roteia `api.katoshop.localhost/identity/*` e `/catalog/*`, além dos hosts das duas apps;
  - aplica rate limit nas rotas `/identity/v1/auth/*`;
  - repassa `traceparent`;
  - tem o dashboard habilitado só em dev.
- **Postgres:**
  - uma instância com os bancos `identity` e `catalog`;
  - um usuário por serviço, criado no script `infra/postgres-init`;
  - extensão `unaccent` no catalog.
- **Migrações:** cada serviço roda `alembic upgrade head` no start, antes do Uvicorn.
- **Seed:** `scripts/seed` é idempotente. Ele cria o admin, 4 categorias (Camisetas, Moletons, Calças, Acessórios), 7 cores, cerca de 24 produtos com variantes e estoque variado (incluindo alguns tamanhos esgotados), 3 coleções e as configurações da vitrine.
- **Fotos do seed:**
  - escolhidas a dedo no Unsplash/Pexels e listadas em `scripts/seed/images.json` com autor, URL, licença e hash SHA-256;
  - baixadas uma vez e conferidas pelo hash;
  - os nomes e descrições dos produtos são escritos para combinar com as fotos.
- **Observabilidade:** o Collector, o Jaeger, o Prometheus e o Grafana sobem no compose.
- **Comandos (cross-platform):**
  - `pnpm dev:up`, `pnpm dev:down`, `pnpm seed`, `pnpm gen:api` e `pnpm test:e2e` na raiz;
  - o equivalente com `docker compose` documentado no README.

### 8.5 Loja (apps/storefront)

| Rota | Conteúdo |
|---|---|
| `/` | hero com CTA principal "Ver o drop atual" e secundário "Todas as peças", coleções em destaque, grade de novidades, faixa com políticas (frete, troca, Pix), rodapé |
| `/c/[categoria]` | listagem com filtros laterais (tamanho, cor, preço) em desktop e painel no mobile, ordenação, contadores, "carregar mais" por cursor |
| `/colecoes/[slug]` | listagem da coleção |
| `/busca?q=` | resultado da busca com os mesmos filtros |
| `/p/[slug]` | galeria por cor, preço em mono limão, parcelamento e preço no Pix como texto da política demo, seletor de cor e tamanho com esgotado riscado, guia de medidas (modal), detalhes do produto. O botão "Adicionar ao carrinho" fica desabilitado com a nota "Carrinho chega na próxima versão" e é ativado na fatia 2. O cálculo de frete entra na fatia 3 |
| `/entrar`, `/criar-conta`, `/conta` | autenticação e perfil |
| `/privacidade`, `/termos`, `/creditos` | páginas legais e créditos das fotos |
| `not-found`, `error` | páginas próprias na identidade da marca |

Detalhes:
- **Renderização:** Server Components. Catálogo e home com revalidação de 60s. A conta é dinâmica.
- **SEO:** metadata por página, Open Graph com foto do produto, JSON-LD `Product` (sem `aggregateRating`, já que não há avaliações), `sitemap.xml` e `robots.txt`.
- **Imagens:** `next/image` com `sizes` corretos. A primeira imagem da página de produto é a única com prioridade.

### 8.6 Admin (apps/admin)

| Rota | Conteúdo |
|---|---|
| `/entrar` | login de funcionário |
| `/` | visão geral provisória: contagem de produtos por status, variantes sem estoque e últimos movimentos de estoque (dados reais do catalog). KPIs de venda entram na fatia 4 |
| `/produtos` | tabela com busca, filtro por status e categoria, paginação |
| `/produtos/novo`, `/produtos/[id]` | abas Dados, Variantes (grade cor × tamanho com preço e estoque, gerador), Fotos (upload, alt, cor, créditos, ordenação por arrastar com alternativa por teclado), Publicação (checklist do que falta) |
| `/produtos/[id]/variantes/[vid]/estoque` | livro razão de estoque + formulário de ajuste com motivo |
| `/categorias`, `/colecoes` | CRUD e ordenação |

Visual:
- conteúdo claro, barra lateral escura com o logo, selo "dados demo";
- itens futuros da barra lateral (Pedidos, Cupons, Frete, Clientes, Vitrine, Saúde, Auditoria) aparecem desabilitados com a indicação da fatia.

### 8.7 Tratamento de erros

- Os serviços sempre respondem `problem+json` com `code` estável (por exemplo, `catalog.product.version_conflict`, `identity.auth.invalid_credentials`).
- O Next mapeia os `code` para mensagens em pt-BR:
  - **409 de versão:** o admin mostra "Este produto foi alterado por outra pessoa" com a opção de recarregar;
  - **422:** erros por campo no formulário;
  - **401:** tenta o refresh uma vez e, se falhar, manda para o login;
  - **5xx ou timeout:** página de erro da marca com o `trace_id` para suporte.

### 8.8 Plano de testes da fatia 1

- **identity:**
  - unitários: política de senha, emissão e validação de tokens, rotação e detecção de reuso, bloqueio de conta;
  - API: fluxos de cadastro, login, refresh, logout e audiência errada.
- **catalog:**
  - unitários: geração de grade e SKU, regras de publicação, livro razão de estoque (nunca negativo), cálculo de disponibilidade;
  - integração: busca em português com acento, filtros combinados e contagem de facetas, paginação keyset estável, conflito de versão;
  - API: upload com arquivo inválido por magic bytes, rotas admin sem permissão.
- **platform:** verificação de JWT com chave rotacionada (`kid` desconhecido força recarregar as chaves) e problem+json.
- **Contrato:** OpenAPI de identity e catalog versionados; a CI regenera e compara; typecheck das duas apps.
- **E2E (Playwright):**
  1. login no admin → criar produto → gerar variantes → estoque → foto → publicar → aparece na loja;
  2. visitante filtra por tamanho e cor e abre o produto, que mostra o esgotado correto;
  3. cadastro, login e logout na loja;
  4. token de cliente barrado no admin.

## 9. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Escopo grande (7 serviços + 2 apps) | Fatias verticais com spec e plano próprios. Cada fatia termina apresentável |
| Compose pesado para máquina local | Perfis do compose (`core`, `observability`). Limites de memória por container. Meta de RAM total abaixo de 6 GB na fatia 1 |
| Fotos reais combinando com o catálogo | Selecionar as fotos antes de escrever os produtos do seed. Manifesto com créditos e hash |
| Versões muito novas com pouca documentação (Next 16.4, TS 7, Tailwind 4.3) | Conferir as notas de versão no início do plano. Se uma versão estável quebrar a integração, registrar em ADR e usar a última estável que funciona |
| Sandboxes externas instáveis (fatia 3) | O provider fake é o padrão e o sandbox real é opt-in por variável de ambiente |

## 10. Pontos pendentes de confirmação

1. **Linha do Python:** o `CLAUDE.md` fixa 3.14 (referência 3.14.8), mas a regra "versão estável mais atual" aponta para 3.14.9 dentro da linha, e o 3.15.1 já está estável. Esta spec usa 3.14.9. Atualizar a referência do `CLAUDE.md` para 3.14.9, ou migrar para a linha 3.15, depende da decisão do usuário.
2. **Licença do repositório:** proposta MIT, por ser template de portfólio.
