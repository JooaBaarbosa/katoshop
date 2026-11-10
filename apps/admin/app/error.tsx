"use client";

import { Button } from "@katoshop/ui/button";
import { Logo } from "@katoshop/ui/logo";
import Link from "next/link";

/** Falha ao carregar uma página do painel (API fora, erro inesperado). */
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main
      id="conteudo"
      className="flex min-h-dvh flex-col items-start justify-center gap-6 px-4 py-16 sm:px-16"
    >
      <Logo tone="light" aria-label="KatoShop" />
      <h1 className="text-4xl sm:text-5xl">Algo deu errado</h1>
      <p className="max-w-prose text-sm text-ks-muted">
        Não foi possível carregar esta página do painel agora. Tente de novo em instantes.
      </p>
      {error.digest && (
        <p className="font-mono text-xs text-ks-muted">Código para suporte: {error.digest}</p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="button" onClick={reset}>
          Tentar de novo
        </Button>
        <Button asChild variant="secondary">
          <Link href="/">Ir para a visão geral</Link>
        </Button>
      </div>
    </main>
  );
}
