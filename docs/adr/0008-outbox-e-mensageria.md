# ADR 0008: Outbox transacional e consumo idempotente de eventos

## Contexto

Na fatia 2 o carrinho guarda uma cópia do preço, do estoque e do status de cada item (spec da fatia 2, seção 2,
abordagem A). Essa cópia precisa acompanhar o catalog: quando o admin muda o preço, ajusta o estoque, desativa uma
variante ou arquiva um produto, o carrinho que contém o item deve mudar e avisar o cliente. O catalog e o cart têm
armazenamentos diferentes (Postgres e Redis), então não há transação que cubra os dois. O broker é o RabbitMQ
([ADR 0003](0003-rabbitmq.md)).

Publicar o evento direto no broker, dentro do handler HTTP do catalog, deixa duas janelas de inconsistência:

- o commit no Postgres funciona e a publicação falha (broker fora, processo cai entre um e outro): a mudança existe,
  mas nenhum carrinho fica sabendo;
- a publicação funciona e o commit falha: o carrinho aplica uma mudança que não aconteceu.

## Decisão

### Outbox no produtor

O catalog grava o evento numa tabela `outbox` na mesma transação da mudança (lib `ks_platform`, `outbox.py`). A linha
leva o envelope completo (`id` UUIDv7, `type`, `version`, `occurred_at`, `correlation_id`, `causation_id`, `producer`,
`data`), `published_at` nulo e o `traceparent` W3C da requisição que gerou o evento. Um rollback não deixa evento.

Eventos desta fatia, no exchange `catalog.events` (topic, durável), com o nome do evento como routing key:

- `catalog.variant.price_changed.v1`: mudança no preço da variante, ou no preço base para cada variante que herda o
  preço;
- `catalog.variant.stock_changed.v1`: ajuste de estoque, e desativação da variante (com `available: 0`);
- `catalog.product.archived.v1`: arquivamento do produto, com a lista de variantes.

Toda escrita que emite evento de variante incrementa `variants.version`, inclusive ajuste de estoque e mudança herdada
do preço base (ruling S4). O `data.version` do evento é essa versão.

### Relay no processo do serviço

Uma tarefa assíncrona dentro do processo do catalog lê lotes de até 100 linhas não publicadas com
`SELECT ... FOR UPDATE SKIP LOCKED`, publica cada uma com *publisher confirms* e mensagem persistente, e só então marca
`published_at`. Lote cheio repete na hora; senão espera 1 s. Com o RabbitMQ fora, as linhas acumulam e saem quando
ele volta (a escrita no catalog continua funcionando). Linhas publicadas há mais de 7 dias são apagadas pelo próprio
relay. O `SKIP LOCKED` permite mais de uma réplica do catalog sem publicar a mesma linha em paralelo.

Rastreamento (ruling S5): o relay publica dentro do contexto do `traceparent` guardado na linha, e o publisher injeta
esse contexto nos headers AMQP. O consumidor abre o span de processamento como filho desse contexto. Assim um trace
no Jaeger atravessa admin, catalog, RabbitMQ e cart (critério de aceite 8), mesmo com a publicação acontecendo
depois da resposta HTTP. O `correlation_id` do envelope é o trace id.

### Consumidor com retry e DLQ

O `EventConsumer` da `ks_platform` declara a topologia na subida do cart:

- fila durável `cart.catalog-events`, ligada a `catalog.variant.*.v1` e `catalog.product.archived.v1`;
- filas de espera `cart.catalog-events.retry.1s`, `.retry.5s` e `.retry.25s`, com TTL e dead letter de volta para a
  fila principal;
- DLQ `cart.catalog-events.dlq`.

Se o handler falha, a mensagem é republicada (com confirm) na fila de espera da tentativa seguinte e só então recebe
ack. São a entrega original e três novas tentativas (1 s, 5 s e 25 s); se a última também falha, a mensagem vai para a
DLQ com o erro num header. Envelope inválido vai direto para a DLQ. Payload com formato errado ou tipo desconhecido é
registrado em log e marcado como processado, para não girar no retry. A tela de DLQ e o reprocessamento ficam para a
fatia 4.

### Garantia e idempotência

A entrega é *at-least-once*: o relay pode publicar de novo uma linha cujo confirm chegou mas cuja marcação falhou, e
o broker pode reentregar. O consumidor do cart é idempotente em três camadas:

- **`processed_events`:** uma chave `processed_events:{event_id}` no Redis com TTL de 7 dias. Evento já visto recebe
  ack sem efeito. A marcação acontece depois de atualizar todos os carrinhos afetados, então uma falha no meio
  reaplica o evento inteiro.
- **Guarda de versão:** preço e estoque só são aplicados se `data.version` for maior que a versão guardada no item.
  Evento repetido ou fora de ordem não volta o item para um estado antigo.
- **Arquivado permanente (rulings S7 e S10):** a marca `archived` do item é *sticky*. Eventos de preço e estoque nunca
  reativam um item arquivado, porque o catalog continua emitindo `stock_changed` de produto arquivado e o evento de
  arquivamento não tem versão. Só uma nova inclusão de um produto ativo limpa a marca, e no merge do login a linha fica
  arquivada se qualquer um dos lados estiver arquivado.

A ordem é por agregado, no melhor esforço: há uma fila por consumidor, e a versão cobre a reordenação causada por
retry.

## Consequências

- Nenhuma mudança do catalog se perde entre o commit e a publicação, e nenhum evento sai de uma transação desfeita.
- O relay não exige processo nem container extra, mas fica acoplado ao ciclo de vida do catalog: com o catalog parado,
  nada é publicado (o que é coerente, porque também nada muda).
- Eventos publicados antes de a fila `cart.catalog-events` existir não têm rota e se perdem (ruling S3). As filas são
  duráveis depois de declaradas, o cart declara a topologia na subida e o compose sobe o cart junto com o broker. Aceito:
  a perda só acontece numa janela em que o cart nunca rodou, e um carrinho criado depois lê o preço atual ao adicionar o
  item.
- Uma linha da outbox que sempre falha ao publicar bloqueia as seguintes do lote (não há estado de "estacionada").
  Não acontece com os eventos desta fatia, que são JSON gerado pelo próprio catalog.
- Limitação conhecida: o arquivamento não tem versão. Se uma reentrega acontece depois de um processamento parcial (o
  evento atualizou parte dos carrinhos e falhou antes da marcação em `processed_events`), o arquivamento é aplicado de
  novo e pode fazer reaparecer um aviso que o cliente já tinha confirmado com "Entendi", ou arquivar de novo uma linha
  que o cliente adicionou outra vez nesse intervalo. É raro e não deixa preço nem estoque errado.
- A deduplicação do cart é "verifica e depois marca", não atômica. Os handlers continuam corretos sob execução dupla
  por causa da guarda de versão e do arquivado permanente.
- O painel do Grafana acompanha profundidade das filas, taxa de consumo, backlog da outbox e mensagens na DLQ.

## Alternativas consideradas

- **Publicar direto no broker dentro do handler HTTP:** mais simples, mas com as duas janelas de inconsistência do
  contexto.
- **Relay em processo ou container separado:** isola a publicação do serviço, mas acrescenta um deploy por produtor
  sem ganho numa demo local. A lib permite mover o relay depois sem mudar o formato da outbox.
- **Change data capture (Debezium lendo o WAL do Postgres):** sem polling, mas traz Kafka Connect e mais um conjunto de
  peças para operar, fora do que a demo quer mostrar.
- **Retry com `nack` e requeue imediato:** sem backoff, uma mensagem com falha transitória gira em loop quente e
  atrasa as outras. As filas de espera com TTL dão backoff sem plugin do RabbitMQ.
- **Exactly-once:** o RabbitMQ não oferece, e simular exigiria transação distribuída entre Redis e broker. A
  idempotência no consumidor resolve o mesmo problema com menos peças.
