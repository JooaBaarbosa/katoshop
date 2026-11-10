"use client";

import { Button } from "@katoshop/ui/button";
import { Plus, X } from "lucide-react";
import { useState, useTransition } from "react";
import { ReorderList } from "../../../components/reorder-list";
import type { AdminProductRow } from "../../../lib/catalog-data";
import { STATUS_LABELS } from "../../../lib/catalog-input";
import { setCollectionProductsAction } from "./actions";

type Item = Pick<AdminProductRow, "id" | "name" | "status">;

/** Produtos da coleção na ordem da loja: adicionar, remover e reordenar, gravando com PUT. */
export function CollectionProducts({
  collectionId,
  productIds,
  products,
}: {
  collectionId: string;
  productIds: string[];
  products: AdminProductRow[];
}) {
  const byId = new Map(products.map((product) => [product.id, product]));
  const toItems = (ids: string[]): Item[] =>
    ids.map((id) => byId.get(id) ?? { id, name: `Produto ${id.slice(-6)}`, status: "draft" });
  const [items, setItems] = useState(() => toItems(productIds));
  const [source, setSource] = useState(productIds);
  // a lista gravada volta pelas props depois da revalidação
  if (source !== productIds) {
    setSource(productIds);
    setItems(toItems(productIds));
  }
  const [adding, setAdding] = useState("");
  const [saving, startSaving] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function save(next: Item[]) {
    const previous = items;
    setItems(next);
    setError(null);
    setNotice(null);
    startSaving(async () => {
      const result = await setCollectionProductsAction(
        collectionId,
        next.map((item) => item.id),
      );
      if (result.ok) setNotice("Ordem da coleção salva.");
      else {
        setItems(previous);
        setError(result.error);
      }
    });
  }

  const inCollection = new Set(items.map((item) => item.id));
  const available = products.filter((product) => !inCollection.has(product.id));

  return (
    <section aria-labelledby="produtos-colecao" className="space-y-4">
      <h2 id="produtos-colecao" className="text-xl">
        Produtos da coleção
      </h2>
      <p className="text-sm text-ks-muted">
        A loja mostra só os produtos ativos, nesta ordem. Arraste ou use os botões para mover.
      </p>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      <p role="status" className="text-sm text-ks-muted">
        {saving ? "Salvando..." : notice}
      </p>

      {items.length === 0 ? (
        <p className="border border-ks-border bg-ks-surface p-4 text-sm text-ks-muted">
          Nenhum produto nesta coleção.
        </p>
      ) : (
        <ReorderList
          label="Ordem dos produtos na coleção"
          items={items}
          getKey={(item) => item.id}
          getLabel={(item) => item.name}
          disabled={saving}
          onReorder={save}
          renderItem={(item) => (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">
                {item.name}
                <span className="ml-2 text-xs font-normal text-ks-muted">
                  {STATUS_LABELS[item.status] ?? item.status}
                </span>
              </span>
              <Button
                type="button"
                variant="ghost"
                disabled={saving}
                onClick={() => save(items.filter((other) => other.id !== item.id))}
              >
                <X aria-hidden className="size-4" />
                Remover
                <span className="sr-only"> {item.name}</span>
              </Button>
            </div>
          )}
        />
      )}

      <div className="flex flex-wrap items-end gap-3 border border-ks-border bg-ks-surface p-4">
        <div className="min-w-64 flex-1 space-y-2">
          <label htmlFor="adicionar-produto" className="block text-sm font-medium">
            Adicionar produto
          </label>
          <select
            id="adicionar-produto"
            value={adding}
            onChange={(event) => setAdding(event.target.value)}
            className="h-10 w-full rounded-[var(--radius)] border border-ks-border bg-ks-surface px-3 text-sm"
          >
            <option value="">Escolha um produto</option>
            {available.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name} ({STATUS_LABELS[product.status] ?? product.status})
              </option>
            ))}
          </select>
        </div>
        <Button
          type="button"
          variant="secondary"
          disabled={!adding || saving}
          onClick={() => {
            const product = byId.get(adding);
            if (!product) return;
            setAdding("");
            save([...items, product]);
          }}
        >
          <Plus aria-hidden className="size-4" />
          Adicionar
        </Button>
      </div>
    </section>
  );
}
