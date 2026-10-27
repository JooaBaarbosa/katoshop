import type { ReactNode } from "react";
import { SiteFooter } from "../../components/site-footer";
import { SiteHeader } from "../../components/site-header";
import { navCategories, storePolicies } from "../../lib/storefront";

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
