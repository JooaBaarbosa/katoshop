# ADR 0002: Orquestração da saga de checkout em vez de coreografia

## Contexto

O checkout atravessa vários serviços: reservar estoque (catalog), aplicar cupom (promotions), cotar e fixar frete
(shipping), cobrar (payments) e confirmar o pedido (orders). Cada passo pode falhar e os anteriores precisam ser
desfeitos (liberar estoque, devolver o uso do cupom, estornar). Não há transação distribuída: cada serviço tem o seu
banco (ADR 0001).

Esta decisão é registrada na fatia 1 porque define a forma como o catalog expõe o estoque. A saga em si é implementada
na fatia 3.

## Decisão

Saga orquestrada. O serviço orders é o orquestrador: ele persiste o estado da saga no próprio banco, envia os comandos
de cada passo e decide a compensação quando um passo falha. Cada passo tem uma compensação definida. Os demais serviços
só reagem a comandos e respondem com eventos, sem conhecer o fluxo completo.

Na fatia 1 isso aparece só na preparação do catalog: o modelo de estoque já separa `stock_on_hand` e `stock_reserved`,
e as operações `reserve`, `release` e `commit` entram na fatia 3 como comandos da saga (ver ADR 0004).

## Consequências

- O fluxo do checkout fica legível em um lugar só, com o estado persistido, o que facilita o diagnóstico, os testes de
  cada ponto de falha e a exibição no admin e no Jaeger.
- O orders vira um ponto de acoplamento: conhece os comandos de todos os participantes. É o preço aceito pela
  clareza.
- Cada participante precisa de comandos idempotentes (mesmo comando, mesmo efeito) e de compensações seguras para serem
  repetidas, porque a entrega do broker é pelo menos uma vez (ADR 0003).
- O orquestrador precisa tratar timeouts e retomar sagas interrompidas depois de uma queda. Isso é trabalho da fatia 3.

## Alternativas consideradas

- **Coreografia por eventos:** sem ponto central, mas o fluxo fica espalhado entre os serviços. É difícil de entender,
  de testar ponta a ponta e de mostrar para um recrutador em poucos minutos.
- **Transação distribuída (2PC):** inadequada para serviços independentes com brokers e provedores externos de
  pagamento, e pouco usada na prática.
- **Fluxo síncrono em cadeia no orders, sem estado persistido:** simples, mas perde compensação confiável quando o
  processo cai no meio do checkout.
