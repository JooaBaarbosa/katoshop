# @katoshop/ui

Design system SARJETA compartilhado pelas apps Next.js (consumo direto do código TS via `transpilePackages`).

## Uso nas apps

- Fontes: em `app/layout.tsx`, coloque `${anton.variable} ${inter.variable} ${jetbrainsMono.variable}` (de `@katoshop/ui/fonts`) na `className` do `<html>`. Os utilitários `font-display`, `font-sans` e `font-mono` passam a usar as fontes auto-hospedadas.
- CSS: importe `@katoshop/ui/styles/globals-store.css` (loja, escura) ou `@katoshop/ui/styles/globals-admin.css` (admin, clara). Adicione `@source` apontando para o código da própria app.
- Tema: a loja é o padrão. O admin precisa de `data-theme="admin"` no `<html>`; os componentes usam tokens semânticos (`text-ks-fg`, `bg-ks-surface`, `outline-ks-focus`...) que trocam de valor nesse contexto.
- Requer `tailwindcss` 4.3.3 na app.
