import { Button } from "@katoshop/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@katoshop/ui/dialog";
import { SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { type CatalogFilters, defaultSort, hasActiveFilters } from "../lib/filters";
import type { Facets } from "../lib/storefront";

type Props = {
  /** Caminho da listagem (o formulário faz GET nele). */
  action: string;
  filters: CatalogFilters;
  facets: Facets | null;
};

const CHECK =
  "size-4 shrink-0 rounded-[var(--radius)] accent-[var(--color-accent)]";

function reais(cents: number | null | undefined, round: (n: number) => number): string | undefined {
  return cents === null || cents === undefined ? undefined : String(round(cents / 100));
}

function FiltersForm({ action, filters, facets, idPrefix }: Props & { idPrefix: string }) {
  // Opção sem peças some, a menos que já esteja marcada (para poder desmarcar).
  const sizes = (facets?.sizes ?? []).filter((s) => s.count > 0 || filters.size.includes(s.code));
  const colors = (facets?.colors ?? []).filter(
    (c) => c.count > 0 || filters.color.includes(c.code),
  );
  const clearHref = filters.q ? `${action}?${new URLSearchParams({ q: filters.q })}` : action;
  return (
    <form action={action} className="space-y-8">
      {filters.q !== undefined && <input type="hidden" name="q" value={filters.q} />}
      {filters.sort !== defaultSort(filters.q) && (
        <input type="hidden" name="ordem" value={filters.sort} />
      )}

      <fieldset className="space-y-3">
        <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-ks-muted">
          Tamanho
        </legend>
        {sizes.length === 0 && <p className="text-sm text-ks-muted">Nenhum tamanho disponível.</p>}
        <ul className="grid grid-cols-3 gap-2">
          {sizes.map((size) => {
            const checked = filters.size.includes(size.code);
            const id = `${idPrefix}-tamanho-${size.code}`;
            return (
              <li key={size.code}>
                <label
                  htmlFor={id}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    id={id}
                    type="checkbox"
                    name="tamanho"
                    value={size.code}
                    defaultChecked={checked}
                    className={CHECK}
                  />
                  <span>{size.label}</span>
                  <span className="font-mono text-xs text-ks-muted">({size.count})</span>
                </label>
              </li>
            );
          })}
        </ul>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-ks-muted">
          Cor
        </legend>
        {colors.length === 0 && <p className="text-sm text-ks-muted">Nenhuma cor disponível.</p>}
        <ul className="space-y-2">
          {colors.map((color) => {
            const checked = filters.color.includes(color.code);
            const id = `${idPrefix}-cor-${color.code}`;
            return (
              <li key={color.code}>
                <label
                  htmlFor={id}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    id={id}
                    type="checkbox"
                    name="cor"
                    value={color.code}
                    defaultChecked={checked}
                    className={CHECK}
                  />
                  <span
                    aria-hidden
                    className="size-4 rounded-[var(--radius)] border border-ks-muted"
                    style={{ backgroundColor: color.hex }}
                  />
                  <span>{color.name}</span>
                  <span className="font-mono text-xs text-ks-muted">({color.count})</span>
                </label>
              </li>
            );
          })}
        </ul>
      </fieldset>

      <fieldset>
        <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-ks-muted">
          Preço (R$)
        </legend>
        <div className="flex items-end gap-3">
          <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm" htmlFor={`${idPrefix}-preco-min`}>
            Mínimo
            <input
              id={`${idPrefix}-preco-min`}
              type="number"
              name="preco_min"
              min={0}
              step={1}
              inputMode="numeric"
              defaultValue={reais(filters.priceMin, Math.floor)}
              placeholder={reais(facets?.price.min, Math.floor)}
              className="h-10 w-full rounded-[var(--radius)] border border-ks-muted bg-ks-surface px-3 font-mono text-sm text-ks-fg placeholder:text-ks-muted"
            />
          </label>
          <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm" htmlFor={`${idPrefix}-preco-max`}>
            Máximo
            <input
              id={`${idPrefix}-preco-max`}
              type="number"
              name="preco_max"
              min={0}
              step={1}
              inputMode="numeric"
              defaultValue={reais(filters.priceMax, Math.floor)}
              placeholder={reais(facets?.price.max, Math.ceil)}
              className="h-10 w-full rounded-[var(--radius)] border border-ks-muted bg-ks-surface px-3 font-mono text-sm text-ks-fg placeholder:text-ks-muted"
            />
          </label>
        </div>
      </fieldset>

      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit">Aplicar filtros</Button>
        {hasActiveFilters(filters) && (
          <Link href={clearHref} className="text-sm font-semibold underline underline-offset-4">
            Limpar filtros
          </Link>
        )}
      </div>
    </form>
  );
}

/** Filtros da listagem: coluna fixa a partir de 1024px e diálogo "Filtrar" abaixo disso. */
export function FiltersPanel(props: Props) {
  const active =
    props.filters.size.length +
    props.filters.color.length +
    (props.filters.priceMin !== undefined || props.filters.priceMax !== undefined ? 1 : 0);
  return (
    <>
      <aside aria-label="Filtros" className="hidden lg:block">
        <div className="sticky top-6">
          <FiltersForm {...props} idPrefix="filtro" />
        </div>
      </aside>
      <div className="lg:hidden">
        <Dialog>
          <DialogTrigger asChild>
            <Button type="button" variant="secondary">
              <SlidersHorizontal aria-hidden className="size-4" />
              Filtrar
              {active > 0 && <span className="font-mono">({active})</span>}
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90dvh] w-[calc(100%-2rem)] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Filtrar</DialogTitle>
              <DialogDescription>Escolha tamanho, cor e faixa de preço.</DialogDescription>
            </DialogHeader>
            <FiltersForm {...props} idPrefix="filtro-mobile" />
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
}
