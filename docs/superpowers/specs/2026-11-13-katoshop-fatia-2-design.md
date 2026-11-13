# KatoShop fatia 2: carrinho reativo a eventos e motor de cupons

- **Data:** 2026-11-13
- **Status:** aguardando revisão
- **Base:** spec geral `docs/superpowers/specs/2026-10-23-katoshop-design.md`. Arquitetura e convenções da seção 4 continuam valendo.
- **Valem também:** as decisões R1 a R29 da fatia 1, registradas no README ("Limitações conhecidas") e nos ADRs 0001 a 0007.

## 1. Objetivo e critérios de aceite

A loja passa a ter um carrinho de verdade, que reage a mudanças do catálogo por eventos. O cliente pode aplicar um cupom e ver o desconto. O admin cria e gerencia cupons. Esta fatia introduz a mensageria (RabbitMQ + outbox) e dois serviços novos: `cart` e `promotions`.

Critérios de aceite:
1. Um visitante adiciona produtos ao carrinho sem login, e o carrinho sobrevive a refresh e a restart do Redis.
2. Ao entrar na conta, o carrinho do visitante é unido ao da conta. O mesmo SKU tem as quantidades somadas, limitadas ao estoque, com aviso.
3. O admin muda o preço de uma variante, e em até 5 segundos o carrinho que contém o item mostra o preço novo com o aviso "preço mudou de R$ X para R$ Y".
4. Zerar o estoque ou arquivar o produto marca o item como indisponível. Reduzir o estoque abaixo da quantidade reduz a quantidade, com aviso.
5. Um cupom válido mostra o desconto calculado no carrinho. Um inválido mostra o motivo em pt-BR (expirado, pedido mínimo, sem itens elegíveis, etc.).
6. O admin cria, edita (com conflito de versão) e desativa cupons de percentual e de valor fixo, com as condições da seção 5.
7. Evento repetido não tem efeito duplo. Evento com versão antiga é ignorado. Mensagem que falha 3 vezes vai para a DLQ.
8. Um trace no Jaeger atravessa admin → catalog → RabbitMQ → cart.
9. A CI fica verde, incluindo os novos testes de integração com RabbitMQ e Redis reais e o e2e.

Fora desta fatia:
- resgate do cupom e contagem de usos: fatia 3, no checkout;
- frete grátis: fatia 3, depende do serviço de frete;
- tela de DLQ e reprocessamento no admin: fatia 4;
- promoções automáticas (sem código) e cumulatividade de cupons.

## 2. Decisões tomadas no brainstorming

| Tema | Decisão |
|---|---|
| Regras de cupom | Percentual e valor fixo; pedido mínimo; validade; limite total e por cliente; restrição a categorias ou coleções; um cupom por carrinho |
| Mudança de preço ou estoque | O carrinho atualiza e avisa por item |
| Merge no login | Soma por SKU limitada ao estoque; cupom do visitante prevalece se válido; carrinho de visitante expira em 30 dias, o de cliente não expira |
| Arquitetura | Abordagem A: o carrinho guarda uma cópia dos dados do item, atualizada por eventos do catálogo; o cupom é avaliado sob demanda por REST no promotions |

## 3. Mensageria (RabbitMQ + outbox)

### 3.1 Topologia
- Um exchange `topic` por produtor. Nesta fatia: `catalog.events`.
- Routing key igual ao nome do evento (`catalog.variant.price_changed.v1`).
- Cada consumidor tem fila durável própria. Nesta fatia: `cart.catalog-events`, ligada a `catalog.variant.*.v1` e `catalog.product.archived.v1`.
- Cada fila tem DLQ (`cart.catalog-events.dlq`). São 3 tentativas com backoff exponencial (1 s, 5 s, 25 s) via fila de espera com TTL; depois a mensagem vai para a DLQ.

### 3.2 Outbox (catalog, com apoio da lib `ks_platform`)
- **Tabela `outbox`:** `id` (UUIDv7, igual ao `id` do evento), `type`, `payload` jsonb (o envelope completo), `created_at`, `published_at` (nulo até publicar), `attempts`.
- **Gravação:** a linha entra na mesma transação da mudança: ajuste de preço da variante ou do preço base, ajuste de estoque, ativar ou desativar variante e arquivar produto.
- **Relay:** uma tarefa no processo do catalog lê lotes de até 100 linhas não publicadas, com `FOR UPDATE SKIP LOCKED`, a cada 1 s. Publica com *publisher confirms* e marca `published_at`. Se o RabbitMQ estiver fora, as linhas acumulam e saem quando ele voltar, com log de aviso e métrica de backlog.
- **Limpeza:** linhas publicadas há mais de 7 dias são apagadas pelo próprio relay.
- **Garantia:** entrega *at-least-once*. A ordem é por agregado, no melhor esforço. O payload leva `version` da variante para o consumidor descartar evento antigo.

### 3.3 Consumidor idempotente (lib `ks_platform`)
- Interface genérica: o consumidor registra um handler por tipo de evento. A lib cuida de ack/nack, retry, DLQ, extração do `traceparent` dos headers AMQP e do registro de eventos processados.
- **Idempotência no cart:** SET `processed_events` no Redis com o `id` do evento e TTL de 7 dias. Evento já visto é descartado com ack.
- **Versão:** evento com `version` menor ou igual à guardada no item é ignorado.

### 3.4 Envelope e eventos
- Envelope (spec geral §3.3): `id`, `type`, `version`, `occurred_at`, `correlation_id`, `causation_id`, `producer`, `data`. O `traceparent` vai nos headers AMQP.

| Evento | `data` |
|---|---|
| `catalog.variant.price_changed.v1` | `{variant_id, sku, product_id, old_price_cents, new_price_cents, version}` |
| `catalog.variant.stock_changed.v1` | `{variant_id, sku, available, version}` |
| `catalog.product.archived.v1` | `{product_id, variant_ids[]}` |

- Mudança no preço base gera um `price_changed` para cada variante sem preço próprio.
- Desativar variante gera `stock_changed` com `available: 0`.
- Publicar produto não gera evento nesta fatia, porque não há consumidor.

## 4. Serviço cart (FastAPI + Redis)

### 4.1 Modelo no Redis
- **`cart:{cart_id}` (hash):**
  - `owner`: `guest:{uuid}` ou `user:{user_id}`;
  - `coupon_code`;
  - `updated_at`;
  - `version`, usado em lock otimista com WATCH/MULTI.
- **`cart:{cart_id}:items` (hash por `variant_id`):** valor JSON com `variant_id, product_id, product_slug, name, color_code, color_name, size_code, image_url, unit_price_cents, available, category_slug, collection_slugs[], quantity, item_version, notice?`.
- **`variant:{variant_id}:carts` (SET):** índice reverso para o consumidor de eventos.
- **`user:{user_id}:cart`:** aponta para o `cart_id` do cliente.
- **TTL:** carrinho de visitante expira em 30 dias, renovado a cada uso. Carrinho de cliente não expira.
- **Persistência:** Redis com AOF (`appendfsync everysec`).

### 4.2 Identidade do carrinho
- **Cliente logado:** token storefront.
- **Visitante:** header `X-Cart-Id` com o ID opaco (UUIDv4 aleatório), que o BFF lê do cookie `ks_cart`. O ID só é aceito se o carrinho existir e for de visitante.
- Um token de cliente com `X-Cart-Id` de visitante é usado só no merge.

### 4.3 API (`/v1`, via Traefik em `/cart`)

| Rota | Comportamento |
|---|---|
| `GET /v1/cart` | `{items, notices, subtotal_cents, discount_cents, total_cents, coupon: {code, valid, reason?} \| null, checkout_blocked}`. Carrinho inexistente devolve um carrinho vazio. |
| `POST /v1/cart/items` | `{variant_id, quantity}`. Valida no catalog (variante e produto ativos, preço, disponível). Soma ao item existente, limitado ao disponível; acima disso devolve 422 `cart.item.quantity_exceeds_stock` com o máximo. Se o carrinho de visitante não existir, cria e devolve `cart_id`. |
| `PATCH /v1/cart/items/{variant_id}` | `{quantity}`. Quantidade 0 remove. |
| `DELETE /v1/cart/items/{variant_id}` | Remove. |
| `DELETE /v1/cart/items/unavailable` | Remove todos os itens marcados como indisponíveis. |
| `POST /v1/cart/notices/ack` | Limpa os avisos já vistos. |
| `PUT /v1/cart/coupon` | `{code}`. Avalia no promotions. Inválido devolve 422 com o motivo e não grava o cupom. |
| `DELETE /v1/cart/coupon` | Remove o cupom. |
| `POST /v1/cart/merge` | Só com token de cliente, `{guest_cart_id}`. Une os itens (soma limitada ao estoque, com aviso `quantity_reduced`), mantém o cupom do visitante se ainda for válido (senão o da conta) e apaga o carrinho do visitante. |

- **Limites:** até 50 itens distintos e quantidade de 1 a 20 por SKU.
- **Erros:** `cart.<área>.<motivo>` em problem+json.

### 4.4 Avisos por item

| Código | Dados | Quando |
|---|---|---|
| `price_changed` | `old_price_cents, new_price_cents` | evento de preço |
| `quantity_reduced` | `quantity` (nova) | estoque abaixo da quantidade, ou merge |
| `unavailable` | nenhum | estoque 0, variante desativada ou produto arquivado |

- O aviso some com `POST /v1/cart/notices/ack` ou quando o cliente altera o item.
- `checkout_blocked` fica verdadeiro enquanto houver item `unavailable`. Isso prepara a fatia 3.
- Se o item voltar a ter estoque, o aviso `unavailable` sai e a quantidade fica em 1 (o cliente reajusta).

### 4.5 Cálculo
- Subtotal: soma de `unit_price_cents × quantity`, só dos itens disponíveis.
- Desconto: o cart chama o promotions a cada `GET /v1/cart` com cupom. O resultado fica em cache no Redis por 30 s, com chave que inclui a versão do carrinho.
- Total: subtotal menos desconto, nunca negativo.
- **Promotions fora do ar:** o carrinho funciona sem desconto e devolve `coupon.reason = "promotions.unavailable"`. A loja mostra "Não foi possível validar o cupom agora".

### 4.6 Consumidor de eventos
- O cart roda o consumidor no próprio processo (tarefa de background no lifespan).
- Para cada evento, atualiza os itens de todos os carrinhos do índice reverso, numa transação Redis por carrinho:
  - `price_changed`: novo preço e aviso.
  - `stock_changed`: quantidade e aviso, ou `unavailable`.
  - `archived`: `unavailable`.

## 5. Serviço promotions (FastAPI + Postgres)

### 5.1 Modelo
- **`coupons`:**

  | Coluna | Detalhe |
  |---|---|
  | `id` | UUIDv7 |
  | `code` | único, maiúsculo, `^[A-Z0-9-]{3,32}$` |
  | `description` | |
  | `kind` | `percent` ou `fixed` |
  | `value` | percentual inteiro de 1 a 90, ou centavos maiores que 0 |
  | `min_order_cents` | nulo ou maior que 0 |
  | `starts_at`, `ends_at` | `timestamptz`; `ends_at > starts_at` quando ambos existem |
  | `category_slugs` | `text[]` |
  | `collection_slugs` | `text[]` (as duas listas vazias valem para a loja toda) |
  | `max_uses_total`, `max_uses_per_customer` | inteiros maiores que 0 ou nulos |
  | `active` | |
  | `version` | |
  | `created_at`, `updated_at` | |

- **`coupon_redemptions`:** `id`, `coupon_id`, `customer_id`, `order_id` único, `created_at`. A tabela é criada nesta fatia e gravada só na fatia 3.

### 5.2 Avaliação (interna): `POST /v1/promotions/evaluate`
- Acesso só com token de serviço (seção 6). A rota não é exposta pelo Traefik.
- Entrada: `{code, customer_id?, items: [{variant_id, unit_price_cents, quantity, category_slug, collection_slugs[]}]}`.
- Regras, em ordem:
  1. `promotions.coupon.not_found`: o código não existe (comparação sem diferenciar maiúsculas).
  2. `promotions.coupon.inactive`.
  3. `promotions.coupon.not_started` ou `promotions.coupon.expired`.
  4. `promotions.coupon.no_eligible_items`: um item é elegível se o cupom não tiver restrição, ou se a categoria do item estiver em `category_slugs`, ou se alguma coleção do item estiver em `collection_slugs`.
  5. `promotions.coupon.min_order_not_met`: a soma dos itens elegíveis é menor que `min_order_cents` (a resposta inclui o valor mínimo).
  6. `promotions.coupon.usage_limit_reached`: limite total atingido.
  7. `promotions.coupon.login_required` quando há `max_uses_per_customer` e o cliente é visitante; `promotions.coupon.customer_limit_reached` quando o cliente já atingiu o limite dele.
- Cálculo:
  - `percent`: `floor(soma_elegíveis × value / 100)`.
  - `fixed`: `min(value, soma_elegíveis)`.
  - O desconto é rateado entre os itens elegíveis em proporção ao valor de cada um (arredondando para baixo), e o resto em centavos vai para o item elegível de maior valor.
- Saída: `{valid, code, discount_cents, per_item: [{variant_id, discount_cents}], reason?, min_order_cents?}`.

### 5.3 Admin: `/v1/admin/coupons` (via Traefik em `/promotions`)
- Permissão `promotions.write`. O papel `admin` concede `*`.
- Rotas: `GET` (lista com filtro `q`, `active` e paginação por cursor), `POST`, `GET /{id}`, `PATCH /{id}` (exige `version`; divergência devolve 409 `promotions.coupon.version_conflict`), `POST /{id}/activate` e `POST /{id}/deactivate`.
- Código repetido devolve 409 `promotions.coupon.code_taken`. O código não pode ser alterado depois de criado.
- `DELETE` só é permitido sem resgates. Com resgates, devolve 409 `promotions.coupon.has_redemptions`.
- A lista mostra `uses_count`, que fica em 0 nesta fatia.

## 6. Autenticação entre serviços
- Endpoint novo no identity: `POST /v1/auth/service-token` com `{client_id, client_secret}`. Os segredos vêm do env, um por serviço cliente (nesta fatia, só `cart`).
- Resposta: JWT EdDSA com `aud="service"`, `kind="service"`, `sub=<client_id>`, `roles=[]`, validade de 300 s.
- O cart guarda o token em memória e renova 30 s antes de expirar.
- O promotions exige `require_audience("service")` no evaluate. O catalog exige o mesmo no endpoint interno de variante (seção 7).
- A rota de token de serviço não passa pelo Traefik. Só é acessível na rede interna do compose.
- `ks_platform.auth` passa a aceitar `kind="service"` no `Principal`.
- Segue o ADR 0006: cada serviço valida o próprio token, e nenhuma rota interna confia só na rede.

## 7. Mudanças no catalog
- Outbox, relay e eventos (seção 3).
- Endpoint interno `GET /v1/internal/variants/{variant_id}` com token de serviço. Devolve `{variant_id, sku, product_id, product_slug, product_status, name, color_code, color_name, size_code, unit_price_cents, available, active, image_url, category_slug, collection_slugs[], version}`. Variante inexistente devolve 404.
- Mudança de coleção não gera evento nesta fatia. O carrinho guarda as coleções do momento em que o item entrou.

## 8. Loja (apps/storefront)
- **Cookie `ks_cart`:** ID do carrinho de visitante, httpOnly, `SameSite=Lax`, 30 dias. O BFF cria o cookie quando o cart devolve um `cart_id` novo.
- **No login e no cadastro:** o BFF chama `POST /v1/cart/merge` e apaga o `ks_cart`. Uma falha no merge não bloqueia o login, mas o cookie é mantido para a próxima tentativa.
- **Página de produto:** "Adicionar ao carrinho" vira uma Server Action que exige cor e tamanho escolhidos. Sai a nota "Carrinho chega na próxima versão" e entra um toast de confirmação. Os erros de estoque aparecem em linha.
- **Cabeçalho:** "Carrinho (N)" ativo, com a soma das quantidades.
- **`/carrinho`:**
  - itens com foto, nome, cor, tamanho, preço em mono limão, quantidade (botões − e +, acessíveis por teclado) e remover;
  - avisos por item;
  - "Limpar indisponíveis";
  - campo de cupom com o motivo em pt-BR;
  - resumo com subtotal, desconto e total;
  - "Finalizar compra" desabilitado com a nota "Checkout chega na próxima versão";
  - carrinho vazio com estado honesto e CTA "Todas as peças".
- Os avisos usam só dados reais. Sem urgência falsa, sem contador inventado, sem travessões.
- O carrinho é renderizado por requisição (R21). As ações são Server Actions com o rate limit R24.

## 9. Admin (apps/admin)
- Item **Cupons** ativo na barra lateral.
- `/cupons`: tabela com código, tipo, valor, validade, condições, status e usos.
- `/cupons/novo` e `/cupons/[id]`:
  - formulário com tipo, valor, pedido mínimo, datas, categorias e coleções (multisseleção vinda do catalog) e limites;
  - conflito de versão com o botão "Recarregar";
  - ativar e desativar;
  - excluir quando não houver usos.
- Mensagens pt-BR por código. O guard `staffAction` e o classificador de 403 (R25) são reaproveitados.

## 10. Infra
- **Compose, versões estáveis mais novas conferidas na hora do plano:**
  - `rabbitmq` na imagem `management-alpine`, UI em `127.0.0.1:15672`, credenciais do env;
  - `redis` na imagem `alpine` com AOF e volume próprio;
  - serviços `cart` e `promotions` com healthcheck, `mem_limit` e usuário não root.
- **Postgres:** novo banco `promotions` com usuário dono `promotions_svc`, no script de init.
- **Traefik:**
  - `/cart` e `/promotions` (este só para `/promotions/v1/admin`);
  - `evaluate`, `internal` e `service-token` não são roteados;
  - limite de corpo do cart em 64 KiB.
- **Observabilidade:**
  - instrumentação OTel do aio-pika e do Redis;
  - spans de publish e consume ligados pelo `traceparent`;
  - painel no Grafana com profundidade das filas, taxa de consumo, backlog do outbox e mensagens na DLQ.
- **CI:** novos workflows `ci-cart` e `ci-promotions`, iguais aos existentes. O `ci-catalog` ganha os testes de outbox com RabbitMQ real (testcontainers). O `ci-e2e` cobre os fluxos novos.

## 11. Testes
- **Unitários:**
  - promotions: cada regra na ordem; rateio e arredondamento (o total do rateio é igual ao desconto); limites; datas nas bordas;
  - cart: soma e limites por SKU; merge; aplicação de cada evento; avisos; `checkout_blocked`.
- **Integração com testcontainers:**
  - o outbox grava na mesma transação; um rollback não gera evento;
  - o relay publica e marca `published_at`; com o RabbitMQ fora, o relay acumula e publica quando ele volta;
  - o consumidor ignora evento duplicado e versão antiga;
  - a falha repetida leva a mensagem à DLQ após 3 tentativas;
  - o cart usa Redis real com TTL do visitante.
- **API:** rotas de cart e promotions, token de serviço (audiência errada devolve 403; rota interna sem token devolve 401), conflito de versão do cupom.
- **Contrato:** OpenAPI de cart e promotions versionados e cliente TS regenerado. A CI quebra em divergência.
- **E2E (Playwright):**
  1. visitante adiciona dois produtos, aplica cupom e vê o desconto;
  2. admin altera o preço de um item que está num carrinho aberto, e a loja mostra o aviso em até 5 s;
  3. visitante com itens faz login numa conta que já tem carrinho, e as quantidades são somadas;
  4. admin cria um cupom restrito a uma coleção, que vale para o item da coleção e é recusado para outro.

## 12. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Evento perdido entre o commit e a publicação | Outbox na mesma transação; o relay republica até receber confirmação |
| Evento duplicado ou fora de ordem | Idempotência por `id` e descarte por `version` |
| Mensagem envenenada travando a fila | 3 tentativas com backoff e depois DLQ, com painel de alerta |
| Promotions indisponível | O carrinho segue sem desconto e informa o motivo |
| Redis reiniciando | AOF e volume; teste de restart no e2e local |
| Mais containers pesando na máquina | `mem_limit` por serviço; meta de RAM total abaixo de 7 GB |
