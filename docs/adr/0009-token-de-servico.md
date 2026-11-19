# ADR 0009: Token de serviço por client credentials

## Contexto

Na fatia 2 aparecem as primeiras chamadas de serviço para serviço. O cart lê a variante no catalog
(`GET /v1/internal/variants/{variant_id}`) ao adicionar um item e pede ao promotions o cálculo do cupom
(`POST /v1/promotions/evaluate`). Essas rotas não pertencem a nenhum cliente nem funcionário: só um serviço da
plataforma pode chamá-las. O [ADR 0006](0006-validacao-jwt-por-servico.md) já decidiu que nenhuma rota confia só na
rede, então essas rotas precisam de uma credencial própria.

## Decisão

### Emissão

O identity expõe `POST /v1/auth/service-token` com `{client_id, client_secret}` (fluxo *client credentials*). Os
clientes e segredos vêm do env do identity, em `IDENTITY_SERVICE_CLIENTS` (um JSON `{"cart": "<segredo>"}`); nesta
fatia o único cliente é o `cart`, que recebe o mesmo segredo em `CART_CLIENT_SECRET`. O identity recusa subir com um
segredo de menos de 32 caracteres. A comparação é em tempo constante (`hmac.compare_digest` sobre o SHA-256 dos dois
valores), e um `client_id` desconhecido também passa por uma comparação, para não revelar pelo tempo quais clientes
existem. Credencial errada responde 401 `identity.service.invalid_client`.

O token é um JWT EdDSA assinado com a mesma chave dos outros tokens, com `aud="service"`, `kind="service"`,
`sub=<client_id>`, `roles=[]` e validade de 300 s.

### Uso e validação

- O cart guarda o token em memória e renova 30 s antes de expirar (`ks_platform.service_tokens`). Um 401 de uma rota
  interna força a renovação e uma nova tentativa.
- O catalog (rota interna de variante) e o promotions (evaluate) exigem a audiência `service`. Na `ks_platform`, o
  chamador vira um `ServicePrincipal(client_id)`, separado do `Principal` de cliente e funcionário (ruling S1): o `sub`
  de usuário continua sendo UUID e um token de serviço nunca passa por uma checagem de permissão de usuário.
- Sem token: 401. Token de cliente ou de funcionário numa rota de serviço: 403. Token de serviço numa rota de usuário:
  403. São os códigos do ADR 0006.

### Rotas internas fora do gateway

Além do token, o Traefik não publica as rotas internas. O router `internal-block`, com prioridade acima de todos,
responde 404 sem corpo e sem chegar ao serviço para:

- `/catalog/v1/internal/...`;
- `/identity/v1/auth/service-token`;
- `/promotions/v1/promotions/...` (o evaluate). Do promotions, só `/promotions/v1/admin/...` é roteado.

O cart não tem rota interna. Dentro do compose os serviços se chamam pelo nome (`http://catalog:8000`), sem passar
pelo gateway.

Toda regra com prefixo usa `PathRegexp` ancorado em fronteira de segmento (`^/catalog(/|$)`). Durante a fatia 2 foi
encontrado (e corrigido também na fatia 1, num hotfix na `main`) que o `PathPrefix` do Traefik é prefixo de texto:
`PathPrefix(/catalog)` casava com `/catalogv1/internal/...`, o `stripPrefix` entregava `/v1/internal/...` ao serviço, e
a requisição escapava dos routers de bloqueio e de limite de taxa. Pelo mesmo motivo o entrypoint `web` recusa `%2F` e
`%5C` no caminho (`encodedCharacters` com `allowEncodedSlash` e `allowEncodedBackSlash` falsos): o router compara o
caminho ainda codificado, mas o uvicorn decodifica, então `/identity/v1/auth%2Flogin` chegava ao login sem o limite de
taxa. O teste e2e `gateway.spec.ts` cobre esses casos contra a pilha no ar.

### Geração do segredo

Os valores do `.env.example` servem só para desenvolvimento local. Fora dele, cada segredo é gerado com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

e o mesmo valor vai em `IDENTITY_SERVICE_CLIENTS` e na variável do serviço cliente.

## Consequências

- Uma rota interna continua protegida mesmo que alguém alcance o serviço pela rede do compose, e o bloqueio no gateway
  é uma segunda barreira, não a única.
- A validação reaproveita o JWKS e a lib dos outros tokens: nenhum serviço novo de autenticação.
- O token não é revogável antes de expirar, como os access tokens (ADR 0006), mas a validade curta (300 s) limita a
  janela de um token vazado.
- Trocar um segredo exige reiniciar o identity e o serviço cliente com o valor novo. Não há rotação sem parada nesta
  fatia.
- Os segredos ficam como texto no env, sem cofre de segredos. Aceito para a demo local.
- O cart passa a depender do identity para chamar catalog e promotions. Com o identity fora, o token em cache vale até
  expirar; depois disso adicionar item falha e o cupom aparece como indisponível.

## Alternativas consideradas

- **Confiar na rede interna (rota sem autenticação, só fora do gateway):** mais simples, mas qualquer container ou
  processo na rede do compose chamaria as rotas, e um erro de roteamento no gateway (como o do `PathPrefix`) as
  exporia sem nenhuma barreira. Contraria o ADR 0006.
- **Chave de API estática por serviço, conferida em cada serviço chamado:** cada serviço chamado teria de conhecer os
  segredos de todos os chamadores, e o segredo trafegaria em toda requisição.
- **mTLS entre serviços:** identidade forte no transporte, mas exige uma CA, emissão e rotação de certificados e mais
  configuração em cada container. Desproporcional para a demo local.
- **Reutilizar o token do usuário (repassar o token do cliente):** o visitante não tem token, e o cálculo do cupom não
  é uma ação em nome de um usuário específico.
