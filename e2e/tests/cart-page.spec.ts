import { expect, type Page, test } from "@playwright/test";
import { healVariant, SEED, setStock } from "./seed-reference";
import {
  addToCart,
  brl,
  cartLine,
  expectQuantity,
  guestCart,
  openApi,
  staffToken,
  submit,
  summaryValue,
} from "./support";

// 129,90 por unidade: com 2 unidades o subtotal (259,80) passa do mínimo do BEMVINDO10.
const SHIRT = {
  slug: "camiseta-pesada-branca",
  name: "Camiseta pesada branca",
  cents: 12900,
};

/** −, +, cupom inválido, válido e remoção do cupom, e "Remover"; com ou sem JavaScript. */
async function exerciseCart(page: Page, js: boolean): Promise<void> {
  await addToCart(page, SHIRT.slug, "BRC", "M", js);
  await page.goto("/carrinho");
  const line = cartLine(page, SHIRT.name);
  await expectQuantity(line, 1);

  // depois de cada clique, o erro da linha vazio antes da quantidade (falha mostra o motivo)
  await submit(page, line.getByRole("button", { name: "Aumentar quantidade" }), js);
  await expectQuantity(line, 2);
  await submit(page, line.getByRole("button", { name: "Diminuir quantidade" }), js);
  await expectQuantity(line, 1);
  await submit(page, line.getByRole("button", { name: "Aumentar quantidade" }), js);
  await expectQuantity(line, 2);
  await expect(summaryValue(page, "Subtotal")).toHaveText(brl(2 * SHIRT.cents));

  // cupom inexistente: a mensagem em pt-BR e o código digitado volta no campo
  await page.getByLabel("Cupom", { exact: true }).fill("NAOEXISTE99");
  await submit(page, page.getByRole("button", { name: "Aplicar" }), js);
  await expect(page.getByText("Cupom não encontrado.")).toBeVisible();
  await expect(page.getByLabel("Cupom", { exact: true })).toHaveValue("NAOEXISTE99");

  await page.getByLabel("Cupom", { exact: true }).fill("BEMVINDO10");
  await submit(page, page.getByRole("button", { name: "Aplicar" }), js);
  const discount = Math.round((2 * SHIRT.cents) / 10);
  await expect(summaryValue(page, "Desconto")).toHaveText(`− ${brl(discount)}`);
  await expect(summaryValue(page, "Total")).toHaveText(brl(2 * SHIRT.cents - discount));

  await submit(page, page.getByRole("button", { name: "Remover cupom" }), js);
  await expect(page.getByLabel("Cupom", { exact: true })).toBeVisible();
  await expect(summaryValue(page, "Desconto")).toHaveText(brl(0));

  await submit(page, line.getByRole("button", { name: "Remover", exact: true }), js);
  await expect(page.getByText("Seu carrinho está vazio.")).toBeVisible();
}

test("carrinho com JavaScript: quantidade, cupom e remover leva o foco ao título", async ({
  page,
}) => {
  await exerciseCart(page, true);
  await expect(page.locator("#carrinho-titulo")).toBeFocused();
});

test.describe("sem JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("carrinho sem JavaScript: quantidade, cupom e remover", async ({ page }) => {
    await exerciseCart(page, false);
  });
});

test("estoque reduzido com a página aberta: o + mostra o aviso depois do refresh", async ({
  page,
  context,
}) => {
  const bermuda = SEED.bermudaCinzaM;
  const api = await openApi(context);
  try {
    const token = await staffToken(api);
    // começa do estoque do seed (uma execução interrompida pode ter deixado 2)
    const { variant } = await healVariant(api, token, bermuda);
    try {
      await addToCart(page, bermuda.slug, bermuda.color, bermuda.size);
      await page.goto("/carrinho");
      const line = cartLine(page, bermuda.name);
      const quantity = line.getByLabel("Quantidade", { exact: true });
      const plus = line.getByRole("button", { name: "Aumentar quantidade" });
      await plus.click();
      await expectQuantity(line, 2);

      // estoque absoluto de 2: a linha não é reduzida, mas o 3 passa do estoque
      await setStock(api, token, bermuda, 2, "Teste e2e: estoque desatualizado no carrinho");
      // espera o evento chegar ao cart; a página continua com o + habilitado (desatualizada)
      await expect
        .poll(
          async () =>
            (await guestCart(api, context)).items.find((i) => i.variant_id === variant.id)
              ?.available,
          { timeout: 15_000, intervals: [500, 1_000] },
        )
        .toBe(2);
      await expect(plus).toBeEnabled();
      await plus.click();

      // a mensagem chega no mesmo commit do refresh (a linha já com o estoque novo)
      await expect(line.getByText("Só temos 2 unidades desse tamanho.")).toBeVisible();
      await expect(quantity).toHaveText("2");
      await expect(plus).toBeDisabled();
    } finally {
      await healVariant(api, token, bermuda, { log: false });
    }
  } finally {
    await api.close();
  }
});
