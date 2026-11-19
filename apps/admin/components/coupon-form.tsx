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
import { Power, PowerOff, RefreshCw, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useActionState, useState, useTransition } from "react";
import {
  activateCouponAction,
  createCouponAction,
  deactivateCouponAction,
  deleteCouponAction,
  updateCouponAction,
} from "../app/(painel)/cupons/actions";
import type { ActionState } from "../lib/action-state";
import { formatCentsInput } from "../lib/catalog-input";
import {
  KIND_LABELS,
  MESSAGES,
  slugOptions,
  utcToSaoPauloLocal,
  type Coupon,
  type SlugOption,
} from "../lib/coupons";
import { FormError, FormField, TextareaField } from "./form-field";
import { SelectField } from "./select-field";

const CONFLICT = "promotions.coupon.version_conflict";

type EditState = (ActionState & { submittedVersion?: number }) | null;

function SlugChecklist({
  name,
  legend,
  options,
  selected,
  empty,
  error,
}: {
  name: string;
  legend: string;
  options: SlugOption[];
  selected: readonly string[];
  empty: string;
  error?: string | undefined;
}) {
  const errorId = error ? `field-${name}-error` : undefined;
  // slug salvo que sumiu do catálogo continua marcado; só sai do cupom se alguém desmarcar
  const items = slugOptions(options, selected);
  return (
    <fieldset className="space-y-2" aria-describedby={errorId}>
      <legend className="text-sm font-medium">{legend}</legend>
      {items.length === 0 ? (
        <p className="text-sm text-ks-muted">{empty}</p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {items.map((option) => {
            const id = `field-${name}-${option.slug}`;
            return (
              <li key={option.slug} className="flex items-center gap-2">
                <Checkbox
                  id={id}
                  name={name}
                  value={option.slug}
                  defaultChecked={selected.includes(option.slug)}
                />
                <label htmlFor={id} className="text-sm">
                  {option.name}
                </label>
              </li>
            );
          })}
        </ul>
      )}
      {error && (
        <p id={errorId} className="text-sm text-red-700">
          {error}
        </p>
      )}
    </fieldset>
  );
}

function valueInput(coupon: Coupon): string {
  return coupon.kind === "percent" ? String(coupon.value) : formatCentsInput(coupon.value);
}

/**
 * Cria (sem `coupon`) ou edita um cupom. Na edição o código aparece só para leitura (é imutável)
 * e a versão lida vai oculta; o 409 de versão oferece "Recarregar".
 */
export function CouponForm({
  coupon,
  categories,
  collections,
}: {
  coupon?: Coupon;
  categories: SlugOption[];
  collections: SlugOption[];
}) {
  const router = useRouter();
  const [reloading, startReload] = useTransition();
  const [state, action, pending] = useActionState<EditState, FormData>(async (prev, formData) => {
    const submittedVersion = Number(formData.get("version"));
    const result = coupon
      ? await updateCouponAction(prev, formData)
      : await createCouponAction(prev, formData);
    return result && { ...result, submittedVersion };
  }, null);

  const failed = state?.ok === false ? state : null;
  // depois de recarregar, a versão nova chega pelas props e o aviso some
  const conflict =
    failed?.code === CONFLICT && coupon !== undefined && state?.submittedVersion === coupon.version;
  const errors = failed?.fieldErrors ?? {};

  return (
    <form action={action} className="max-w-3xl space-y-6" noValidate>
      {conflict ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 border border-red-700 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          <p>{failed?.formError}</p>
          <Button
            type="button"
            variant="secondary"
            disabled={reloading}
            onClick={() => startReload(() => router.refresh())}
          >
            <RefreshCw aria-hidden className="size-4" />
            {reloading ? "Recarregando..." : "Recarregar"}
          </Button>
        </div>
      ) : (
        <FormError message={failed?.formError} />
      )}

      {coupon && (
        <>
          <input type="hidden" name="id" value={coupon.id} />
          <input type="hidden" name="version" value={coupon.version} />
        </>
      )}

      {/* a versão nova (recarregada) remonta os campos com os valores atuais */}
      <div key={coupon?.version ?? "novo"} className="space-y-6">
        <section aria-labelledby="cupom-desconto" className="grid gap-4 sm:grid-cols-2">
          <h2 id="cupom-desconto" className="text-xl sm:col-span-2">
            Desconto
          </h2>
          {coupon ? (
            <div className="space-y-2">
              <p className="text-sm font-medium">Código</p>
              <p className="flex h-10 items-center font-mono text-sm">{coupon.code}</p>
              <p className="text-xs text-ks-muted">
                O código não pode ser alterado depois de criado.
              </p>
            </div>
          ) : (
            <FormField
              name="code"
              label="Código"
              required
              maxLength={32}
              autoCapitalize="characters"
              autoComplete="off"
              spellCheck={false}
              placeholder="BEMVINDO10"
              hint="De 3 a 32 caracteres: letras sem acento, números e hífen. Fica em maiúsculas."
              error={errors.code}
            />
          )}
          <SelectField
            name="kind"
            label="Tipo"
            required
            defaultValue={coupon?.kind ?? "percent"}
            options={Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label }))}
            error={errors.kind}
          />
          <FormField
            name="value"
            label="Valor"
            required
            inputMode="decimal"
            placeholder="10"
            hint={`Percentual: inteiro de 1 a 90. Valor fixo: em reais, como 10,50. ${MESSAGES.money_hint}`}
            defaultValue={coupon ? valueInput(coupon) : undefined}
            error={errors.value}
          />
          <FormField
            name="min_order"
            label="Pedido mínimo (R$)"
            inputMode="decimal"
            placeholder="Vazio: sem mínimo"
            hint={MESSAGES.money_hint}
            defaultValue={
              coupon?.min_order_cents != null ? formatCentsInput(coupon.min_order_cents) : undefined
            }
            error={errors.min_order}
          />
          <div className="sm:col-span-2">
            <TextareaField
              name="description"
              label="Descrição interna"
              rows={2}
              maxLength={500}
              defaultValue={coupon?.description ?? ""}
              error={errors.description}
            />
          </div>
        </section>

        <section aria-labelledby="cupom-validade" className="grid gap-4 sm:grid-cols-2">
          <h2 id="cupom-validade" className="text-xl sm:col-span-2">
            Validade
          </h2>
          <p className="text-sm text-ks-muted sm:col-span-2">
            Horário de Brasília. Vazio: vale desde já ou sem data para acabar.
          </p>
          <FormField
            name="starts_at"
            label="Início"
            type="datetime-local"
            defaultValue={utcToSaoPauloLocal(coupon?.starts_at)}
            error={errors.starts_at}
          />
          <FormField
            name="ends_at"
            label="Fim"
            type="datetime-local"
            defaultValue={utcToSaoPauloLocal(coupon?.ends_at)}
            error={errors.ends_at}
          />
        </section>

        <section aria-labelledby="cupom-alcance" className="space-y-4">
          <h2 id="cupom-alcance" className="text-xl">
            Onde vale
          </h2>
          <p className="text-sm text-ks-muted">
            Sem nenhuma marcada, o cupom vale para a loja toda.
          </p>
          <SlugChecklist
            name="category_slugs"
            legend="Categorias"
            options={categories}
            selected={coupon?.category_slugs ?? []}
            empty="Nenhuma categoria cadastrada."
            error={errors.category_slugs}
          />
          <SlugChecklist
            name="collection_slugs"
            legend="Coleções"
            options={collections}
            selected={coupon?.collection_slugs ?? []}
            empty="Nenhuma coleção cadastrada."
            error={errors.collection_slugs}
          />
        </section>

        <section aria-labelledby="cupom-limites" className="grid gap-4 sm:grid-cols-2">
          <h2 id="cupom-limites" className="text-xl sm:col-span-2">
            Limites de uso
          </h2>
          <FormField
            name="max_uses_total"
            label="Usos no total"
            type="number"
            min={1}
            step={1}
            placeholder="Vazio: sem limite"
            defaultValue={
              coupon?.max_uses_total != null ? String(coupon.max_uses_total) : undefined
            }
            error={errors.max_uses_total}
          />
          <FormField
            name="max_uses_per_customer"
            label="Usos por cliente"
            type="number"
            min={1}
            step={1}
            placeholder="Vazio: sem limite"
            hint="Com limite por cliente, o cupom exige login."
            defaultValue={
              coupon?.max_uses_per_customer != null
                ? String(coupon.max_uses_per_customer)
                : undefined
            }
            error={errors.max_uses_per_customer}
          />
        </section>

        {!coupon && (
          <div className="flex items-center gap-2">
            <Checkbox id="field-active" name="active" defaultChecked />
            <label htmlFor="field-active" className="text-sm font-medium">
              Ativo assim que criado
            </label>
          </div>
        )}
      </div>

      <Button type="submit" disabled={pending}>
        {pending ? "Salvando..." : coupon ? "Salvar alterações" : "Criar cupom"}
      </Button>
    </form>
  );
}

/** Ativar ou desativar pelas rotas próprias; a página recarrega com a versão nova. */
export function CouponStatusToggle({ coupon }: { coupon: Coupon }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="max-w-56 space-y-2">
      <Button
        type="button"
        variant="secondary"
        disabled={pending}
        aria-describedby="cupom-status-aviso"
        onClick={() =>
          startTransition(async () => {
            setError(null);
            const result = coupon.active
              ? await deactivateCouponAction(coupon.id)
              : await activateCouponAction(coupon.id);
            if (result.ok) router.refresh();
            else setError(result.error);
          })
        }
      >
        {coupon.active ? (
          <PowerOff aria-hidden className="size-4" />
        ) : (
          <Power aria-hidden className="size-4" />
        )}
        {pending ? "Salvando..." : coupon.active ? "Desativar" : "Ativar"}
      </Button>
      <p id="cupom-status-aviso" className="text-xs text-ks-muted">
        O formulário recarrega com os dados salvos. Salve as alterações antes.
      </p>
      <FormError message={error ?? undefined} />
    </div>
  );
}

/** Só aparece sem usos; o 409 has_redemptions (uso entre a leitura e o clique) vira aviso. */
export function DeleteCoupon({ coupon }: { coupon: Coupon }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog onOpenChange={() => setError(null)}>
      <DialogTrigger asChild>
        <Button type="button" variant="secondary">
          <Trash2 aria-hidden className="size-4" />
          Excluir cupom
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Excluir o cupom {coupon.code}?</DialogTitle>
          <DialogDescription>
            O código deixa de funcionar na loja e pode ser cadastrado de novo depois.
          </DialogDescription>
        </DialogHeader>
        <FormError message={error ?? undefined} />
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
                const result = await deleteCouponAction(coupon.id);
                if (result.ok) router.push("/cupons?aviso=excluido");
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
