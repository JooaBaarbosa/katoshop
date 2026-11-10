import { beforeEach, describe, expect, it, vi } from "vitest";

class RedirectSignal extends Error {
  constructor(readonly url: string) {
    super(`redirect:${url}`);
  }
}

const mocks = vi.hoisted(() => ({
  meGet: vi.fn(),
  identity: vi.fn(),
  catalog: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
  withAuth: vi.fn(),
  clear: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  redirect: (url: string) => {
    throw new RedirectSignal(url);
  },
}));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("../lib/api", () => ({ identity: mocks.identity, catalog: mocks.catalog }));
vi.mock("../lib/session", () => ({
  session: { withAuth: mocks.withAuth, clear: mocks.clear },
}));

const products = await import("../app/(painel)/produtos/[id]/actions");
const stock = await import("../app/(painel)/produtos/[id]/variantes/[vid]/estoque/actions");
const categories = await import("../app/(painel)/categorias/actions");
const collections = await import("../app/(painel)/colecoes/actions");

const STAFF = { id: "u1", email: "a@k.localhost", name: "Admin", kind: "staff", roles: ["admin"] };
const PID = "0190a000-0000-7000-8000-000000000001";

function ok<T>(data: T, status = 200) {
  return { data, error: undefined, response: new Response(null, { status }) };
}

function problem(status: number, body: Record<string, unknown>) {
  return { data: undefined, error: body, response: new Response(null, { status }) };
}

function form(fields: Record<string, string | string[] | File>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (Array.isArray(value)) for (const item of value) data.append(key, item);
    else data.set(key, value);
  }
  return data;
}

async function redirectOf(promise: Promise<unknown>): Promise<string> {
  const error = await promise.then(
    () => null,
    (e: unknown) => e,
  );
  if (!(error instanceof RedirectSignal)) throw new Error(`esperava redirect, veio ${String(error)}`);
  return error.url;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.identity.mockReturnValue({ GET: mocks.meGet });
  mocks.meGet.mockResolvedValue(ok(STAFF));
  mocks.catalog.mockReturnValue({
    GET: mocks.get,
    POST: mocks.post,
    PATCH: mocks.patch,
    PUT: mocks.put,
    DELETE: mocks.del,
  });
  mocks.withAuth.mockImplementation((fn: (token: string) => Promise<unknown>) => fn("at"));
});

const PRODUCT_FIELDS = {
  id: PID,
  version: "3",
  name: "Moletom Kato",
  slug: "moletom-kato",
  description: "Peluciado.",
  category_id: "cat-1",
  base_price: "249,90",
  attributes: "Composição: algodão",
};

describe("updateProductAction (Dados)", () => {
  it("envia a versão lida e os campos com preço em centavos", async () => {
    mocks.patch.mockResolvedValue(ok({ id: PID, version: 4 }));

    const state = await products.updateProductAction(null, form(PRODUCT_FIELDS));

    expect(state).toMatchObject({ ok: true });
    expect(mocks.catalog).toHaveBeenCalledWith("at");
    expect(mocks.patch).toHaveBeenCalledWith("/v1/admin/products/{product_id}", {
      params: { path: { product_id: PID } },
      body: {
        version: 3,
        name: "Moletom Kato",
        slug: "moletom-kato",
        description: "Peluciado.",
        category_id: "cat-1",
        base_price_cents: 24990,
        attributes: { Composição: "algodão" },
      },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/produtos/${PID}`);
  });

  it("409 de versão devolve o código e a mensagem para o botão Recarregar", async () => {
    mocks.patch.mockResolvedValue(
      problem(409, { code: "catalog.product.version_conflict", title: "Conflito" }),
    );

    const state = await products.updateProductAction(null, form(PRODUCT_FIELDS));

    expect(state).toMatchObject({
      ok: false,
      code: "catalog.product.version_conflict",
      formError: "Este produto foi alterado por outra pessoa. Recarregue para ver a versão atual.",
    });
  });

  it("endereço vazio fica fora do PATCH (slug não aceita null na edição)", async () => {
    mocks.patch.mockResolvedValue(ok({ id: PID, version: 4 }));

    await products.updateProductAction(null, form({ ...PRODUCT_FIELDS, slug: "  " }));

    const [, init] = mocks.patch.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(init.body).not.toHaveProperty("slug");
    expect(init.body).toMatchObject({ version: 3, name: "Moletom Kato" });
  });

  it("preço inválido não chama a API", async () => {
    const state = await products.updateProductAction(
      null,
      form({ ...PRODUCT_FIELDS, base_price: "abc", name: " " }),
    );

    expect(state).toMatchObject({
      ok: false,
      fieldErrors: { base_price: "Informe um preço válido, como 129,90.", name: "Informe o nome." },
    });
    expect(mocks.patch).not.toHaveBeenCalled();
  });

  it("rejeita sem sessão de funcionário (401 vai ao login, nada é gravado)", async () => {
    const { ApiProblem } = await import("@katoshop/api-client");
    mocks.withAuth.mockRejectedValue(
      new ApiProblem({ status: 401, code: "auth.missing_token", message: "Não autenticado" }),
    );

    expect(await redirectOf(products.updateProductAction(null, form(PRODUCT_FIELDS)))).toBe(
      "/entrar",
    );
    expect(mocks.patch).not.toHaveBeenCalled();
  });

  it("403 de permissão mostra a mensagem sem deslogar", async () => {
    mocks.patch.mockResolvedValue(
      problem(403, {
        code: "auth.insufficient_permission",
        title: "Permissão insuficiente",
        detail: "Requer catalog.write.",
      }),
    );

    const state = await products.updateProductAction(null, form(PRODUCT_FIELDS));

    expect(state).toMatchObject({ formError: "Você não tem permissão para esta ação." });
    expect(mocks.clear).not.toHaveBeenCalled();
  });
});

describe("createProductAction", () => {
  it("cria e abre a página do produto", async () => {
    mocks.post.mockResolvedValue(ok({ id: PID }, 201));
    const fields: Record<string, string> = { ...PRODUCT_FIELDS };
    delete fields.id;
    delete fields.version;

    const url = await redirectOf(products.createProductAction(null, form({ ...fields, slug: "" })));

    expect(url).toBe(`/produtos/${PID}`);
    expect(mocks.post).toHaveBeenCalledWith("/v1/admin/products", {
      body: {
        name: "Moletom Kato",
        slug: null,
        description: "Peluciado.",
        category_id: "cat-1",
        base_price_cents: 24990,
        attributes: { Composição: "algodão" },
      },
    });
  });

  it("sem categoria não chama a API", async () => {
    const state = await products.createProductAction(
      null,
      form({ name: "X", base_price: "10", category_id: "" }),
    );

    expect(state).toMatchObject({ fieldErrors: { category_id: "Escolha a categoria." } });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("slug repetido aparece no campo do endereço", async () => {
    mocks.post.mockResolvedValue(problem(409, { code: "catalog.product.slug_taken" }));

    const state = await products.createProductAction(
      null,
      form({ name: "X", base_price: "10", category_id: "c", slug: "x" }),
    );

    expect(state).toMatchObject({
      ok: false,
      fieldErrors: { slug: "Já existe um produto com este endereço." },
    });
  });
});

describe("variantes", () => {
  it("gera a grade com as cores e tamanhos marcados", async () => {
    mocks.post.mockResolvedValue(ok({ id: PID }));

    const state = await products.generateVariantsAction(
      null,
      form({ product_id: PID, colors: ["PRT"], sizes: ["P", "M"] }),
    );

    expect(state).toMatchObject({ ok: true });
    expect(mocks.post).toHaveBeenCalledWith("/v1/admin/products/{product_id}/variants/generate", {
      params: { path: { product_id: PID } },
      body: { colors: ["PRT"], sizes: ["P", "M"] },
    });
  });

  it("sem cor ou tamanho marcado não chama a API", async () => {
    const state = await products.generateVariantsAction(
      null,
      form({ product_id: PID, colors: ["PRT"] }),
    );

    expect(state).toMatchObject({ ok: false, formError: "Marque pelo menos uma cor e um tamanho." });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("atualiza preço (vazio = preço base) e ativo com a versão da variante", async () => {
    mocks.patch.mockResolvedValue(ok({ id: "v1", version: 2 }));

    const result = await products.updateVariantAction({
      productId: PID,
      variantId: "v1",
      version: 1,
      price: "",
      active: false,
    });

    expect(result).toMatchObject({ ok: true });
    expect(mocks.patch).toHaveBeenCalledWith("/v1/admin/variants/{variant_id}", {
      params: { path: { variant_id: "v1" } },
      body: { version: 1, price_cents: null, active: false },
    });
  });
});

describe("fotos", () => {
  it("repassa o FormData do arquivo para a API sem serializar como JSON", async () => {
    mocks.post.mockResolvedValue(ok({ id: "img1" }, 201));
    const file = new File([new Uint8Array([1, 2, 3])], "foto.jpg", { type: "image/jpeg" });

    const result = await products.uploadImageAction(
      PID,
      form({ file, alt: "Moletom preto dobrado", color_code: "PRT", credit_author: "Ana" }),
    );

    expect(result).toMatchObject({ ok: true });
    const [path, init] = mocks.post.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe("/v1/admin/products/{product_id}/images");
    expect(init.params).toEqual({ path: { product_id: PID } });
    const body = init.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("alt")).toBe("Moletom preto dobrado");
    expect(body.get("color_code")).toBe("PRT");
    expect((body.get("file") as File).name).toBe("foto.jpg");
    expect(body.has("license")).toBe(false);
    const serializer = init.bodySerializer as (b: FormData) => unknown;
    expect(serializer(body)).toBe(body);
  });

  it("alt vazio não envia", async () => {
    const file = new File([new Uint8Array([1])], "foto.jpg", { type: "image/jpeg" });

    const result = await products.uploadImageAction(PID, form({ file, alt: "  " }));

    expect(result).toMatchObject({ ok: false, error: "Descreva a imagem no texto alternativo." });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("413 da API vira a mensagem de 8 MB", async () => {
    mocks.post.mockResolvedValue(problem(413, { code: "catalog.image.too_large" }));
    const file = new File([new Uint8Array([1])], "grande.jpg", { type: "image/jpeg" });

    const result = await products.uploadImageAction(PID, form({ file, alt: "x" }));

    expect(result).toMatchObject({ ok: false, error: "A imagem passa de 8 MB." });
  });

  it.each([
    ["none", null],
    ["", null],
    ["PRT", "PRT"],
  ])("editar foto com cor %j envia color_code %j", async (color, expected) => {
    mocks.patch.mockResolvedValue(ok({ id: "img1" }));

    const state = await products.updateImageAction(
      null,
      form({ product_id: PID, image_id: "img1", alt: "Foto", color_code: color }),
    );

    expect(state).toMatchObject({ ok: true });
    expect(mocks.patch).toHaveBeenCalledWith("/v1/admin/images/{image_id}", {
      params: { path: { image_id: "img1" } },
      body: {
        alt: "Foto",
        color_code: expected,
        credit_author: null,
        credit_source_url: null,
        license: null,
      },
    });
  });

  it("reordena gravando só as posições que mudaram", async () => {
    mocks.get.mockResolvedValue(
      ok({
        id: PID,
        images: [
          { id: "a", position: 0 },
          { id: "b", position: 1 },
          { id: "c", position: 2 },
        ],
      }),
    );
    mocks.patch.mockResolvedValue(ok({}));

    const result = await products.reorderImagesAction(PID, ["a", "c", "b"]);

    expect(result).toMatchObject({ ok: true });
    expect(mocks.patch).toHaveBeenCalledTimes(2);
    expect(mocks.patch).toHaveBeenCalledWith("/v1/admin/images/{image_id}", {
      params: { path: { image_id: "c" } },
      body: { position: 1 },
    });
    expect(mocks.patch).toHaveBeenCalledWith("/v1/admin/images/{image_id}", {
      params: { path: { image_id: "b" } },
      body: { position: 2 },
    });
  });
});

describe("publicação", () => {
  it("422 not_publishable devolve a lista de pendências", async () => {
    mocks.post.mockResolvedValue(
      problem(422, {
        code: "catalog.product.not_publishable",
        errors: { product: ["no_image"] },
      }),
    );

    const result = await products.publishProductAction(PID);

    expect(result).toMatchObject({ ok: false, blockers: ["Envie pelo menos uma foto."] });
  });

  it("arquiva e revalida a página", async () => {
    mocks.post.mockResolvedValue(ok({ id: PID, status: "archived" }));

    expect(await products.archiveProductAction(PID)).toMatchObject({ ok: true });
    expect(mocks.post).toHaveBeenCalledWith("/v1/admin/products/{product_id}/archive", {
      params: { path: { product_id: PID } },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/produtos/${PID}`);
  });
});

describe("adjustStockAction", () => {
  const FIELDS = { product_id: PID, variant_id: "v1", delta: "-2", reason: "damage", note: "Rasgo" };

  it("envia delta, motivo e nota", async () => {
    mocks.post.mockResolvedValue(ok({ movement: {}, variant: {} }, 201));

    const state = await stock.adjustStockAction(null, form(FIELDS));

    expect(state).toMatchObject({ ok: true });
    expect(mocks.post).toHaveBeenCalledWith("/v1/admin/variants/{variant_id}/stock-adjustments", {
      params: { path: { variant_id: "v1" } },
      body: { delta: -2, reason: "damage", note: "Rasgo" },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/produtos/${PID}/variantes/v1/estoque`);
  });

  it("motivo fora da lista e delta zero não chamam a API", async () => {
    const state = await stock.adjustStockAction(
      null,
      form({ ...FIELDS, delta: "0", reason: "sale" }),
    );

    expect(state).toMatchObject({
      fieldErrors: {
        delta: "Informe um número inteiro diferente de zero.",
        reason: "Escolha um motivo.",
      },
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("saldo negativo mostra a mensagem do catálogo", async () => {
    mocks.post.mockResolvedValue(problem(409, { code: "catalog.stock.would_go_negative" }));

    const state = await stock.adjustStockAction(null, form(FIELDS));

    expect(state).toMatchObject({ formError: "O estoque não pode ficar negativo." });
  });
});

describe("categorias", () => {
  it("excluir categoria com produtos mostra a mensagem", async () => {
    mocks.del.mockResolvedValue(problem(409, { code: "catalog.category.in_use" }));

    const result = await categories.deleteCategoryAction("cat-1");

    expect(result).toMatchObject({ ok: false, error: "Há produtos nesta categoria." });
  });

  it("cria categoria com pai opcional", async () => {
    mocks.post.mockResolvedValue(ok({ id: "c2" }, 201));

    const state = await categories.saveCategoryAction(
      null,
      form({ name: "Moletons", slug: "", parent_id: "none", position: "2" }),
    );

    expect(state).toMatchObject({ ok: true });
    expect(mocks.post).toHaveBeenCalledWith("/v1/admin/categories", {
      body: { name: "Moletons", slug: null, parent_id: null, position: 2 },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/categorias");
  });

  it("ciclo de pai aparece no campo Categoria pai", async () => {
    mocks.patch.mockResolvedValue(problem(422, { code: "catalog.category.parent_cycle" }));

    const state = await categories.saveCategoryAction(
      null,
      form({ id: "c1", name: "A", slug: "a", parent_id: "c2", position: "0" }),
    );

    expect(state).toMatchObject({
      ok: false,
      fieldErrors: {
        parent_id: "Uma categoria não pode ficar dentro dela mesma nem de uma subcategoria sua.",
      },
    });
    expect(mocks.patch).toHaveBeenCalledWith("/v1/admin/categories/{category_id}", {
      params: { path: { category_id: "c1" } },
      body: { name: "A", slug: "a", parent_id: "c2", position: 0 },
    });
  });
});

describe("endereço vazio na edição de categoria e coleção", () => {
  it("categoria: slug vazio fica fora do PATCH", async () => {
    mocks.patch.mockResolvedValue(ok({ id: "c1" }));

    await categories.saveCategoryAction(
      null,
      form({ id: "c1", name: "A", slug: "", parent_id: "none", position: "0" }),
    );

    expect(mocks.patch).toHaveBeenCalledWith("/v1/admin/categories/{category_id}", {
      params: { path: { category_id: "c1" } },
      body: { name: "A", parent_id: null, position: 0 },
    });
  });

  it("coleção: slug vazio fica fora do PATCH", async () => {
    mocks.patch.mockResolvedValue(ok({ id: "col1" }));

    await collections.saveCollectionAction(
      null,
      form({ id: "col1", name: "Inverno", slug: "", description: "", position: "0" }),
    );

    expect(mocks.patch).toHaveBeenCalledWith("/v1/admin/collections/{collection_id}", {
      params: { path: { collection_id: "col1" } },
      body: { name: "Inverno", description: null, featured: false, position: 0 },
    });
  });
});

describe("coleções", () => {
  it("grava a ordem dos produtos com PUT", async () => {
    mocks.put.mockResolvedValue(ok({ id: "col1", product_ids: ["p2", "p1"] }));

    const result = await collections.setCollectionProductsAction("col1", ["p2", "p1"]);

    expect(result).toMatchObject({ ok: true });
    expect(mocks.put).toHaveBeenCalledWith("/v1/admin/collections/{collection_id}/products", {
      params: { path: { collection_id: "col1" } },
      body: { product_ids: ["p2", "p1"] },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/colecoes/col1");
  });

  it("cria coleção e abre a página dela", async () => {
    mocks.post.mockResolvedValue(ok({ id: "col9" }, 201));

    const url = await redirectOf(
      collections.saveCollectionAction(
        null,
        form({ name: "Inverno", slug: "", description: "", featured: "on", position: "1" }),
      ),
    );

    expect(url).toBe("/colecoes/col9");
    expect(mocks.post).toHaveBeenCalledWith("/v1/admin/collections", {
      body: { name: "Inverno", slug: null, description: null, featured: true, position: 1 },
    });
  });
});
