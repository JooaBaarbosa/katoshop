import type { ReactNode } from "react";
import { type CatalogFilters, toSearchParams } from "../lib/filters";
import { type ListingScope, listProducts, productFacets } from "../lib/storefront";
import { FiltersPanel } from "./filters-panel";
import { LoadMore } from "./load-more";
import { SortSelect } from "./sort-select";

/** Listagem com filtros, ordenação e "Carregar mais"; usada por categoria, coleção e busca. */
export async function ProductListing({
  scope,
  filters,
  action,
  header,
}: {
  scope: ListingScope;
  filters: CatalogFilters;
  /** Caminho da página, destino dos formulários GET. */
  action: string;
  header: ReactNode;
}) {
  const [result, facets] = await Promise.all([
    listProducts(scope, filters),
    productFacets(scope, filters),
  ]);
  const search = toSearchParams(filters);
  const hiddenForSort = [...search].filter(([name]) => name !== "ordem");

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">{header}</div>
        <div className="flex flex-wrap items-center gap-3">
          <SortSelect
            key={filters.sort}
            action={action}
            value={filters.sort}
            hidden={hiddenForSort}
            withRelevance={filters.q !== undefined || filters.sort === "relevance"}
          />
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[16rem_1fr]">
        <FiltersPanel key={search.toString()} action={action} filters={filters} facets={facets} />

        <section aria-label="Produtos">
          {!result.ok && result.reason === "invalid" && (
            <p role="alert" className="rounded-[var(--radius)] border border-ks-border p-4 text-sm">
              Filtro inválido. Revise os filtros ou limpe a busca para ver as peças.
            </p>
          )}
          {!result.ok && result.reason !== "invalid" && (
            <p role="alert" className="rounded-[var(--radius)] border border-ks-border p-4 text-sm">
              Não foi possível carregar as peças agora. Tente de novo em instantes.
            </p>
          )}
          {result.ok && result.data.items.length === 0 && (
            <p className="text-sm text-ks-muted">Nenhuma peça encontrada com esses filtros.</p>
          )}
          {result.ok && result.data.items.length > 0 && (
            <LoadMore
              key={search.toString()}
              scope={scope}
              search={search.toString()}
              initialProducts={result.data.items}
              initialCursor={result.data.next_cursor}
            />
          )}
        </section>
      </div>
    </div>
  );
}
