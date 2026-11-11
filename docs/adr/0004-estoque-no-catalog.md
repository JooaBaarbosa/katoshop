# ADR 0004: Estoque dentro do catalog

## Contexto

O estoque pertence a cada variante (SKU) de produto. Um serviço de inventário separado seria o oitavo serviço e exigiria
sincronizar variantes, preços e estoque entre dois bancos para uma operação simples: mostrar "esgotado" por tamanho e
reservar unidades no checkout.

## Decisão

O estoque fica no catalog, na própria tabela de variantes, com dois contadores: `stock_on_hand` e `stock_reserved`.
Há restrições de banco contra saldo negativo e reserva acima do saldo. O ajuste manual (admin) exige um motivo e é
registrado em `stock_movements`. Ajustes concorrentes na mesma variante são serializados com `SELECT ... FOR UPDATE`,
então nenhum se perde e o saldo nunca fica negativo (coberto por teste de concorrência).

A loja mostra o tamanho como esgotado quando a quantidade disponível é zero. As operações `reserve`, `release` e
`commit`, usadas pela saga (ADR 0002), chegam na fatia 3.

Desvios em relação à spec, registrados aqui como consequência desta decisão:

- `products.min_price_cents` é uma coluna denormalizada, recalculada quando as variantes mudam, para filtrar e ordenar
  por preço com índice (ADR 0001).
- `PUT /v1/admin/storefront/settings` (configuração da vitrine) existe na API de admin, mas na fatia 1 só o seed o usa. A
  tela de edição da vitrine fica para a fatia 4. Até o primeiro PUT, o GET da configuração responde 404
  e a loja usa valores padrão.
- As fotos ficam em disco local, em um volume Docker (`CATALOG_MEDIA_ROOT`), servidas pelo próprio catalog em
  `/v1/media/...`. A spec cogitava um object store (MinIO), que não era necessário para o objetivo da fatia 1.

## Consequências

- Reservar estoque e mudar um preço acontecem no mesmo banco, em uma transação local, sem mensageria nem consistência
  eventual entre catálogo e estoque.
- O catalog acumula duas responsabilidades. Se o estoque crescer (depósitos, lotes, transferências), a extração para um
  serviço próprio exige migração de dados e de contrato.
- Os eventos `catalog.variant.stock_changed.v1` e `catalog.variant.price_changed.v1` (fatia 2) saem do mesmo serviço que
  muda os dados, o que simplifica o outbox.
- Disco local não serve para produção. O armazenamento fica atrás de uma porta, então um object store pode entrar
  depois sem mexer no domínio. O upload é idempotente e regrava o arquivo, então o seed recupera um volume de mídia
  recriado.

## Alternativas consideradas

- **Serviço de inventário separado:** isola o domínio, mas adiciona um serviço, outro banco e sincronização de SKUs,
  sem ganho visível na demo.
- **Estoque no orders:** o orders não é dono do SKU, e a vitrine precisaria consultar o orders para exibir esgotado.
- **MinIO desde já:** mais perto de produção, porém mais um container, credenciais e configuração para o mesmo
  resultado visível na demo.
