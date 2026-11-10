"use client";

import { Button } from "@katoshop/ui/button";
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
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@katoshop/ui/table";
import { Pencil, Trash2 } from "lucide-react";
import { useActionState, useState, useTransition } from "react";
import { FormError, FormField, FormNotice } from "../../../components/form-field";
import { SelectField } from "../../../components/select-field";
import type { Category } from "../../../lib/catalog-data";
import { deleteCategoryAction, saveCategoryAction } from "./actions";

function CategoryForm({ category, categories }: { category?: Category; categories: Category[] }) {
  const [state, action, pending] = useActionState(saveCategoryAction, null);
  const errors = state?.ok === false ? (state.fieldErrors ?? {}) : {};
  const suffix = category ? `-${category.id}` : "-nova";
  const parents = categories.filter((item) => item.id !== category?.id);
  return (
    <form action={action} className="grid gap-4 sm:grid-cols-2" noValidate>
      {category && <input type="hidden" name="id" value={category.id} />}
      <div className="space-y-2 sm:col-span-2">
        <FormError message={state?.ok === false ? state.formError : undefined} />
        <FormNotice message={state?.ok ? state.message : undefined} />
      </div>
      <FormField
        name="name"
        idSuffix={suffix}
        label="Nome"
        required
        maxLength={200}
        defaultValue={category?.name}
        error={errors.name}
      />
      <FormField
        name="slug"
        idSuffix={suffix}
        label="Endereço (slug)"
        maxLength={120}
        defaultValue={category?.slug}
        placeholder={category ? undefined : "Vazio: gerado a partir do nome"}
        error={errors.slug}
      />
      <SelectField
        name="parent_id"
        idSuffix={suffix}
        label="Categoria pai"
        defaultValue={category?.parent_id ?? "none"}
        options={[
          { value: "none", label: "Nenhuma (categoria principal)" },
          ...parents.map((item) => ({ value: item.id, label: item.name })),
        ]}
        error={errors.parent_id}
      />
      <FormField
        name="position"
        idSuffix={suffix}
        label="Posição"
        type="number"
        min={0}
        defaultValue={String(category?.position ?? 0)}
        error={errors.position}
      />
      <div className="sm:col-span-2">
        <Button type="submit" disabled={pending}>
          {pending ? "Salvando..." : category ? "Salvar categoria" : "Criar categoria"}
        </Button>
      </div>
    </form>
  );
}

function DeleteCategory({ category }: { category: Category }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog onOpenChange={() => setError(null)}>
      <DialogTrigger asChild>
        <Button type="button" variant="ghost">
          <Trash2 aria-hidden className="size-4" />
          Excluir
          <span className="sr-only"> {category.name}</span>
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Excluir {category.name}?</DialogTitle>
          <DialogDescription>
            Só é possível excluir categorias sem produtos. Esta ação não pode ser desfeita.
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
                const result = await deleteCategoryAction(category.id);
                if (!result.ok) setError(result.error);
              })
            }
          >
            {pending ? "Excluindo..." : "Excluir categoria"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function CategoryManager({ categories }: { categories: Category[] }) {
  const names = new Map(categories.map((category) => [category.id, category.name]));
  return (
    <div className="space-y-8">
      <section aria-labelledby="nova-categoria" className="max-w-2xl space-y-3 border border-ks-border bg-ks-surface p-4">
        <h2 id="nova-categoria" className="text-xl">
          Nova categoria
        </h2>
        <CategoryForm categories={categories} />
      </section>

      <section aria-labelledby="lista-categorias" className="space-y-3">
        <h2 id="lista-categorias" className="text-xl">
          Categorias
        </h2>
        {categories.length === 0 ? (
          <p className="border border-ks-border bg-ks-surface p-4 text-sm text-ks-muted">
            Nenhuma categoria cadastrada.
          </p>
        ) : (
          <div className="overflow-x-auto border border-ks-border bg-ks-surface">
            <Table>
              <TableCaption className="sr-only">Categorias do catálogo</TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Nome</TableHead>
                  <TableHead scope="col">Endereço</TableHead>
                  <TableHead scope="col">Categoria pai</TableHead>
                  <TableHead scope="col" className="text-right">
                    Posição
                  </TableHead>
                  <TableHead scope="col">
                    <span className="sr-only">Ações</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {categories.map((category) => (
                  <TableRow key={category.id}>
                    <TableCell className="font-medium">{category.name}</TableCell>
                    <TableCell className="font-mono text-xs">{category.slug}</TableCell>
                    <TableCell>
                      {category.parent_id ? (names.get(category.parent_id) ?? "") : "Principal"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{category.position}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Dialog>
                          <DialogTrigger asChild>
                            <Button type="button" variant="ghost">
                              <Pencil aria-hidden className="size-4" />
                              Editar
                              <span className="sr-only"> {category.name}</span>
                            </Button>
                          </DialogTrigger>
                          <DialogContent className="max-h-[90dvh] overflow-y-auto">
                            <DialogHeader>
                              <DialogTitle>Editar {category.name}</DialogTitle>
                              <DialogDescription>
                                Mudar o endereço altera o link da categoria na loja.
                              </DialogDescription>
                            </DialogHeader>
                            <CategoryForm
                              key={`${category.id}-${category.name}-${category.slug}-${category.parent_id}-${category.position}`}
                              category={category}
                              categories={categories}
                            />
                          </DialogContent>
                        </Dialog>
                        <DeleteCategory category={category} />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    </div>
  );
}
