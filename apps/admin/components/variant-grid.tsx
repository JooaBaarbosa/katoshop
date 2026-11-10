"use client";

import { Button } from "@katoshop/ui/button";
import { Checkbox } from "@katoshop/ui/checkbox";
import { Input } from "@katoshop/ui/input";
import { formatBRL } from "@katoshop/ui/money";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@katoshop/ui/table";
import { BookOpen } from "lucide-react";
import Link from "next/link";
import { useState, useTransition } from "react";
import { updateVariantAction } from "../app/(painel)/produtos/[id]/actions";
import type { AdminVariant } from "../lib/catalog-data";
import { colorName, COLORS, formatCentsInput, sortVariants } from "../lib/catalog-input";

function Swatch({ code }: { code: string }) {
  const hex = COLORS.find((color) => color.code === code)?.hex ?? "transparent";
  return (
    <span
      aria-hidden
      className="inline-block size-4 shrink-0 border border-ks-fg/40"
      style={{ backgroundColor: hex }}
    />
  );
}

function VariantRow({ productId, variant }: { productId: string; variant: AdminVariant }) {
  const initialPrice = variant.price_cents === null ? "" : formatCentsInput(variant.price_cents);
  const [price, setPrice] = useState(initialPrice);
  const [active, setActive] = useState(variant.active);
  const [error, setError] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();
  const changed = price.trim() !== initialPrice || active !== variant.active;
  const label = `${colorName(variant.color_code)} ${variant.size_code}`;
  const errorId = `variante-${variant.id}-erro`;

  function save() {
    setError(null);
    startSaving(async () => {
      const result = await updateVariantAction({
        productId,
        variantId: variant.id,
        version: variant.version,
        price,
        active,
      });
      if (!result.ok) setError(result.error);
    });
  }

  return (
    <TableRow>
      <TableCell>
        <span className="flex items-center gap-2">
          <Swatch code={variant.color_code} />
          {colorName(variant.color_code)}
        </span>
      </TableCell>
      <TableCell className="font-medium">{variant.size_code}</TableCell>
      <TableCell className="font-mono text-xs">{variant.sku}</TableCell>
      <TableCell className="min-w-36">
        <Input
          aria-label={`Preço de ${label} em reais`}
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error ? true : undefined}
          inputMode="decimal"
          value={price}
          placeholder={`Base ${formatBRL(variant.effective_price_cents)}`}
          onChange={(event) => setPrice(event.target.value)}
        />
        {error && (
          <p id={errorId} role="alert" className="mt-1 text-xs text-red-700">
            {error}
          </p>
        )}
      </TableCell>
      <TableCell>
        <Checkbox
          aria-label={`${label} ativa`}
          checked={active}
          onCheckedChange={(value) => setActive(value === true)}
        />
      </TableCell>
      <TableCell className="text-right tabular-nums">{variant.available}</TableCell>
      <TableCell>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={!changed || saving}
            onClick={save}
            aria-label={`Salvar ${label}`}
          >
            {saving ? "Salvando..." : "Salvar"}
          </Button>
          <Link
            href={`/produtos/${productId}/variantes/${variant.id}/estoque`}
            className="inline-flex items-center gap-1 text-sm font-medium underline-offset-4 hover:underline"
          >
            <BookOpen aria-hidden className="size-4" />
            Estoque
            <span className="sr-only"> de {label}</span>
          </Link>
        </div>
      </TableCell>
    </TableRow>
  );
}

/** Grade cor × tamanho: preço próprio (vazio usa o preço base), ativa e saldo disponível. */
export function VariantGrid({
  productId,
  variants,
}: {
  productId: string;
  variants: AdminVariant[];
}) {
  if (variants.length === 0) {
    return (
      <p className="border border-ks-border bg-ks-surface p-4 text-sm text-ks-muted">
        Nenhuma variante ainda. Gere a grade de cores e tamanhos abaixo.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto border border-ks-border bg-ks-surface">
      <Table>
        <TableCaption className="sr-only">
          Variantes por cor e tamanho, com preço, situação e estoque disponível
        </TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Cor</TableHead>
            <TableHead scope="col">Tamanho</TableHead>
            <TableHead scope="col">SKU</TableHead>
            <TableHead scope="col">Preço (vazio = base)</TableHead>
            <TableHead scope="col">Ativa</TableHead>
            <TableHead scope="col" className="text-right">
              Disponível
            </TableHead>
            <TableHead scope="col">
              <span className="sr-only">Ações</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortVariants(variants).map((variant) => (
            // a versão no key descarta a edição local quando a variante muda no servidor
            <VariantRow key={`${variant.id}-${variant.version}`} productId={productId} variant={variant} />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
