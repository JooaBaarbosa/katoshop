"use client";

import { Button } from "@katoshop/ui/button";
import Link from "next/link";
import { BrandMessage } from "../components/brand-message";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main id="conteudo">
      <BrandMessage
        title="Algo deu errado"
        actions={
          <>
            <Button type="button" onClick={reset}>
              Tentar de novo
            </Button>
            <Button asChild variant="secondary">
              <Link href="/">Voltar para a loja</Link>
            </Button>
          </>
        }
      >
        <p>Não foi possível carregar esta página agora. Tente de novo em instantes.</p>
        {error.digest && <p className="font-mono text-xs">Código para suporte: {error.digest}</p>}
      </BrandMessage>
    </main>
  );
}
