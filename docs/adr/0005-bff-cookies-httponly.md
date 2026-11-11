# ADR 0005: BFF com cookies httpOnly

## Contexto

A loja e o admin são apps Next.js que consomem os serviços pelo gateway. Tokens guardados em `localStorage` ficam
expostos a qualquer script injetado (XSS). O projeto também precisa de duas audiências separadas (`storefront` e `admin`)
e de um cliente que sobreviva a abas concorrentes renovando o mesmo refresh token.

## Decisão

O navegador só fala com o Next. As chamadas ao gateway saem do servidor (Server Components, Server Actions e Route
Handlers) com `Authorization: Bearer`. Os tokens ficam em cookies `httpOnly`, `SameSite=Lax`, `Path=/`, no próprio
domínio de cada app, com `Secure` ativado por `COOKIE_SECURE` (desligado no desenvolvimento local em HTTP).

- **Cookies por app:** `ks_at` e `ks_rt` na loja, `ka_at` e `ka_rt` no admin (access token de 900 s e refresh token
  opaco e rotativo). Cada app tem o seu prefixo, e a sessão de uma não vale na outra.
- **Renovação só onde cookies são graváveis (R18).** O Next 16 proíbe escrever cookies em Server Components. Por isso a
  renovação acontece no `proxy.ts` de cada app (`refreshInProxy`, que grava os cookies na resposta e na requisição
  encaminhada) e, opcionalmente, em Server Actions e Route Handlers. Em Server Components, um 401 não renova: lança
  erro e a página redireciona ao login. O identity aceita o reuso do refresh token dentro de 10 s do primeiro uso e
  emite um novo par na mesma família sem revogar, para que requisições simultâneas não derrubem a sessão. Depois dessa
  janela, o reuso revoga a família inteira.
- **CSRF:** `SameSite=Lax` mais a checagem de origem das Server Actions do Next. No admin, a rota `GET /sair`
  valida `Sec-Fetch-Site`.
- **Rate limit por cliente (R20, R24):** como o identity só enxerga o IP do container do Next, o limite por IP do
  gateway virou um balde global. O Traefik aplica 10 req/s (rajada 20) por IP de cliente nos POSTs de `/entrar` e
  `/criar-conta` e em todo POST com cabeçalho `Next-Action`, nas duas apps.
- O admin tem um guarda que exige a audiência `admin` e a permissão `catalog.write`, decidido pelos códigos de erro da
  API (`auth.forbidden` e `auth.insufficient_permission`, ver ADR 0006).

## Consequências

- Tokens inacessíveis ao JavaScript do navegador reduzem o dano de um XSS. Um XSS ainda pode agir como o usuário
  enquanto a sessão existir.
- Toda chamada autenticada passa pelo servidor do Next, o que acrescenta um salto, e o tracing mostra os spans do Next
  antes do gateway.
- As apps precisam conectar o `proxy.ts` e passar uma `NextResponse.next()` simples ao helper de renovação. É uma
  regra fácil de esquecer, por isso fica coberta por testes.
- Durante uma queda do identity, o proxy segue sem renovar e as páginas autenticadas redirecionam ao login.
- Cookies não servem a clientes de API de terceiros. Não é um requisito do projeto.
- Sem JavaScript, o formulário posta o id da action no corpo e sem o cabeçalho `Next-Action`. Esse caso depende do
  limite por caminho (`/entrar`, `/criar-conta`) e do limite do identity como retaguarda.

## Alternativas consideradas

- **Token em `localStorage` e SPA chamando a API:** simples, mas legível por qualquer XSS.
- **Sessão no servidor (id de sessão em cookie e Redis):** dispensa JWT no navegador, mas obriga o Next a manter estado
  e perde o encaixe com os serviços que já validam JWT (ADR 0006).
- **Renovar tokens em Server Components:** não é possível gravar cookies ali no Next 16, e a rotação do refresh
  consumiria o token sem entregar o novo ao navegador.
