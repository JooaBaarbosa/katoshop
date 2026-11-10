"use client";

import { Badge } from "@katoshop/ui/badge";
import { Button } from "@katoshop/ui/button";
import { Archive, CircleAlert, CircleCheck, Send } from "lucide-react";
import { useState, useTransition } from "react";
import {
  archiveProductAction,
  publishProductAction,
} from "../app/(painel)/produtos/[id]/actions";
import type { AdminProduct } from "../lib/catalog-data";
import { publishBlockers, STATUS_LABELS } from "../lib/catalog-input";
import { messageFor } from "../lib/problem-messages";

const CHECKS = [
  { blocker: "no_active_variant", done: "Pelo menos uma variante ativa" },
  { blocker: "no_image", done: "Pelo menos uma foto" },
  { blocker: "no_price", done: "Toda variante ativa com preço maior que zero" },
] as const;

/** Checklist dos blockers de publicação e os botões Publicar e Arquivar. */
export function PublishChecklist({ product }: { product: AdminProduct }) {
  const blockers = publishBlockers(product);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [serverBlockers, setServerBlockers] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  function publish() {
    setError(null);
    setNotice(null);
    setServerBlockers([]);
    startTransition(async () => {
      const result = await publishProductAction(product.id);
      if (result.ok) setNotice("Produto publicado. A loja mostra a mudança em até 60 segundos.");
      else {
        setError(result.error);
        setServerBlockers(result.blockers ?? []);
      }
    });
  }

  function archive() {
    setError(null);
    setNotice(null);
    startTransition(async () => {
      const result = await archiveProductAction(product.id);
      if (result.ok) setNotice("Produto arquivado. Ele sai da loja em até 60 segundos.");
      else setError(result.error);
    });
  }

  return (
    <div className="max-w-2xl space-y-5">
      <p className="flex items-center gap-2 text-sm">
        Situação atual:
        <Badge variant={product.status === "active" ? "accent" : "default"}>
          {STATUS_LABELS[product.status] ?? product.status}
        </Badge>
      </p>

      <ul aria-label="Requisitos para publicar" className="space-y-2">
        {CHECKS.map((check) => {
          const missing = blockers.includes(check.blocker);
          return (
            <li key={check.blocker} className="flex items-start gap-2 text-sm">
              {missing ? (
                <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-red-700" />
              ) : (
                <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-green-700" />
              )}
              <span>
                <span className="sr-only">{missing ? "Pendente: " : "Concluído: "}</span>
                {missing ? messageFor(check.blocker) : check.done}
              </span>
            </li>
          );
        })}
      </ul>

      {error && (
        <div role="alert" className="space-y-1 border border-red-700 bg-red-50 px-3 py-2 text-sm text-red-800">
          <p>{error}</p>
          {serverBlockers.length > 0 && (
            <ul className="list-disc pl-5">
              {serverBlockers.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {notice && (
        <p role="status" className="border border-green-700 bg-green-50 px-3 py-2 text-sm text-green-800">
          {notice}
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        {product.status !== "active" && (
          <Button type="button" onClick={publish} disabled={pending || blockers.length > 0}>
            <Send aria-hidden className="size-4" />
            Publicar
          </Button>
        )}
        {product.status !== "archived" && (
          <Button type="button" variant="secondary" onClick={archive} disabled={pending}>
            <Archive aria-hidden className="size-4" />
            Arquivar
          </Button>
        )}
      </div>
    </div>
  );
}
