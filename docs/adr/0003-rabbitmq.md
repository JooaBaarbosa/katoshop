# ADR 0003: RabbitMQ como broker de eventos

## Contexto

A partir da fatia 2, mudanças de estado que outros serviços precisam conhecer viajam como eventos (spec seção 3.2):
`catalog.variant.price_changed.v1`, `orders.order.placed.v1` e outros. O padrão é o transactional outbox: a linha do
evento entra na mesma transação da mudança e um relay publica no broker. Os consumidores são idempotentes
(`processed_events`), com fila de falhas (DLQ) e reprocessamento pelo admin (fatia 4). Precisamos de um broker que
rode no Docker Compose local com pouca memória, tenha roteamento por tipo de evento e tenha painel de administração.

## Decisão

RabbitMQ (a spec indica a imagem `4.4.0-management-alpine`; a versão estável é conferida de novo quando a fatia 2
começar), com uma exchange de tópicos, filas duráveis por consumidor e dead letter exchange por fila. O nome do evento
(`<serviço>.<entidade>.<fato>.v<versão>`) é a routing key.

O broker não entra na fatia 1: nenhum serviço da fatia publica ou consome eventos, e por isso o RabbitMQ ainda não
está no `compose.yaml`. O outbox e o envelope de evento entram na lib `ks_platform` na fatia 2.

## Consequências

- Filas, DLQ, TTL e reprocessamento são recursos nativos, e o painel de gestão alimenta a tela de saúde do sistema do
  admin (fatia 4).
- A entrega é pelo menos uma vez, então todo consumidor precisa ser idempotente. O broker não oferece reprodução do
  histórico como um log distribuído.
- Mais um container para manter, com consumo de memória próprio.
- Ordem de eventos só é garantida dentro de uma fila com um consumidor. As specs das fatias tratam a reordenação quando
  importa, por exemplo com a versão do agregado no payload.

## Alternativas consideradas

- **Kafka:** log durável com reprodução e partições, mas é pesado para uma máquina de desenvolvimento e mais do que o
  volume de uma loja demo pede. A operação (KRaft, tópicos, offsets) distrai do que o projeto quer mostrar.
- **Redis Streams:** o Redis já entra para o carrinho, mas DLQ, roteamento por padrão e painel de administração
  ficariam por nossa conta.
- **Postgres como fila (LISTEN/NOTIFY ou leitura periódica da tabela de outbox):** menos peças, mas não demonstra um
  broker de mensagens real e deixa o roteamento e a DLQ por nossa conta.
