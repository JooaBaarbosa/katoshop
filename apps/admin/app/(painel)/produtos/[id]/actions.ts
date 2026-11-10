"use server";

import { ApiProblem, unwrap } from "@katoshop/api-client";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  failureResult,
  failureState,
  field,
  optional,
  slugPatch,
  type ActionResult,
  type ActionState,
} from "../../../../lib/action-state";
import { catalog } from "../../../../lib/api";
import { parseAttributes, parsePriceCents } from "../../../../lib/catalog-input";
import { blockerMessages, messageFor } from "../../../../lib/problem-messages";
import { staffAction } from "../../../../lib/staff-action";

const PRODUCT_FIELD_BY_CODE = {
  "catalog.product.slug_taken": "slug",
  "catalog.product.invalid_slug": "slug",
};

type ProductFields = {
  name: string;
  slug: string | null;
  description: string | null;
  category_id: string;
  base_price_cents: number;
  attributes: Record<string, string>;
};

function readProduct(
  formData: FormData,
): { ok: true; fields: ProductFields } | { ok: false; fieldErrors: Record<string, string> } {
  const name = field(formData, "name");
  const categoryId = field(formData, "category_id");
  const price = parsePriceCents(field(formData, "base_price"));
  const fieldErrors: Record<string, string> = {};
  if (!name) fieldErrors.name = "Informe o nome.";
  if (!categoryId) fieldErrors.category_id = "Escolha a categoria.";
  if (price === null) fieldErrors.base_price = "Informe um preço válido, como 129,90.";
  if (Object.keys(fieldErrors).length > 0 || price === null) return { ok: false, fieldErrors };
  return {
    ok: true,
    fields: {
      name,
      slug: optional(formData, "slug"),
      description: optional(formData, "description"),
      category_id: categoryId,
      base_price_cents: price,
      attributes: parseAttributes(field(formData, "attributes")),
    },
  };
}

function withoutSlug(fields: ProductFields): Omit<ProductFields, "slug"> {
  const rest: Partial<ProductFields> = { ...fields };
  delete rest.slug;
  return rest as Omit<ProductFields, "slug">;
}

export async function createProductAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const input = readProduct(formData);
  if (!input.ok) return { ok: false, fieldErrors: input.fieldErrors };
  const result = await staffAction(async (token) =>
    unwrap(await catalog(token).POST("/v1/admin/products", { body: input.fields })),
  );
  if (!result.ok) return failureState(result, PRODUCT_FIELD_BY_CODE);
  redirect(`/produtos/${result.data.id}`);
}

export async function updateProductAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const id = field(formData, "id");
  const version = Number(field(formData, "version"));
  const input = readProduct(formData);
  if (!input.ok) return { ok: false, fieldErrors: input.fieldErrors };
  const result = await staffAction(async (token) =>
    unwrap(
      await catalog(token).PATCH("/v1/admin/products/{product_id}", {
        params: { path: { product_id: id } },
        // slug vazio na edição: mantém o atual (null não é aceito no PATCH)
        body: { version, ...withoutSlug(input.fields), ...slugPatch(formData) },
      }),
    ),
  );
  if (!result.ok) return failureState(result, PRODUCT_FIELD_BY_CODE);
  revalidatePath(`/produtos/${id}`);
  return { ok: true, message: "Alterações salvas." };
}

export async function generateVariantsAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const id = field(formData, "product_id");
  const colors = formData.getAll("colors").filter((v): v is string => typeof v === "string");
  const sizes = formData.getAll("sizes").filter((v): v is string => typeof v === "string");
  if (colors.length === 0 || sizes.length === 0) {
    return { ok: false, formError: "Marque pelo menos uma cor e um tamanho." };
  }
  const result = await staffAction(async (token) =>
    unwrap(
      await catalog(token).POST("/v1/admin/products/{product_id}/variants/generate", {
        params: { path: { product_id: id } },
        body: { colors, sizes },
      }),
    ),
  );
  if (!result.ok) return failureState(result);
  revalidatePath(`/produtos/${id}`);
  return { ok: true, message: "Grade gerada. Combinações que já existiam foram mantidas." };
}

export async function updateVariantAction(input: {
  productId: string;
  variantId: string;
  version: number;
  /** Texto do campo de preço; vazio volta ao preço base do produto. */
  price: string;
  active: boolean;
}): Promise<ActionResult> {
  const text = input.price.trim();
  const price = text === "" ? null : parsePriceCents(text);
  if (text !== "" && price === null) {
    return { ok: false, error: "Informe um preço válido, como 129,90, ou deixe vazio." };
  }
  const result = await staffAction(async (token) =>
    unwrap(
      await catalog(token).PATCH("/v1/admin/variants/{variant_id}", {
        params: { path: { variant_id: input.variantId } },
        body: { version: input.version, price_cents: price, active: input.active },
      }),
    ),
  );
  if (!result.ok) return failureResult(result);
  revalidatePath(`/produtos/${input.productId}`);
  return { ok: true };
}

const UPLOAD_TEXT_FIELDS = [
  "alt",
  "color_code",
  "credit_author",
  "credit_source_url",
  "license",
] as const;

type UploadBody = {
  file: string;
  alt: string;
  color_code?: string;
  credit_author?: string;
  credit_source_url?: string;
  license?: string;
};

/**
 * Uma foto por chamada (o cliente envia os arquivos em sequência): cada requisição fica abaixo
 * do limite de corpo e cada arquivo tem o próprio erro. O multipart vai como está para a API.
 */
export async function uploadImageAction(
  productId: string,
  formData: FormData,
): Promise<ActionResult> {
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return { ok: false, error: "Escolha um arquivo de imagem." };
  }
  if (!field(formData, "alt")) {
    return { ok: false, error: messageFor("catalog.image.alt_required") };
  }
  const body = new FormData();
  body.set("file", file, file.name);
  for (const name of UPLOAD_TEXT_FIELDS) {
    const value = field(formData, name);
    if (value) body.set(name, value);
  }
  const result = await staffAction(async (token) =>
    unwrap(
      await catalog(token).POST("/v1/admin/products/{product_id}/images", {
        params: { path: { product_id: productId } },
        // o tipo gerado descreve os campos do multipart; o corpo real é o FormData
        body: body as unknown as UploadBody,
        bodySerializer: (value) => value as unknown as FormData,
      }),
    ),
  );
  if (!result.ok) return failureResult(result);
  revalidatePath(`/produtos/${productId}`);
  return { ok: true };
}

function colorOf(formData: FormData): string | null {
  const value = field(formData, "color_code");
  return value === "" || value === "none" ? null : value;
}

export async function updateImageAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const productId = field(formData, "product_id");
  const imageId = field(formData, "image_id");
  const alt = field(formData, "alt");
  if (!alt) return { ok: false, fieldErrors: { alt: messageFor("catalog.image.alt_required") } };
  const result = await staffAction(async (token) =>
    unwrap(
      await catalog(token).PATCH("/v1/admin/images/{image_id}", {
        params: { path: { image_id: imageId } },
        body: {
          alt,
          // "none" é o item "Todas as cores" do seletor: limpa a cor da foto
          color_code: colorOf(formData),
          credit_author: optional(formData, "credit_author"),
          credit_source_url: optional(formData, "credit_source_url"),
          license: optional(formData, "license"),
        },
      }),
    ),
  );
  if (!result.ok) return failureState(result);
  revalidatePath(`/produtos/${productId}`);
  return { ok: true, message: "Foto atualizada." };
}

export async function deleteImageAction(productId: string, imageId: string): Promise<ActionResult> {
  const result = await staffAction(async (token) => {
    const { response, error } = await catalog(token).DELETE("/v1/admin/images/{image_id}", {
      params: { path: { image_id: imageId } },
    });
    if (!response.ok) unwrap({ error, response });
  });
  if (!result.ok) return failureResult(result);
  revalidatePath(`/produtos/${productId}`);
  return { ok: true };
}

/** Grava a nova ordem das fotos: só as que mudaram de posição recebem PATCH. */
export async function reorderImagesAction(
  productId: string,
  orderedIds: string[],
): Promise<ActionResult> {
  const result = await staffAction(async (token) => {
    const api = catalog(token);
    const product = unwrap(
      await api.GET("/v1/admin/products/{product_id}", {
        params: { path: { product_id: productId } },
      }),
    );
    const current = new Map(product.images.map((image) => [image.id, image.position]));
    for (const [position, imageId] of orderedIds.entries()) {
      if (!current.has(imageId) || current.get(imageId) === position) continue;
      unwrap(
        await api.PATCH("/v1/admin/images/{image_id}", {
          params: { path: { image_id: imageId } },
          body: { position },
        }),
      );
    }
  });
  if (!result.ok) return failureResult(result);
  revalidatePath(`/produtos/${productId}`);
  return { ok: true };
}

export type PublishResult = { ok: true } | { ok: false; error: string; blockers?: string[] };

export async function publishProductAction(productId: string): Promise<PublishResult> {
  let blockers: string[] | undefined;
  const result = await staffAction(async (token) => {
    try {
      return unwrap(
        await catalog(token).POST("/v1/admin/products/{product_id}/publish", {
          params: { path: { product_id: productId } },
        }),
      );
    } catch (error) {
      if (error instanceof ApiProblem && error.code === "catalog.product.not_publishable") {
        blockers = blockerMessages(error);
      }
      throw error;
    }
  });
  if (!result.ok) return { ok: false, error: result.error, ...(blockers ? { blockers } : {}) };
  revalidatePath(`/produtos/${productId}`);
  return { ok: true };
}

export async function archiveProductAction(productId: string): Promise<ActionResult> {
  const result = await staffAction(async (token) =>
    unwrap(
      await catalog(token).POST("/v1/admin/products/{product_id}/archive", {
        params: { path: { product_id: productId } },
      }),
    ),
  );
  if (!result.ok) return failureResult(result);
  revalidatePath(`/produtos/${productId}`);
  return { ok: true };
}
