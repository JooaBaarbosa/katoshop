# ADR 0006: Cada serviço valida o JWT

## Contexto

Os serviços ficam atrás de um gateway (Traefik), mas precisam de autorização própria: o catalog decide se quem chama
pode escrever, e o identity decide quem é o usuário. Confiar só no gateway tornaria um serviço alcançável pela rede
interna uma porta aberta, e o Traefik não conhece permissões de domínio.

## Decisão

O identity emite access tokens JWT assinados com EdDSA (Ed25519), com `iss = katoshop-identity`, `aud` igual a
`storefront` ou `admin`, claims `sub`, `exp`, `iat`, `jti`, `roles` e `kind` (`customer` ou `staff`), header `kid` e
validade de 900 s. As chaves públicas ficam em `/.well-known/jwks.json`. Cada serviço verifica o token sozinho, com a
lib `ks_platform`: baixa o JWKS do identity, guarda em cache e usa as dependências `current_principal` e
`require_permission`. A chave privada só existe no identity, como secret de arquivo.

Códigos de resposta (R1, R9, R25):

| Situação | Status | Código |
|---|---|---|
| Sem token | 401 | `auth.missing_token` |
| Assinatura inválida, expirado ou `kid` desconhecido | 401 | `auth.invalid_token` |
| Token válido, mas `aud` diferente da exigida (cliente no admin) | 403 | `auth.forbidden` |
| Audiência correta, mas sem a permissão exigida | 403 | `auth.insufficient_permission` |
| Falha ao buscar o JWKS com cache vazio | 503 | `auth.jwks_unavailable` |

O 403 de audiência errada é o que a spec pede no critério de aceite 5: o usuário está autenticado, só não pode estar
ali. O papel `admin` concede `*`, e a escrita no catálogo exige `catalog.write`. O 503 distingue falha do servidor de
falha do cliente: um 401 empurraria os clientes a renovar o token e a deslogar sem necessidade.

Cache do JWKS (R9): enquanto há chaves em cache, elas continuam em uso mesmo com o identity fora do ar. Falhas de busca
têm backoff e um intervalo mínimo entre tentativas, para que um identity fora do ar não receba uma rajada de buscas
nem serialize as requisições.

## Consequências

- Um serviço continua correto mesmo que alguém o alcance sem passar pelo gateway.
- Chaves e algoritmo ficam em um lugar só (`ks_platform`), mas os serviços dependem do identity na primeira subida,
  para buscar as chaves.
- Não há revogação imediata do access token: ele vale até expirar (900 s). A revogação vale para refresh tokens
  (ADR 0005).
- Rotacionar a chave exige mais de uma chave ativa no JWKS e aceitar a antiga até os tokens expirarem. A rotação
  fica fora da fatia 1.
- O JWT carrega `roles`, então uma mudança de papel só vale no próximo token.
- Não há tolerância (leeway) para diferença de relógio no `iat`. No desenvolvimento local, no mesmo host, isso não
  aparece.

## Alternativas consideradas

- **Validação só no gateway (forward auth):** um ponto único de falha e de configuração, sem autorização por domínio
  nos serviços.
- **Introspecção de token em cada chamada:** revogação imediata, mas acopla cada requisição à disponibilidade do
  identity.
- **Tokens opacos com sessão no identity:** mesmo problema da introspecção.
- **HS256 com segredo compartilhado:** qualquer serviço poderia forjar tokens. Com EdDSA só o identity assina.
