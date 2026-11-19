import { expect, test } from "@playwright/test";
import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  ADMIN_URL,
  addToCart,
  adminLogin,
  brl,
  summaryValue,
} from "./support";

// Camiseta pesada preta está em "Básicos pesados"; o boné não está.
const IN_COLLECTION = { slug: "camiseta-pesada-preta", cents: 12900 };
const OUTSIDE = { slug: "bone-lavado-cinza", cents: 11900 };

test("cupom do admin restrito à coleção desconta só o item da coleção", async ({
  page,
  browser,
}) => {
  test.setTimeout(120_000);
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
  await addToCart(shopper, IN_COLLECTION.slug, "PRT", "M");
  await addToCart(shopper, OUTSIDE.slug, "CNZ", "M");
  await shopper.goto("/carrinho");
  await shopper.getByLabel("Cupom", { exact: true }).fill(code.toLowerCase());
  await shopper.getByRole("button", { name: "Aplicar" }).click();
  const discount = Math.round((IN_COLLECTION.cents * 15) / 100);
  await expect(summaryValue(shopper, "Desconto")).toHaveText(`− ${brl(discount)}`);
  await expect(summaryValue(shopper, "Total")).toHaveText(
    brl(IN_COLLECTION.cents + OUTSIDE.cents - discount),
  );
  await store.close();

  // só o item de fora: o cupom é recusado com o motivo
  const other = await browser.newContext({ locale: "pt-BR" });
  const outsider = await other.newPage();
  await addToCart(outsider, OUTSIDE.slug, "CNZ", "M");
  await outsider.goto("/carrinho");
  await outsider.getByLabel("Cupom", { exact: true }).fill(code);
  await outsider.getByRole("button", { name: "Aplicar" }).click();
  await expect(outsider.getByText("Nenhum item do carrinho vale para este cupom.")).toBeVisible();
  await expect(summaryValue(outsider, "Desconto")).toHaveText(brl(0));
  await other.close();
});
