import { Button } from "@katoshop/ui/button";
import { ChevronDown } from "lucide-react";
import type { Sort } from "../lib/filters";

const LABELS: Record<Sort, string> = {
  relevance: "Relevância",
  newest: "Novidades",
  price_asc: "Menor preço",
  price_desc: "Maior preço",
};

/**
 * Ordenação por formulário GET com botão "Ordenar" visível. Não envia no `change`: navegar
 * pelas opções com as setas do teclado não pode mudar de página (WCAG 3.2.2).
 * `hidden` leva os demais filtros da URL, já normalizados.
 */
export function SortSelect({
  action,
  value,
  hidden,
  withRelevance,
}: {
  action: string;
  value: Sort;
  hidden: [string, string][];
  withRelevance: boolean;
}) {
  const options = (Object.keys(LABELS) as Sort[]).filter(
    (sort) => withRelevance || sort !== "relevance",
  );
  return (
    <form action={action} className="flex items-center gap-2">
      {hidden.map(([name, val], index) => (
        <input key={`${name}-${val}-${index}`} type="hidden" name={name} value={val} />
      ))}
      <label htmlFor="ordem" className="text-sm text-ks-muted">
        Ordenar por
      </label>
      <div className="relative">
        <select
          id="ordem"
          name="ordem"
          defaultValue={value}
          className="h-10 appearance-none rounded-[var(--radius)] border border-ks-muted bg-ks-surface pl-3 pr-9 text-sm text-ks-fg"
        >
          {options.map((sort) => (
            <option key={sort} value={sort}>
              {LABELS[sort]}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden
          className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-ks-muted"
        />
      </div>
      <Button type="submit" variant="secondary">
        Ordenar
      </Button>
    </form>
  );
}
