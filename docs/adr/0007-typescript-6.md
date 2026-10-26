# ADR 0007: TypeScript 6.0.3 no workspace

## Contexto

A regra do projeto é usar a versão estável mais recente de cada tecnologia. O TypeScript 7.0.2 (compilador nativo) é a
estável mais nova, mas a API de compilador em JavaScript mudou. Em 2026-10-26, com o TypeScript 7.0.2:

- `openapi-typescript` 7.13.0 (gerador dos tipos do contrato OpenAPI) quebra ao iniciar com
  `TypeError: Cannot read properties of undefined (reading 'createKeywordTypeNode')`.
- `typescript-eslint` 8.72.1 declara o peer `typescript >=4.8.4 <6.1.0`, então não oferece lint tipado com a versão 7.

## Decisão

Fixar o TypeScript em 6.0.3 (última 6.x estável) em todo o workspace (`packages/config` e `packages/api-client`),
conforme o Ruling R7. Com a 6.0.3, `openapi-typescript` gera os tipos e o `typecheck` passa. O único aviso é o de peer
do `openapi-typescript` (`unmet peer typescript: wanted ^5.x, installed 6.0.3`), aceito porque o funcionamento foi
verificado. O lint tipado volta com `typescript-eslint` (`recommendedTypeChecked`) na base em `packages/config`.

## Consequências

- Sem os ganhos de velocidade do compilador nativo do TypeScript 7.
- Um aviso de peer persiste no `pnpm install` até o `openapi-typescript` ampliar o range.
- Revisar esta decisão quando `openapi-typescript` e `typescript-eslint` suportarem o TypeScript 7.

## Alternativas

- Manter o TypeScript 7.0.2 e usar um TypeScript 5 isolado só para o gerador: duas versões no repositório e lint tipado
  ainda indisponível.
- Fixar o TypeScript 5.9.3: funciona, mas fica atrás da 6.x sem necessidade, já que a 6.0.3 funcionou.
