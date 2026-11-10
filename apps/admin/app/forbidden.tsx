import { Button } from "@katoshop/ui/button";
import { Logo } from "@katoshop/ui/logo";
import type { Metadata } from "next";
import Link from "next/link";
import { logoutAction } from "./(painel)/actions";
import { READ_FORBIDDEN } from "../lib/forbidden";

export const metadata: Metadata = { title: "Sem permissão" };

/** forbidden() de uma leitura: conta da equipe sem a permissão desta área (R25). */
export default function Forbidden() {
  return (
    <main
      id="conteudo"
      className="flex min-h-dvh flex-col items-start justify-center gap-6 px-4 py-16 sm:px-16"
    >
      <Logo tone="light" aria-label="KatoShop" />
      <h1 className="text-4xl sm:text-5xl">Sem permissão</h1>
      <p className="max-w-prose text-sm text-ks-muted">
        {READ_FORBIDDEN} Peça acesso a uma pessoa administradora ou entre com outra conta.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button asChild variant="secondary">
          <Link href="/">Ir para a visão geral</Link>
        </Button>
        <form action={logoutAction}>
          <Button type="submit">Entrar com outra conta</Button>
        </form>
      </div>
    </main>
  );
}
