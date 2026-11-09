import { cn } from "@katoshop/ui/cn";
import Link from "next/link";
import { type ProductDetail, sizeStates } from "../lib/pdp";
import { SizeGuideDialog } from "./size-guide-dialog";

const OPTION =
  "inline-flex h-10 min-w-12 items-center justify-center rounded-[var(--radius)] border px-3 text-sm font-semibold transition-colors duration-[var(--duration-fast)]";

/** Link do produto com a cor e o tamanho na URL (estado compartilhável e sem JS). */
function variantHref(slug: string, color: string, size: string | undefined) {
  return { pathname: `/p/${slug}`, query: size ? { cor: color, tamanho: size } : { cor: color } };
}

export function VariantPicker({
  detail,
  color,
  size,
}: {
  detail: ProductDetail;
  color: string;
  size: string | undefined;
}) {
  const selectedColor = detail.colors.find((c) => c.code === color);
  const sizes = sizeStates(detail, color).filter((s) => s.state !== "absent");
  const selectedSize = sizes.find((s) => s.code === size);

  return (
    <div className="space-y-6">
      <div role="group" aria-labelledby="pdp-cor">
        <p id="pdp-cor" className="mb-3 text-xs font-semibold uppercase tracking-wide text-ks-muted">
          Cor: <span className="text-ks-fg">{selectedColor?.name}</span>
        </p>
        <ul className="flex flex-wrap gap-2">
          {detail.colors.map((c) => {
            // mantém o tamanho ao trocar de cor só se ele estiver disponível na nova cor
            const keep = sizeStates(detail, c.code).some(
              (s) => s.code === size && s.state === "available",
            );
            const current = c.code === color;
            return (
              <li key={c.code}>
                <Link
                  href={variantHref(detail.slug, c.code, keep ? size : undefined)}
                  scroll={false}
                  replace
                  aria-label={c.name}
                  aria-current={current ? "true" : undefined}
                  title={c.name}
                  className={cn(
                    "block size-10 rounded-[var(--radius)] border-2 p-0.5 transition-colors duration-[var(--duration-fast)]",
                    current ? "border-ks-fg" : "border-transparent hover:border-ks-muted",
                  )}
                >
                  <span
                    aria-hidden
                    className="block size-full rounded-[var(--radius)] border border-ks-muted"
                    style={{ backgroundColor: c.hex }}
                  />
                </Link>
              </li>
            );
          })}
        </ul>
      </div>

      <div role="group" aria-labelledby="pdp-tamanho">
        <div className="mb-3 flex items-center justify-between gap-4">
          <p id="pdp-tamanho" className="text-xs font-semibold uppercase tracking-wide text-ks-muted">
            Tamanho
            {selectedSize && (
              <>
                : <span className="text-ks-fg">{selectedSize.label}</span>
              </>
            )}
          </p>
          <SizeGuideDialog categorySlug={detail.category.slug} />
        </div>
        <ul className="flex flex-wrap gap-2">
          {sizes.map((s) =>
            s.state === "sold_out" ? (
              <li key={s.code}>
                <button
                  type="button"
                  aria-disabled="true"
                  title={`${s.label} esgotado`}
                  className={cn(OPTION, "cursor-not-allowed border-ks-border text-ks-muted line-through")}
                >
                  {s.label}
                  <span className="sr-only"> esgotado</span>
                </button>
              </li>
            ) : (
              <li key={s.code}>
                <Link
                  href={variantHref(detail.slug, color, s.code)}
                  scroll={false}
                  replace
                  aria-current={s.code === size ? "true" : undefined}
                  className={cn(
                    OPTION,
                    s.code === size
                      ? "border-ks-fg bg-ks-fg text-ks-bg"
                      : "border-ks-muted text-ks-fg hover:border-ks-fg",
                  )}
                >
                  {s.label}
                </Link>
              </li>
            ),
          )}
        </ul>
      </div>
    </div>
  );
}
