import type { CatalogComponents } from "@katoshop/api-client";
import { formatBRL } from "@katoshop/ui/money";
import Image from "next/image";
import Link from "next/link";

export type ProductCardData = CatalogComponents["schemas"]["ProductCardOut"];

const CARD_SIZES = "(min-width: 1024px) 25vw, (min-width: 640px) 33vw, 50vw";

export function ProductCard({ product }: { product: ProductCardData }) {
  return (
    <article className="relative flex flex-col gap-3 rounded-[var(--radius)] has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-offset-4 has-[a:focus-visible]:outline-ks-focus">
      <div className="relative aspect-[4/5] overflow-hidden rounded-[var(--radius)] bg-ks-surface">
        {product.image ? (
          <Image
            src={product.image.url}
            alt={product.image.alt}
            fill
            sizes={CARD_SIZES}
            className="object-cover"
          />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center text-xs uppercase tracking-wide text-ks-muted">
            Sem foto
          </span>
        )}
        {product.sold_out && (
          <span className="absolute left-2 top-2 rounded-[var(--radius)] bg-ks-bg px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-ks-fg">
            Esgotado
          </span>
        )}
      </div>
      <div className="flex flex-col gap-1">
        <h3 className="font-sans text-sm font-semibold normal-case">
          <Link
            href={`/p/${product.slug}`}
            className="after:absolute after:inset-0 hover:underline focus-visible:outline-none"
          >
            {product.name}
          </Link>
        </h3>
        <p className="font-mono text-sm text-accent">{formatBRL(product.min_price_cents)}</p>
        {product.colors.length > 0 && (
          <ul aria-label="Cores" className="flex flex-wrap gap-1.5 pt-1">
            {product.colors.map((color) => (
              <li key={color.code}>
                <span
                  role="img"
                  aria-label={color.name}
                  title={color.name}
                  className="block size-3 rounded-[var(--radius)] border border-ks-muted"
                  style={{ backgroundColor: color.hex }}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
