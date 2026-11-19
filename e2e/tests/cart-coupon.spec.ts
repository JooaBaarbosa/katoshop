import { expect, test } from "@playwright/test";
import { addToCart, brl, cartLine, summaryValue } from "./support";

// Dois produtos do seed: 129,90 + 69,90 = 198,80, acima do mínimo de 150,00 do BEMVINDO10.
const SHIRT = {
  slug: "camiseta-pesada-preta",
  name: "Camiseta pesada preta",
  cents: 12900,
};
const SOCK = {
  slug: "meia-cano-medio-branca",
  name: "Meia cano médio branca",
  cents: 6900,
};

test("visitante aplica bemvindo10 em minúsculas e o total é o subtotal menos 10%", async ({
  page,
}) => {
  await addToCart(page, SHIRT.slug, "PRT", "M");
  await addToCart(page, SOCK.slug, "BRC", "M");

  await page.goto("/carrinho");
  await expect(cartLine(page, SHIRT.name)).toBeVisible();
  await expect(cartLine(page, SOCK.name)).toBeVisible();
  const subtotal = SHIRT.cents + SOCK.cents;
  await expect(summaryValue(page, "Subtotal")).toHaveText(brl(subtotal));

  await page.getByLabel("Cupom", { exact: true }).fill("bemvindo10");
  await page.getByRole("button", { name: "Aplicar" }).click();

  const summary = page.getByRole("complementary", { name: "Resumo do pedido" });
  await expect(summary.getByText("BEMVINDO10", { exact: true })).toBeVisible();
  const discount = Math.round(subtotal / 10);
  await expect(summaryValue(page, "Desconto")).toHaveText(`− ${brl(discount)}`);
  await expect(summaryValue(page, "Total")).toHaveText(brl(subtotal - discount));
});
