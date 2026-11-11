import { expect, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_URL, API_URL, adminLogin } from "./support";

type SeedImage = {
  url: string;
  alt: string;
  credit_author: string | null;
  credit_source_url: string | null;
  license: string | null;
};

/**
 * Foto real de um produto do seed, baixada de /v1/media pelo navegador (o Chromium resolve
 * *.localhost; o Node no Windows não), com os créditos para reenviar junto.
 */
async function seedPhoto(page: Page): Promise<{ image: SeedImage; body: Buffer }> {
  const detail = await page.goto(`${API_URL}/catalog/v1/products/camiseta-pesada-preta`);
  expect(detail?.ok()).toBe(true);
  const product = (await detail!.json()) as { images: SeedImage[] };
  const image = product.images[0];
  if (!image) throw new Error("o produto do seed não tem foto; rode pnpm seed");
  expect(image.url).toContain("/v1/media/");
  const media = await page.goto(image.url);
  expect(media?.ok()).toBe(true);
  return { image, body: await media!.body() };
}

test("produto criado no admin aparece na busca da loja", async ({ page, context }) => {
  test.setTimeout(240_000);
  const stamp = Date.now();
  const name = `Camiseta E2E ${stamp}`;

  const helper = await context.newPage();
  const photo = await seedPhoto(helper);
  await helper.close();

  await adminLogin(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await expect(page).toHaveURL(`${ADMIN_URL}/`);

  // Dados: nasce como rascunho em Camisetas
  await page.goto(`${ADMIN_URL}/produtos/novo`);
  await page.getByLabel("Nome", { exact: true }).fill(name);
  await page.getByRole("combobox", { name: "Categoria" }).click();
  await page.getByRole("option", { name: "Camisetas", exact: true }).click();
  await page.getByLabel("Preço base (R$)").fill("119,90");
  await page.getByRole("button", { name: "Criar produto" }).click();
  await expect(page).toHaveURL(/\/produtos\/[0-9a-f-]{36}$/);
  const productUrl = page.url();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();

  // Variantes: Preto x (P, M)
  await page.getByRole("tab", { name: "Variantes" }).click();
  await page.getByRole("checkbox", { name: "Preto", exact: true }).click();
  await page.getByRole("checkbox", { name: "P", exact: true }).click();
  await page.getByRole("checkbox", { name: "M", exact: true }).click();
  await page.getByRole("button", { name: "Gerar variantes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Grade gerada." })).toBeVisible();
  const grid = page.getByRole("table", { name: /Variantes por cor e tamanho/ });
  await expect(grid.getByRole("row")).toHaveCount(3); // cabeçalho + 2 variantes

  // Estoque: ajuste de P para 3
  await grid.getByRole("link", { name: "Estoque de Preto P" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Estoque Preto P" })).toBeVisible();
  await page.getByLabel("Quantidade (use - para retirar)").fill("3");
  await page.getByRole("button", { name: "Registrar ajuste" }).click();
  await expect(page.getByRole("status")).toHaveText("Ajuste registrado. Disponível agora: 3.");
  const ledger = page.getByRole("table", { name: /Movimentos de estoque/ });
  await expect(ledger.getByRole("row").nth(1)).toContainText("+3");

  // Fotos: reenvia a foto do seed com texto alternativo e créditos
  await page.goto(`${productUrl}?aba=fotos`);
  await page.getByLabel("Arquivos").setInputFiles({
    name: "camiseta-e2e.jpg",
    mimeType: "image/jpeg",
    buffer: photo.body,
  });
  await page.getByLabel("Texto alternativo (obrigatório)").fill(photo.image.alt);
  await page.getByLabel("Autor").fill(photo.image.credit_author ?? "");
  await page.getByLabel("URL de origem").fill(photo.image.credit_source_url ?? "");
  await page.getByLabel("Licença").fill(photo.image.license ?? "");
  await page.getByRole("button", { name: "Enviar fotos" }).click();
  const selected = page.getByRole("list", { name: "Fotos selecionadas" });
  await expect(selected.getByRole("status")).toHaveText("Enviada");
  await expect(page.getByRole("list", { name: /Ordem das fotos/ }).getByRole("img")).toHaveCount(1);

  // Publicação: checklist completo e publicar
  await page.getByRole("tab", { name: "Publicação" }).click();
  const checklist = page.getByRole("list", { name: "Requisitos para publicar" });
  await expect(checklist).not.toContainText("Pendente");
  await page.getByRole("button", { name: "Publicar" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Produto publicado." })).toBeVisible();

  // Loja: o catálogo guarda as buscas por até 60 s (R21), então espera até 70 s
  const card = page.getByRole("main").getByRole("link", { name, exact: true });
  await expect
    .poll(
      async () => {
        await page.goto(`/busca?q=${encodeURIComponent(`E2E ${stamp}`)}`);
        return card.count();
      },
      { timeout: 70_000, intervals: [2_000, 5_000] },
    )
    .toBe(1);
  await expect(card).toHaveAttribute("href", /^\/p\/camiseta-e2e-/);
});
