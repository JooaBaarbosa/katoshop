"use client";

import { Button } from "@katoshop/ui/button";
import { LoaderCircle } from "lucide-react";
import { useState, useTransition } from "react";
import { loadMoreProducts } from "../app/(shop)/catalog-actions";
import type { ListingScope } from "../lib/storefront";
import type { ProductCardData } from "./product-card";
import { ProductGrid } from "./product-grid";

/** Grade da listagem com "Carregar mais" pelo `next_cursor` da API. */
export function LoadMore({
  scope,
  search,
  initialProducts,
  initialCursor,
}: {
  scope: ListingScope;
  /** Filtros da loja já normalizados (`toSearchParams`). */
  search: string;
  initialProducts: ProductCardData[];
  initialCursor: string | null;
}) {
  const [products, setProducts] = useState(initialProducts);
  const [cursor, setCursor] = useState(initialCursor);
  const [status, setStatus] = useState("");
  const [failed, setFailed] = useState(false);
  const [pending, startTransition] = useTransition();

  function loadMore() {
    if (!cursor) return;
    startTransition(async () => {
      const page = await loadMoreProducts(scope, search, cursor);
      if (!page) {
        setFailed(true);
        setStatus("Não foi possível carregar mais peças. Tente de novo.");
        return;
      }
      const known = new Set(products.map((product) => product.slug));
      const fresh = page.items.filter((item) => !known.has(item.slug));
      setFailed(false);
      setProducts((current) => [...current, ...fresh]);
      setCursor(page.next_cursor);
      setStatus(
        fresh.length === 1 ? "1 peça carregada." : `${fresh.length} peças carregadas.`,
      );
    });
  }

  return (
    <div className="space-y-10">
      <ProductGrid products={products} className="lg:grid-cols-3" />
      <p role="status" className={failed ? "text-sm text-ks-fg" : "sr-only"}>
        {status}
      </p>
      {cursor && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="secondary"
            onClick={loadMore}
            disabled={pending}
            aria-busy={pending}
          >
            {pending && <LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />}
            Carregar mais
          </Button>
        </div>
      )}
    </div>
  );
}
