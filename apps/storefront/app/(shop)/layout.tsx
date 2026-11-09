import type { ReactNode } from "react";
import { SiteFooter } from "../../components/site-footer";
import { SiteHeader } from "../../components/site-header";
import { navCategories, storePolicies } from "../../lib/storefront";

// Ruling R21: header e rodapé usam dados do catálogo; nenhuma página da loja é pré-renderizada
// no build (o catálogo não está acessível lá). O cache de 60 s fica em cada fetch.
export const dynamic = "force-dynamic";

export default async function ShopLayout({ children }: { children: ReactNode }) {
  const [categories, policies] = await Promise.all([navCategories(), storePolicies()]);
  return (
    <>
      <SiteHeader categories={categories} />
      <main id="conteudo" className="mx-auto w-full max-w-7xl flex-1 px-4 py-10">
        {children}
      </main>
      <SiteFooter policies={policies} />
    </>
  );
}
