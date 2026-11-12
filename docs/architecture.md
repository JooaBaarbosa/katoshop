# Arquitetura do KatoShop

Este documento resume a arquitetura geral. O detalhamento completo está na spec
([design geral e fatia 1](superpowers/specs/2026-10-23-katoshop-design.md)) e as decisões em [docs/adr](adr/).

Na fatia 1 existem identity, catalog, as duas apps Next.js, o gateway e a observabilidade. Os serviços cart,
promotions, orders, payments e shipping, o RabbitMQ e o Redis aparecem no diagrama porque fazem parte do desenho, mas
só chegam nas fatias 2 a 3.

## Visão geral

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

## Responsabilidades

| Serviço | Responsável por | Fatia |
|---|---|---|
| identity | Clientes, funcionários, login, tokens, papéis e permissões, endereços | 1 (RBAC completo na 4) |
| catalog | Produtos, variantes (SKU), categorias, coleções, imagens, estoque por SKU, busca, configuração da vitrine | 1 (edição da vitrine na 4) |
| cart | Carrinho de visitante e de cliente logado, merge no login, revalidação de preço e estoque | 2 |
| promotions | Cupons, regras de desconto, limites de uso | 2 |
| orders | Pedido, máquina de estados, orquestração da saga de checkout | 3 |
| payments | Cobrança Pix e cartão, webhooks, estornos | 3 |
| shipping | Cotação por CEP, etiqueta, rastreio | 3 |

Hoje a fatia 1 entrega identity e catalog. O estoque fica no catalog ([ADR 0004](adr/0004-estoque-no-catalog.md)).

## Regras de comunicação

- **Leitura entre serviços:** REST síncrono pelo cliente HTTP da lib compartilhada (`ks_platform/http.py`): timeout curto
  (2 s), uma nova tentativa só para GET que falhou ao conectar (nunca para outros métodos) e propagação do
  `traceparent`. Um circuit breaker simples está previsto (spec seção 3.2), mas ainda não existe: nenhum serviço da
  fatia 1 chama outro serviço, só o JWKS do identity.
- **Mudança de estado que outros precisam saber:** evento publicado via transactional outbox. A linha do evento entra
  na mesma transação da mudança e um relay publica no RabbitMQ ([ADR 0003](adr/0003-rabbitmq.md)).
- **Consumidores:** sempre idempotentes, com tabela `processed_events(event_id)`, fila de falhas (DLQ) e
  reprocessamento pelo admin (fatia 4).
- **Checkout (fatia 3):** saga orquestrada pelo orders ([ADR 0002](adr/0002-saga-orquestrada.md)). Passos: reservar
  estoque, aplicar cupom, cotar e fixar frete, cobrar, confirmar pedido. Cada passo tem uma compensação: liberar
  estoque, devolver o uso do cupom, estornar.
- **Nenhum serviço acessa o banco de outro.** Cada serviço tem um usuário Postgres com permissão só no próprio banco
  ([ADR 0001](adr/0001-microsservicos-banco-por-servico.md)).

## Gateway e limites de taxa

O Traefik (`infra/traefik/dynamic.yml`) roteia `api.katoshop.localhost/identity` e `/catalog` (removendo o prefixo),
`katoshop.localhost` para a loja e `admin.katoshop.localhost` para o admin. O dashboard fica em `127.0.0.1:8081`.

Limite `auth-ratelimit`: 10 req/s em média, rajada de 20, por IP de origem. Ele vale para:

- os endpoints de credencial do identity no gateway: login, login de funcionário e cadastro. Refresh e logout ficam de
  fora, porque os BFFs das apps saem pelo mesmo IP e esgotariam o balde renovando sessões (R15);
- `POST /entrar` e `POST /criar-conta` da loja e `POST /entrar` do admin, para que o limite volte a ser por cliente,
  já que o identity só enxerga o IP do container do Next (R20);
- todo `POST` com cabeçalho `Next-Action` nas duas apps, porque o Next despacha Server Actions pelo cabeçalho e não pelo
  caminho (R24). Uso muito intenso de uma action (mais de 10 por segundo) pode receber 429.

Uploads de imagem passam por um limite de corpo de 9 MiB no router do catalog. O identity mantém o próprio limite por
IP como retaguarda, e bloqueia a conta por 15 minutos depois de 5 falhas seguidas de login.

## Autenticação

O identity emite JWT EdDSA e cada serviço valida o token sozinho ([ADR 0006](adr/0006-validacao-jwt-por-servico.md)).
As apps guardam os tokens em cookies httpOnly e chamam o gateway no servidor
([ADR 0005](adr/0005-bff-cookies-httponly.md)). Audiências separadas (`storefront`, `admin`): um token de cliente
recebe 403 em qualquer rota do admin.

## Eventos previstos

Nome no formato `<serviço>.<entidade>.<fato>.v<versão>`. Nenhum evento é publicado na fatia 1.

| Evento | Fatia |
|---|---|
| `catalog.variant.price_changed.v1`, `catalog.variant.stock_changed.v1`, `catalog.product.archived.v1` (consumidos pelo cart) | 2 |
| `orders.order.placed.v1`, `orders.order.confirmed.v1`, `orders.order.cancelled.v1` | 3 |
| `payments.payment.approved.v1`, `payments.payment.failed.v1`, `payments.refund.completed.v1` | 3 |
| `shipping.shipment.created.v1`, `shipping.shipment.status_changed.v1` | 3 |
| `promotions.coupon.redeemed.v1` | 3 |

Envelope padrão: `id` (UUIDv7), `type`, `version`, `occurred_at`, `correlation_id`, `causation_id`, `producer`, `data`.

## Observabilidade

OpenTelemetry nos serviços e nas apps Next.js, com propagação W3C `traceparent` ponta a ponta. O Collector envia traces
ao Jaeger e métricas ao Prometheus; o Grafana sobe provisionado com um dashboard RED por serviço. Esses componentes
ficam no perfil `observability` do Compose e não sobem com `pnpm dev:up`.

Os serviços devolvem o `trace_id` no corpo de todo erro `problem+json`. Nas apps, a página de erro 5xx mostra o
`digest` do Next como "Código para suporte", porque o Next não repassa o trace ao navegador. Para achar o trace a
partir desse código, o `onRequestError` exportado em `apps/*/instrumentation.ts` escreve no stderr do container uma
linha JSON com `event: "request_error"`, o `digest` e o `trace_id` do span ativo (além de método, caminho e rota;
cabeçalhos ficam fora). O suporte procura o código no log (`docker compose logs storefront | grep <digest>`) e abre o
`trace_id` no Jaeger.

## Convenções de API

Prefixo `/v1`, JSON em snake_case, erros `application/problem+json` com `code` estável (`<serviço>.<área>.<motivo>`),
dinheiro em inteiros `_cents`, IDs UUIDv7, datas em UTC, paginação por cursor (`limit` padrão 24, máximo 100).
