"use client";

import { cn } from "@katoshop/ui/cn";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import { useState, type ReactNode } from "react";

/** Move o item de `from` para `to`. Índice inválido devolve uma cópia inalterada. */
export function move<T>(items: T[], from: number, to: number): T[] {
  const copy = [...items];
  const valid = (index: number) => Number.isInteger(index) && index >= 0 && index < items.length;
  if (!valid(from) || !valid(to) || from === to) return copy;
  const [item] = copy.splice(from, 1) as [T];
  copy.splice(to, 0, item);
  return copy;
}

const ICON_BUTTON =
  "inline-flex size-9 items-center justify-center rounded-[var(--radius)] border border-ks-border bg-ks-surface text-ks-fg transition-colors duration-[var(--duration-fast)] hover:bg-ks-fg/10 disabled:pointer-events-none disabled:opacity-40";

/**
 * Lista reordenável: arrastar e soltar nativo para mouse e os botões "Mover para cima" e
 * "Mover para baixo" para teclado e leitores de tela. Cada mudança chama `onReorder` com a
 * nova ordem; quem usa decide quando gravar.
 */
export function ReorderList<T>({
  items,
  getKey,
  getLabel,
  renderItem,
  onReorder,
  disabled = false,
  label,
}: {
  items: T[];
  getKey: (item: T) => string;
  /** Nome curto do item, usado nos rótulos acessíveis dos botões. */
  getLabel: (item: T) => string;
  renderItem: (item: T, index: number) => ReactNode;
  onReorder: (next: T[]) => void;
  disabled?: boolean;
  label: string;
}) {
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);

  function drop(to: number) {
    if (dragging !== null && dragging !== to) onReorder(move(items, dragging, to));
    setDragging(null);
    setOver(null);
  }

  return (
    <ol aria-label={label} className="space-y-2">
      {items.map((item, index) => {
        const name = getLabel(item);
        return (
          <li
            key={getKey(item)}
            draggable={!disabled}
            onDragStart={(event) => {
              event.dataTransfer.effectAllowed = "move";
              setDragging(index);
            }}
            onDragOver={(event) => {
              if (dragging === null) return;
              event.preventDefault();
              setOver(index);
            }}
            onDragLeave={() => setOver((current) => (current === index ? null : current))}
            onDrop={(event) => {
              event.preventDefault();
              drop(index);
            }}
            onDragEnd={() => {
              setDragging(null);
              setOver(null);
            }}
            className={cn(
              "flex items-center gap-3 border bg-ks-surface p-3",
              over === index && dragging !== index ? "border-ks-fg" : "border-ks-border",
              dragging === index && "opacity-60",
            )}
          >
            <GripVertical aria-hidden className="size-4 shrink-0 cursor-grab text-ks-muted" />
            <span className="w-6 shrink-0 text-right font-mono text-xs tabular-nums text-ks-muted">
              {index + 1}
            </span>
            <div className="min-w-0 flex-1">{renderItem(item, index)}</div>
            <div className="flex shrink-0 gap-1">
              <button
                type="button"
                className={ICON_BUTTON}
                disabled={disabled || index === 0}
                onClick={() => onReorder(move(items, index, index - 1))}
                aria-label={`Mover para cima: ${name}`}
                title="Mover para cima"
              >
                <ArrowUp aria-hidden className="size-4" />
              </button>
              <button
                type="button"
                className={ICON_BUTTON}
                disabled={disabled || index === items.length - 1}
                onClick={() => onReorder(move(items, index, index + 1))}
                aria-label={`Mover para baixo: ${name}`}
                title="Mover para baixo"
              >
                <ArrowDown aria-hidden className="size-4" />
              </button>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
