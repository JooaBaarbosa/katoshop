"use client";

import { Button } from "@katoshop/ui/button";
import { Checkbox } from "@katoshop/ui/checkbox";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@katoshop/ui/dialog";
import { Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useActionState, useState, useTransition } from "react";
import { FormError, FormField, FormNotice, TextareaField } from "../../../components/form-field";
import type { Collection } from "../../../lib/catalog-data";
import { deleteCollectionAction, saveCollectionAction } from "./actions";

/** Cria (sem `collection`) ou edita os dados de uma coleção. */
export function CollectionForm({ collection }: { collection?: Collection }) {
  const [state, action, pending] = useActionState(saveCollectionAction, null);
  const errors = state?.ok === false ? (state.fieldErrors ?? {}) : {};
  return (
    <form action={action} className="grid max-w-2xl gap-4 sm:grid-cols-2" noValidate>
      {collection && <input type="hidden" name="id" value={collection.id} />}
      <div className="space-y-2 sm:col-span-2">
        <FormError message={state?.ok === false ? state.formError : undefined} />
        <FormNotice message={state?.ok ? state.message : undefined} />
      </div>
      <FormField
        name="name"
        label="Nome"
        required
        maxLength={200}
        defaultValue={collection?.name}
        error={errors.name}
      />
      <FormField
        name="slug"
        label="Endereço (slug)"
        maxLength={120}
        defaultValue={collection?.slug}
        placeholder={collection ? undefined : "Vazio: gerado a partir do nome"}
        error={errors.slug}
      />
      <div className="sm:col-span-2">
        <TextareaField
          name="description"
          label="Descrição"
          rows={3}
          defaultValue={collection?.description ?? ""}
          error={errors.description}
        />
      </div>
      <FormField
        name="position"
        label="Posição"
        type="number"
        min={0}
        defaultValue={String(collection?.position ?? 0)}
        error={errors.position}
      />
      <div className="flex items-center gap-2 self-end pb-2">
        <Checkbox id="field-featured" name="featured" defaultChecked={collection?.featured ?? false} />
        <label htmlFor="field-featured" className="text-sm font-medium">
          Destaque na página inicial
        </label>
      </div>
      <div className="sm:col-span-2">
        <Button type="submit" disabled={pending}>
          {pending ? "Salvando..." : collection ? "Salvar coleção" : "Criar coleção"}
        </Button>
      </div>
    </form>
  );
}

export function DeleteCollection({ collection }: { collection: Collection }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog onOpenChange={() => setError(null)}>
      <DialogTrigger asChild>
        <Button type="button" variant="secondary">
          <Trash2 aria-hidden className="size-4" />
          Excluir coleção
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Excluir {collection.name}?</DialogTitle>
          <DialogDescription>
            Os produtos continuam no catálogo; só a coleção deixa de existir.
          </DialogDescription>
        </DialogHeader>
        {error && (
          <p role="alert" className="border border-red-700 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </p>
        )}
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              Cancelar
            </Button>
          </DialogClose>
          <Button
            type="button"
            disabled={pending}
            onClick={() =>
              startTransition(async () => {
                const result = await deleteCollectionAction(collection.id);
                if (result.ok) router.push("/colecoes");
                else setError(result.error);
              })
            }
          >
            {pending ? "Excluindo..." : "Excluir"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
