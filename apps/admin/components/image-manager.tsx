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
import { Input } from "@katoshop/ui/input";
import { Pencil, Trash2, Upload } from "lucide-react";
import Image from "next/image";
import { useActionState, useState, useTransition } from "react";
import {
  deleteImageAction,
  reorderImagesAction,
  updateImageAction,
  uploadImageAction,
} from "../app/(painel)/produtos/[id]/actions";
import type { AdminImage } from "../lib/catalog-data";
import { colorName, COLORS } from "../lib/catalog-input";
import { messageFor } from "../lib/problem-messages";
import { FormError, FormField, FormNotice } from "./form-field";
import { ReorderList } from "./reorder-list";
import { SelectField } from "./select-field";

const MAX_BYTES = 8 * 1024 * 1024;
const TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const COLOR_OPTIONS = [
  { value: "none", label: "Todas as cores" },
  ...COLORS.map((color) => ({ value: color.code, label: color.name })),
];

type Pending = {
  key: string;
  file: File;
  alt: string;
  status: "waiting" | "sending" | "sent" | "error";
  error?: string;
};

function precheck(file: File): string | null {
  if (!TYPES.has(file.type)) return messageFor("catalog.image.unsupported_type");
  if (file.size > MAX_BYTES) return messageFor("catalog.image.too_large");
  return null;
}

const STATUS_TEXT: Record<Pending["status"], string> = {
  waiting: "Aguardando envio",
  sending: "Enviando...",
  sent: "Enviada",
  error: "Não enviada",
};

function Uploader({ productId }: { productId: string }) {
  const [pending, setPending] = useState<Pending[]>([]);
  const [shared, setShared] = useState({
    color_code: "none",
    credit_author: "",
    credit_source_url: "",
    license: "",
  });
  const [sending, startSending] = useTransition();
  const [formError, setFormError] = useState<string | null>(null);

  function pick(files: FileList | null) {
    setFormError(null);
    setPending(
      Array.from(files ?? []).map((file, index) => {
        const error = precheck(file);
        return {
          key: `${file.name}-${file.size}-${index}`,
          file,
          alt: "",
          status: error ? "error" : "waiting",
          ...(error ? { error } : {}),
        };
      }),
    );
  }

  function update(key: string, patch: Partial<Pending>) {
    setPending((items) => items.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }

  function send() {
    const queue = pending.filter((item) => item.status === "waiting" || item.status === "error");
    if (queue.some((item) => precheck(item.file) === null && !item.alt.trim())) {
      setFormError("Escreva o texto alternativo de cada foto antes de enviar.");
      return;
    }
    setFormError(null);
    startSending(async () => {
      // uma requisição por foto, em sequência: cada uma fica abaixo do limite e tem o próprio erro
      for (const item of queue) {
        if (precheck(item.file) !== null) continue;
        update(item.key, { status: "sending" });
        const data = new FormData();
        data.set("file", item.file);
        data.set("alt", item.alt);
        if (shared.color_code !== "none") data.set("color_code", shared.color_code);
        for (const name of ["credit_author", "credit_source_url", "license"] as const) {
          if (shared[name].trim()) data.set(name, shared[name].trim());
        }
        try {
          const result = await uploadImageAction(productId, data);
          update(item.key, result.ok ? { status: "sent" } : { status: "error", error: result.error });
        } catch {
          update(item.key, { status: "error", error: messageFor("catalog.image.too_large") });
        }
      }
    });
  }

  const sendable = pending.some((item) => item.status === "waiting" || item.status === "error");

  return (
    <section aria-labelledby="enviar-fotos" className="space-y-4 border border-ks-border bg-ks-surface p-4">
      <h3 id="enviar-fotos" className="text-lg">
        Enviar fotos
      </h3>
      <p className="text-sm text-ks-muted">
        JPG, PNG ou WebP até 8 MB. Use fotos reais com licença e informe os créditos.
      </p>
      <div className="space-y-2">
        <label htmlFor="fotos-arquivos" className="block text-sm font-medium">
          Arquivos
        </label>
        <input
          id="fotos-arquivos"
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => pick(event.target.files)}
          className="block w-full text-sm file:mr-3 file:rounded-[var(--radius)] file:border file:border-ks-fg file:bg-transparent file:px-3 file:py-2 file:text-sm file:font-semibold file:uppercase"
        />
      </div>

      {pending.length > 0 && (
        <ul className="space-y-3" aria-label="Fotos selecionadas">
          {pending.map((item, index) => (
            <li key={item.key} className="space-y-2 border border-ks-border p-3">
              <p className="flex flex-wrap justify-between gap-2 text-sm">
                <span className="font-medium">{item.file.name}</span>
                <span role="status" className="text-ks-muted">
                  {STATUS_TEXT[item.status]}
                </span>
              </p>
              {item.status !== "sent" && precheck(item.file) === null && (
                <div className="space-y-1">
                  <label htmlFor={`alt-${index}`} className="block text-sm font-medium">
                    Texto alternativo (obrigatório)
                  </label>
                  <Input
                    id={`alt-${index}`}
                    value={item.alt}
                    maxLength={300}
                    required
                    placeholder="Ex.: moletom preto dobrado sobre mesa de madeira"
                    onChange={(event) => update(item.key, { alt: event.target.value })}
                  />
                </div>
              )}
              {item.error && (
                <p role="alert" className="text-sm text-red-700">
                  {item.error}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-semibold">Cor e créditos (valem para todas)</legend>
        <div className="space-y-2">
          <label htmlFor="fotos-cor" className="block text-sm font-medium">
            Cor da foto
          </label>
          <select
            id="fotos-cor"
            value={shared.color_code}
            onChange={(event) => setShared({ ...shared, color_code: event.target.value })}
            className="h-10 w-full rounded-[var(--radius)] border border-ks-border bg-ks-surface px-3 text-sm"
          >
            {COLOR_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        {(
          [
            ["credit_author", "Autor", "Nome do fotógrafo"],
            ["credit_source_url", "URL de origem", "https://unsplash.com/photos/..."],
            ["license", "Licença", "Unsplash License"],
          ] as const
        ).map(([name, label, placeholder]) => (
          <div key={name} className="space-y-2">
            <label htmlFor={`fotos-${name}`} className="block text-sm font-medium">
              {label}
            </label>
            <Input
              id={`fotos-${name}`}
              type={name === "credit_source_url" ? "url" : "text"}
              value={shared[name]}
              placeholder={placeholder}
              onChange={(event) => setShared({ ...shared, [name]: event.target.value })}
            />
          </div>
        ))}
      </fieldset>

      {formError && (
        <p role="alert" className="text-sm text-red-700">
          {formError}
        </p>
      )}
      <Button type="button" onClick={send} disabled={!sendable || sending}>
        <Upload aria-hidden className="size-4" />
        {sending ? "Enviando..." : "Enviar fotos"}
      </Button>
    </section>
  );
}

function ImageEditor({ productId, image }: { productId: string; image: AdminImage }) {
  const [state, action, pending] = useActionState(updateImageAction, null);
  const errors = state?.ok === false ? (state.fieldErrors ?? {}) : {};
  const suffix = `-${image.id}`;
  return (
    <form action={action} className="mt-3 grid gap-3 sm:grid-cols-2">
      <input type="hidden" name="product_id" value={productId} />
      <input type="hidden" name="image_id" value={image.id} />
      <div className="sm:col-span-2 space-y-2">
        <FormError message={state?.ok === false ? state.formError : undefined} />
        <FormNotice message={state?.ok ? state.message : undefined} />
      </div>
      <FormField
        name="alt"
        idSuffix={suffix}
        label="Texto alternativo"
        required
        maxLength={300}
        defaultValue={image.alt}
        error={errors.alt}
      />
      <SelectField
        name="color_code"
        idSuffix={suffix}
        label="Cor da foto"
        defaultValue={image.color_code ?? "none"}
        options={COLOR_OPTIONS}
      />
      <FormField name="credit_author" label="Autor" idSuffix={suffix} defaultValue={image.credit_author ?? ""} />
      <FormField
        name="credit_source_url"
        idSuffix={suffix}
        label="URL de origem"
        type="url"
        defaultValue={image.credit_source_url ?? ""}
        error={errors.credit_source_url}
      />
      <FormField name="license" label="Licença" idSuffix={suffix} defaultValue={image.license ?? ""} />
      <div className="sm:col-span-2">
        <Button type="submit" variant="secondary" disabled={pending}>
          {pending ? "Salvando..." : "Salvar foto"}
        </Button>
      </div>
    </form>
  );
}

function ImageItem({
  productId,
  image,
  onError,
}: {
  productId: string;
  image: AdminImage;
  onError: (message: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [deleting, startDeleting] = useTransition();
  const credits = [image.credit_author, image.license].filter(Boolean).join(", ");
  return (
    <div>
      <div className="flex flex-wrap items-center gap-4">
        <Image
          src={image.url}
          alt={image.alt}
          width={96}
          height={Math.round((96 * image.height) / image.width) || 96}
          className="h-24 w-20 shrink-0 border border-ks-border object-cover"
        />
        <div className="min-w-0 flex-1 space-y-1 text-sm">
          <p className="font-medium">{image.alt}</p>
          <p className="text-ks-muted">
            {image.color_code ? colorName(image.color_code) : "Todas as cores"}
            {" · "}
            {credits || "Sem créditos informados"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="ghost"
            aria-expanded={editing}
            onClick={() => setEditing(!editing)}
          >
            <Pencil aria-hidden className="size-4" />
            {editing ? "Fechar" : "Editar"}
          </Button>
          <Dialog>
            <DialogTrigger asChild>
              <Button type="button" variant="ghost">
                <Trash2 aria-hidden className="size-4" />
                Excluir
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Excluir foto?</DialogTitle>
                <DialogDescription>
                  A foto &quot;{image.alt}&quot; sai do produto. Esta ação não pode ser desfeita.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button type="button" variant="secondary">
                    Cancelar
                  </Button>
                </DialogClose>
                <Button
                  type="button"
                  disabled={deleting}
                  onClick={() =>
                    startDeleting(async () => {
                      const result = await deleteImageAction(productId, image.id);
                      onError(result.ok ? null : result.error);
                    })
                  }
                >
                  {deleting ? "Excluindo..." : "Excluir foto"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>
      {editing && <ImageEditor productId={productId} image={image} />}
    </div>
  );
}

/** Fotos do produto: envio múltiplo, alt obrigatório, cor, créditos e ordem de exibição. */
export function ImageManager({ productId, images }: { productId: string; images: AdminImage[] }) {
  const sorted = (list: AdminImage[]) => [...list].sort((a, b) => a.position - b.position);
  const [source, setSource] = useState(images);
  const [order, setOrder] = useState(() => sorted(images));
  // fotos novas, editadas ou excluídas chegam pelas props depois da revalidação
  if (source !== images) {
    setSource(images);
    setOrder(sorted(images));
  }
  const [saving, startSaving] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function reorder(next: AdminImage[]) {
    const previous = order;
    setOrder(next);
    setError(null);
    startSaving(async () => {
      const result = await reorderImagesAction(
        productId,
        next.map((image) => image.id),
      );
      if (!result.ok) {
        setOrder(previous);
        setError(result.error);
      }
    });
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="fotos-atuais" className="space-y-3">
        <h3 id="fotos-atuais" className="text-lg">
          Fotos do produto
        </h3>
        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
        {saving && (
          <p role="status" className="text-sm text-ks-muted">
            Salvando a nova ordem...
          </p>
        )}
        {order.length === 0 ? (
          <p className="border border-ks-border bg-ks-surface p-4 text-sm text-ks-muted">
            Nenhuma foto ainda. A primeira foto da lista é a capa na loja.
          </p>
        ) : (
          <ReorderList
            label="Ordem das fotos; a primeira é a capa"
            items={order}
            getKey={(image) => image.id}
            getLabel={(image) => image.alt}
            disabled={saving}
            onReorder={reorder}
            renderItem={(image) => (
              <ImageItem productId={productId} image={image} onError={setError} />
            )}
          />
        )}
      </section>
      <Uploader productId={productId} />
    </div>
  );
}
