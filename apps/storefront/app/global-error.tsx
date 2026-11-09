"use client";

import "./globals.css";

/** Último recurso: substitui o layout raiz, então traz o próprio html e body. */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="pt-BR">
      <body className="flex min-h-dvh flex-col items-start justify-center gap-6 bg-ks-bg px-4 py-16 text-ks-fg antialiased sm:px-16">
        <p className="font-mono text-sm font-bold uppercase tracking-widest">KATOSHOP</p>
        <h1 className="text-5xl">Algo deu errado</h1>
        <p className="text-sm text-ks-muted">Não foi possível carregar a loja agora.</p>
        {error.digest && (
          <p className="font-mono text-xs text-ks-muted">Código para suporte: {error.digest}</p>
        )}
        <button
          type="button"
          onClick={reset}
          className="h-10 rounded-[var(--radius)] bg-accent px-4 text-sm font-semibold uppercase tracking-wide text-ks-accent-fg"
        >
          Tentar de novo
        </button>
      </body>
    </html>
  );
}
