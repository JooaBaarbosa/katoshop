import { Button } from "@katoshop/ui/button";
import { Logo } from "@katoshop/ui/logo";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Página não encontrada" };

export default function NotFound() {
  return (
    <main
      id="conteudo"
      className="flex min-h-dvh flex-col items-start justify-center gap-6 px-4 py-16 sm:px-16"
    >
      <Logo tone="light" aria-label="KatoShop" />
      <h1 className="text-4xl sm:text-5xl">Página não encontrada</h1>
      <p className="max-w-prose text-sm text-ks-muted">
        O endereço não existe ou o item foi excluído do catálogo.
      </p>
      <Button asChild>
        <Link href="/">Ir para a visão geral</Link>
      </Button>
    </main>
  );
}
