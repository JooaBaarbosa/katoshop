# Arquitetura do KatoShop

Este documento resume a arquitetura geral. O detalhamento completo está na spec
([design geral e fatia 1](superpowers/specs/2026-10-23-katoshop-design.md)) e as decisões em [docs/adr](adr/).

Depois da fatia 2 existem identity, catalog, cart, promotions, as duas apps Next.js, o gateway, o RabbitMQ, o Redis e
a observabilidade. Os serviços orders, payments e shipping aparecem no diagrama porque fazem parte do desenho, mas só
chegam na fatia 3. A spec da fatia 2 está em
[superpowers/specs/2026-11-13-katoshop-fatia-2-design.md](superpowers/specs/2026-11-13-katoshop-fatia-2-design.md).

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
                     Redis (carrinho)   RabbitMQ (eventos)
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

Hoje existem identity, catalog, cart e promotions. O estoque fica no catalog
([ADR 0004](adr/0004-estoque-no-catalog.md)). O cart não tem banco relacional: o carrinho vive no Redis, com AOF e
volume próprio. O promotions tem o banco `promotions` no Postgres, com usuário dono `promotions_svc`. A contagem de usos
do cupom (tabela `coupon_redemptions`) já existe, mas só é gravada no checkout da fatia 3.

## Regras de comunicação

- **Leitura entre serviços:** REST síncrono pelo cliente HTTP da lib compartilhada (`ks_platform/http.py`): timeout curto
  (2 s), uma nova tentativa só para GET que falhou ao conectar (nunca para outros métodos) e propagação do
  `traceparent`. Na fatia 2 o cart chama o catalog (variante interna) e o promotions (evaluate) com timeout de 2 s e um
  token de serviço ([ADR 0009](adr/0009-token-de-servico.md)). Os orçamentos se aninham (ruling S12): a avaliação do
  cupom que só monta a resposta do carrinho tem 800 ms no total, token incluído e sem o retry do 401, e degrada para
  desconto 0; o PUT do cupom mantém 2 s. O BFF da loja espera o cart por 4 s na leitura e 10 s na escrita. Um circuit
  breaker simples está previsto (spec geral, seção 3.2), mas ainda não existe.
- **Mudança de estado que outros precisam saber:** evento publicado via transactional outbox. A linha do evento entra
  na mesma transação da mudança e um relay publica no RabbitMQ ([ADR 0003](adr/0003-rabbitmq.md),
  [ADR 0008](adr/0008-outbox-e-mensageria.md)).
- **Consumidores:** sempre idempotentes (registro de eventos processados por `id` e descarte de versão antiga), com
  retry e fila de falhas (DLQ). O reprocessamento pelo admin chega na fatia 4.
- **Rotas internas:** só de serviço para serviço, com token de serviço e bloqueadas no gateway (seção
  [Gateway e limites de taxa](#gateway-e-limites-de-taxa)).
- **Checkout (fatia 3):** saga orquestrada pelo orders ([ADR 0002](adr/0002-saga-orquestrada.md)). Passos: reservar
  estoque, aplicar cupom, cotar e fixar frete, cobrar, confirmar pedido. Cada passo tem uma compensação: liberar
  estoque, devolver o uso do cupom, estornar.
- **Nenhum serviço acessa o banco de outro.** Cada serviço tem um usuário Postgres com permissão só no próprio banco
  ([ADR 0001](adr/0001-microsservicos-banco-por-servico.md)).

## Gateway e limites de taxa

O Traefik (`infra/traefik/dynamic.yml`) roteia `api.katoshop.localhost/identity`, `/catalog`, `/cart` e
`/promotions/v1/admin` (removendo o prefixo do serviço), `katoshop.localhost` para a loja e `admin.katoshop.localhost`
para o admin. O dashboard fica em `127.0.0.1:8081`.

Fronteiras do gateway:

- Toda regra com prefixo usa `PathRegexp` ancorado em fronteira de segmento (`^/catalog(/|$)`). `PathPrefix` compara
  texto, então `/catalogv1/...` casaria com o router do catalog e o `stripPrefix` entregaria `/v1/...` ao serviço, fora
  dos routers de bloqueio e de limite de taxa.
- O entrypoint `web` recusa `%2F` e `%5C` no caminho (400): o router compara o caminho codificado e o uvicorn
  decodifica, então `/identity/v1/auth%2Flogin` chegaria ao login sem o limite de taxa.
- O router `internal-block` (prioridade 1000) responde 404 sem corpo para `/catalog/v1/internal/...`,
  `/identity/v1/auth/service-token` e `/promotions/v1/promotions/...` (o evaluate). Essas rotas só são chamadas na rede
  interna do compose.
- Limite de corpo: 64 KiB no cart e no admin do promotions (acima disso, 413).

Limite `auth-ratelimit`: 10 req/s em média, rajada de 20, por IP de origem. Ele vale para:

- os endpoints de credencial do identity no gateway: login, login de funcionário e cadastro. Refresh e logout ficam de
  fora, porque os BFFs das apps saem pelo mesmo IP e esgotariam o balde renovando sessões (R15);
- `POST /entrar` e `POST /criar-conta` da loja e `POST /entrar` do admin, para que o limite volte a ser por cliente,
  já que o identity só enxerga o IP do container do Next (R20);
- todo `POST` com cabeçalho `Next-Action` nas duas apps, porque o Next despacha Server Actions pelo cabeçalho e não pelo
  caminho (R24). Uso muito intenso de uma action (mais de 10 por segundo) pode receber 429.

Os demais `POST` da loja (formulários de Server Action sem JavaScript, como "Adicionar ao carrinho" e as ações do
`/carrinho`) passam pelo `storefront-post-ratelimit`, com os mesmos parâmetros e balde próprio.

Uploads de imagem passam por um limite de corpo de 9 MiB no router do catalog. O identity não tem limite de taxa
próprio: a retaguarda é o router `identity-auth` do gateway (o mesmo `auth-ratelimit` nos endpoints de credencial). O
identity bloqueia a conta por 15 minutos depois de 5 falhas seguidas de login.

Troca aceita na fatia 1 (R28): login e cadastro feitos pelas apps chegam ao `identity-auth` pelo IP do container do Next,
então todos os clientes dividem um balde só nesse trecho. Um único IP, mesmo respeitando o limite por cliente de cada
router das apps, pode somar requisições em mais de um deles, esgotar esse balde e fazer o login de todos receber 429
enquanto durar o abuso. Para a demo local o risco é aceito. A correção prevista para uma fatia posterior: o BFF repassa um IP de cliente confiável ao identity, e
o identity aplica o limite por cliente.

## Autenticação

O identity emite JWT EdDSA e cada serviço valida o token sozinho ([ADR 0006](adr/0006-validacao-jwt-por-servico.md)).
As apps guardam os tokens em cookies httpOnly e chamam o gateway no servidor
([ADR 0005](adr/0005-bff-cookies-httponly.md)). Audiências separadas (`storefront`, `admin`): um token de cliente
recebe 403 em qualquer rota do admin.

Entre serviços (fatia 2), o cart obtém no identity um token de serviço por client credentials
(`POST /v1/auth/service-token`), com `aud="service"`, `kind="service"`, `sub=<client_id>` e validade de 300 s, e
renova 30 s antes de expirar. O catalog (rota interna de variante) e o promotions (evaluate) exigem a audiência
`service` ([ADR 0009](adr/0009-token-de-servico.md)).

O carrinho de visitante não tem token: o BFF guarda o id no cookie `ks_cart` (httpOnly, `SameSite=Lax`, 30 dias) e o
envia ao cart no cabeçalho `X-Cart-Id`. O id é um UUIDv4 aleatório; formato inválido responde 422
`cart.cart.invalid_id`, e um id desconhecido ou de carrinho de cliente é tratado como carrinho vazio, sem criar nada.

## Eventos

Nome no formato `<serviço>.<entidade>.<fato>.v<versão>`, usado também como routing key. As decisões de outbox, retry e
idempotência estão no [ADR 0008](adr/0008-outbox-e-mensageria.md).

### Publicados na fatia 2

| Evento | `data` | Quando |
|---|---|---|
| `catalog.variant.price_changed.v1` | `variant_id, sku, product_id, old_price_cents, new_price_cents, version` | preço da variante, ou preço base para cada variante que herda o preço |
| `catalog.variant.stock_changed.v1` | `variant_id, sku, available, version` | ajuste de estoque; desativar a variante gera `available: 0` |
| `catalog.product.archived.v1` | `product_id, variant_ids[]` | arquivar o produto |

`version` é a versão da variante, incrementada em toda escrita que emite evento de variante. Publicar produto não gera
evento nesta fatia, porque não há consumidor, e mudança de coleção também não: o carrinho guarda as coleções do momento
em que o item entrou.

### Topologia

```
catalog (Postgres)
  transação: mudança + linha na tabela outbox (com o traceparent da requisição)
        |
  relay no processo do catalog: lote de até 100 linhas, FOR UPDATE SKIP LOCKED, a cada 1 s,
  publisher confirms e depois published_at
        |
        v
exchange catalog.events (topic, durável)
        |  bindings: catalog.variant.*.v1, catalog.product.archived.v1
        v
fila cart.catalog-events (durável) ----> consumidor no processo do cart
        ^                                   |  sucesso: ack
        |                                   |  falha: republica na espera da tentativa seguinte e dá ack
        |                                   v
        +--- TTL --- cart.catalog-events.retry.1s
        +--- TTL --- cart.catalog-events.retry.5s
        +--- TTL --- cart.catalog-events.retry.25s
                                            |  falha depois da última espera (ou envelope inválido)
                                            v
                                 cart.catalog-events.dlq
```

O `traceparent` vai nos headers AMQP. O relay publica no contexto do trace que gravou o evento e o consumidor abre o
span de processamento como filho dele, então um trace do Jaeger vai do admin ao catalog, passa pelo RabbitMQ e chega
ao cart.

No cart, o consumidor:

1. descarta com ack um evento cujo `id` já está em `processed_events:{id}` (Redis, 7 dias);
2. acha os carrinhos pelo índice reverso `variant:{variant_id}:carts` e atualiza cada um numa transação Redis
   (WATCH/MULTI), sem renovar o TTL do visitante;
3. aplica preço e estoque só se `data.version` for maior que a versão guardada no item, e nunca reativa um item
   arquivado (o arquivado é permanente até uma nova inclusão de produto ativo);
4. remove do índice um carrinho que já expirou, sem falhar;
5. marca o evento como processado depois de todos os carrinhos.

### Previstos

| Evento | Fatia |
|---|---|
| `orders.order.placed.v1`, `orders.order.confirmed.v1`, `orders.order.cancelled.v1` | 3 |
| `payments.payment.approved.v1`, `payments.payment.failed.v1`, `payments.refund.completed.v1` | 3 |
| `shipping.shipment.created.v1`, `shipping.shipment.status_changed.v1` | 3 |
| `promotions.coupon.redeemed.v1` | 3 |

Envelope padrão: `id` (UUIDv7), `type`, `version`, `occurred_at`, `correlation_id`, `causation_id`, `producer`, `data`.

## Carrinho

O carrinho guarda uma cópia dos dados de cada item (nome, cor, tamanho, foto, preço, disponível, categoria e coleções),
atualizada pelos eventos do catálogo. Chaves no Redis:

- `cart:{id}` (hash): dono (`guest:{id}` ou `user:{user_id}`), cupom, `updated_at` e `version` (lock otimista);
- `cart:{id}:items` (hash por `variant_id`): o JSON de cada item, com quantidade, versão da variante e aviso;
- `user:{user_id}:cart`: o carrinho do cliente;
- `variant:{variant_id}:carts` (set): índice reverso para o consumidor de eventos.

O carrinho de visitante expira em 30 dias, renovado a cada uso pelo cliente; o do cliente não expira. Cada escrita é
uma transação WATCH/MULTI com novas tentativas; se todas perdem a corrida, a resposta é 409
`cart.cart.concurrent_update`. Duas abas adicionando ao mesmo tempo não perdem inclusões.

```
adicionar item
  navegador -> loja (Server Action) -> gateway /cart -> cart POST /v1/cart/items {variant_id, quantity}
  cart -> catalog GET /v1/internal/variants/{id} (token de serviço): variante e produto ativos, preço, disponível
  cart: soma ao item existente, limitado ao disponível (acima: 422 cart.item.quantity_exceeds_stock)
  visitante sem carrinho: cria, devolve cart_id, e a loja grava o cookie ks_cart

login ou cadastro
  loja -> cart POST /v1/cart/merge {guest_cart_id} com o token do cliente
  cart: soma por SKU limitada ao estoque (aviso quantity_reduced), cupom do visitante se ainda valer,
        item arquivado em qualquer lado continua arquivado, apaga o carrinho do visitante
  loja: apaga o cookie ks_cart (se o merge falhar, o login segue e o cookie fica para a próxima vez)

evento do catálogo
  catalog -> RabbitMQ -> cart: novo preço com aviso "preço mudou de R$ X para R$ Y", quantidade reduzida com aviso,
  ou item indisponível (estoque 0, variante desativada, produto arquivado)
```

Avisos por item: `price_changed`, `quantity_reduced` e `unavailable`. Eles somem com "Entendi"
(`POST /v1/cart/notices/ack`) ou quando o cliente altera o item. `checkout_blocked` fica verdadeiro enquanto houver item
indisponível, para o checkout da fatia 3.

## Cupons

O promotions guarda os cupons no Postgres e calcula o desconto sob demanda. O código é normalizado com `strip()` e
`upper()`, e o código salvo precisa casar com `^[A-Z0-9-]{3,32}$` (o admin recusa outro formato com 422
`request.validation`). Na aplicação, um código fora desse formato é só um cupom que não existe: o evaluate responde
`promotions.coupon.not_found`, e o `PUT /v1/cart/coupon` responde 422 `cart.coupon.invalid` com esse motivo (nunca
500).

```
aplicar cupom
  loja -> gateway /cart -> cart PUT /v1/cart/coupon {code}
  cart -> promotions POST /v1/promotions/evaluate (token de serviço)
          {code, customer_id?, items: [{variant_id, unit_price_cents, quantity, category_slug, collection_slugs[]}]}
  válido: grava o código no carrinho; inválido: 422 com o motivo, nada gravado; promotions fora: 503, nada gravado

ver o carrinho
  cart GET /v1/cart com cupom -> evaluate, com cache de 30 s no Redis por versão do carrinho
  promotions fora: o carrinho segue sem desconto, com coupon.reason = promotions.unavailable
```

Regras do evaluate, em ordem: código inexistente, inativo, fora da validade, sem itens elegíveis (restrição por
categoria ou coleção), pedido mínimo não atingido, limite total e limite por cliente (que exige login). Percentual:
`floor(soma_elegíveis × valor / 100)`. Valor fixo: `min(valor, soma_elegíveis)`. O desconto é rateado entre os itens
elegíveis em proporção ao valor de cada um, arredondando para baixo; os centavos que sobram vão um a um para os itens
de maior valor, sem passar do valor de nenhuma linha. A loja mostra o motivo de cada recusa em português.

No admin (`/promotions/v1/admin/coupons`, permissão `promotions.write`), o funcionário cria, edita com conflito de
versão (409 `promotions.coupon.version_conflict` e botão "Recarregar"), ativa, desativa e exclui cupons sem usos.

## Observabilidade

OpenTelemetry nos serviços e nas apps Next.js, com propagação W3C `traceparent` ponta a ponta. O Collector envia traces
ao Jaeger e métricas ao Prometheus; o Grafana sobe provisionado com um dashboard RED por serviço e o dashboard
"KatoShop mensageria" (profundidade da fila do cart, retry, DLQ, taxa de consumo, consumidores e backlog da outbox).
O aio-pika e o Redis também são instrumentados, e os spans de publish e consume se ligam pelo `traceparent`. Esses componentes
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
