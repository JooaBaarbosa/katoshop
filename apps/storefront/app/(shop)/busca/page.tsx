import type { Metadata } from "next";
import { ProductListing } from "../../../components/product-listing";
import { parseFilters, type RawSearchParams } from "../../../lib/filters";

export const revalidate = 60;

export const metadata: Metadata = {
  title: "Busca",
  description: "Busque camisetas, moletons e calças na KatoShop, loja demonstrativa.",
  robots: { index: false, follow: true },
};

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const filters = parseFilters(await searchParams);
  return (
    <ProductListing
      scope={{}}
      filters={filters}
      action="/busca"
      header={
        filters.q ? (
          <>
            <h1 className="text-5xl">Busca</h1>
            <p className="text-sm text-ks-muted">
              Resultados para <span className="font-semibold text-ks-fg">“{filters.q}”</span>
            </p>
          </>
        ) : (
          <h1 className="text-5xl">Todas as peças</h1>
        )
      }
    />
  );
}
