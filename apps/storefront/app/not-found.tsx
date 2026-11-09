import { Button } from "@katoshop/ui/button";
import type { Metadata } from "next";
import Link from "next/link";
import { BrandMessage } from "../components/brand-message";

export const metadata: Metadata = { title: "Página não encontrada" };

export default function NotFound() {
  return (
    <main id="conteudo">
      <BrandMessage
        title="Página não encontrada"
        actions={
          <Button asChild>
            <Link href="/">Voltar para a loja</Link>
          </Button>
        }
      >
        <p>O endereço não existe ou o produto saiu de linha.</p>
      </BrandMessage>
    </main>
  );
}
