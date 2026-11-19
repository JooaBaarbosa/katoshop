import { expect, test } from "@playwright/test";
import { healVariant, SEED, seedPrice } from "./seed-reference";
import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  ADMIN_URL,
  addToCart,
  adminLogin,
  brl,
  openApi,
  staffToken,
  summaryValue,
} from "./support";

// Camiseta pesada preta está em "Básicos pesados"; o boné não está.
const IN_COLLECTION = SEED.camisetaPretaM;
const OUTSIDE = SEED.boneCinzaM;

test("cupom do admin restrito à coleção desconta só o item da coleção", async ({
  page,
  context,
  browser,
}) => {
  test.setTimeout(120_000);
  // os totais usam os preços do seed: cura sobras de uma execução interrompida antes
  const api = await openApi(context);
  const token = await staffToken(api);
  await healVariant(api, token, IN_COLLECTION);
  await healVariant(api, token, OUTSIDE);
  await api.close();
  // o archive_test_data desativa os E2E-* depois (R26)
  const code = `E2E-COL-${Date.now()}`;

  await adminLogin(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await expect(page).toHaveURL(`${ADMIN_URL}/`);
  await page.goto(`${ADMIN_URL}/cupons/novo`);
  await page.getByLabel("Código", { exact: true }).fill(code);
  await page.getByLabel("Valor", { exact: true }).fill("15");
  await page.getByLabel("Descrição interna").fill("Cupom de teste e2e por coleção");
  await page.getByRole("group", { name: "Coleções" }).getByLabel("Básicos pesados").check();
  await page.getByRole("button", { name: "Criar cupom" }).click();
  await expect(page).toHaveURL(/\/cupons\?aviso=criado$/);
  await expect(page.getByRole("main").getByText(code)).toBeVisible();

  // um item da coleção e um de fora: o desconto (15%) é só sobre o da coleção
  const store = await browser.newContext({ locale: "pt-BR" });
  const shopper = await store.newPage();
  await addToCart(shopper, IN_COLLECTION.slug, IN_COLLECTION.color, IN_COLLECTION.size);
  await addToCart(shopper, OUTSIDE.slug, OUTSIDE.color, OUTSIDE.size);
  await shopper.goto("/carrinho");
  await shopper.getByLabel("Cupom", { exact: true }).fill(code.toLowerCase());
  await shopper.getByRole("button", { name: "Aplicar" }).click();
  const discount = Math.round((seedPrice(IN_COLLECTION) * 15) / 100);
  await expect(summaryValue(shopper, "Desconto")).toHaveText(`− ${brl(discount)}`);
  await expect(summaryValue(shopper, "Total")).toHaveText(
    brl(seedPrice(IN_COLLECTION) + seedPrice(OUTSIDE) - discount),
  );
  await store.close();

  // só o item de fora: o cupom é recusado com o motivo
  const other = await browser.newContext({ locale: "pt-BR" });
  const outsider = await other.newPage();
  await addToCart(outsider, OUTSIDE.slug, OUTSIDE.color, OUTSIDE.size);
  await outsider.goto("/carrinho");
  await outsider.getByLabel("Cupom", { exact: true }).fill(code);
  await outsider.getByRole("button", { name: "Aplicar" }).click();
  await expect(outsider.getByText("Nenhum item do carrinho vale para este cupom.")).toBeVisible();
  await expect(summaryValue(outsider, "Desconto")).toHaveText(brl(0));
  await other.close();
});
