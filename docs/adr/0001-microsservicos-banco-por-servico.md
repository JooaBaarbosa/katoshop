# ADR 0001: Microsserviços com um banco por serviço

## Contexto

O KatoShop é um projeto de portfólio de arquitetura (spec seção 1). Ele precisa mostrar fronteiras claras entre
domínios, comunicação entre serviços e observabilidade ponta a ponta. Ao mesmo tempo, roda só localmente, em Docker
Compose, na máquina de quem avalia o projeto. Os domínios previstos são identity, catalog, cart, promotions, orders,
payments e shipping, e cada um tem ciclo de vida e regras próprias.

## Decisão

Sete microsserviços completos, cada um com o seu próprio banco Postgres e o seu próprio usuário de banco. O usuário de
um serviço só tem permissão no banco desse serviço; `infra/postgres-init/01-databases.sh` cria os bancos e os usuários
na primeira subida do volume. Nenhum serviço lê ou escreve no banco de outro. Dados de outro domínio chegam por REST
(leituras, com timeout curto) ou por eventos (mudanças de estado, a partir da fatia 2).

Um único cluster Postgres atende os bancos em desenvolvimento, para manter o consumo de memória baixo. A separação é
lógica e de permissões, não de instância. Na fatia 1 existem dois serviços: identity e catalog.

Os serviços compartilham apenas a lib `ks_platform` (settings, observabilidade, verificação de JWT, problem+json,
helpers de banco e de teste). Ela não contém regra de negócio de nenhum domínio.

## Consequências

- Cada serviço migra o seu esquema com Alembic de forma independente e pode ser testado contra um Postgres próprio
  (testcontainers), sem fixtures de outros domínios.
- Não há joins entre domínios. O catalog guarda cópias denormalizadas do que precisa para consultar bem, por exemplo
  `products.min_price_cents` (menor preço entre as variantes) e o nome da categoria usado na busca. Esse é um desvio
  consciente da forma normalizada, feito para que filtro por faixa de preço e ordenação por preço usem índice com
  paginação por cursor.
- Consistência entre serviços passa a ser eventual (fatias 2 e 3), com outbox, consumidores idempotentes e saga.
- O custo operacional é maior que o de um monólito: mais imagens, mais health checks, mais configuração. É o
  propósito do projeto, mas não seria a escolha padrão para uma loja real do mesmo tamanho.
- O init do Postgres só roda em volume novo. Mudar senhas de banco no `.env` depois da primeira subida exige recriar o
  volume.

## Alternativas consideradas

- **Monólito modular:** menos código de infraestrutura e transações locais, mas não demonstra fronteiras de serviço,
  mensageria nem tracing distribuído, que são o objetivo do projeto.
- **Um banco compartilhado com schemas por serviço:** mais simples, porém a fronteira passa a ser só convenção e é fácil
  quebrá-la com um join. O usuário por banco torna a regra verificável.
- **Um cluster Postgres por serviço:** isolamento maior, mas sete instâncias pesam demais numa máquina de
  desenvolvimento.
