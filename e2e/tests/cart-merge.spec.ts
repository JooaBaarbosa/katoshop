import { expect, type Page, test } from "@playwright/test";
import { addToCart, type Customer, cartLine, newCustomer, registerCustomer } from "./support";

async function logout(page: Page): Promise<void> {
  await page.goto("/conta");
  await page.getByRole("button", { name: "Sair", exact: true }).click();
  await expect(page).not.toHaveURL(/\/conta$/);
}

async function login(page: Page, customer: Customer): Promise<void> {
  await page.goto("/entrar?next=/carrinho");
  await page.getByLabel("Email", { exact: true }).fill(customer.email);
  await page.getByLabel("Senha", { exact: true }).fill(customer.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/carrinho$/);
}

/** Conta com 1 unidade, sai, adiciona 1 da mesma variante como visitante e entra de novo. */
async function mergeSameVariant(
  page: Page,
  tag: string,
  slug: string,
  color: string,
  size: string,
): Promise<void> {
  const customer = newCustomer(tag);
  await registerCustomer(page, customer);
  await addToCart(page, slug, color, size);
  await logout(page);
  await addToCart(page, slug, color, size);
  await login(page, customer);
}

test("carrinho de visitante junta com o da conta no login: quantidade 2", async ({ page }) => {
  await mergeSameVariant(page, "merge", "meia-cano-medio-branca", "BRC", "P");
  const line = cartLine(page, "Meia cano médio branca");
  await expect(line.getByLabel("Quantidade", { exact: true })).toHaveText("2");
  await expect(page.getByText("Alguns itens foram ajustados ao juntar seu carrinho.")).toHaveCount(
    0,
  );
});

test("merge acima do estoque ajusta a quantidade e o aviso some com Entendi", async ({ page }) => {
  // XGG com 1 unidade no seed: 1 da conta + 1 do visitante passa do estoque
  await mergeSameVariant(page, "mergeajuste", "camiseta-manga-longa-preta", "PRT", "XGG");
  const flash = page.getByText("Alguns itens foram ajustados ao juntar seu carrinho.");
  await expect(flash).toBeVisible();
  const line = cartLine(page, "Camiseta manga longa preta");
  await expect(line.getByLabel("Quantidade", { exact: true })).toHaveText("1");
  await expect(
    line.getByText("Ajustamos a quantidade para 1, que é o que temos em estoque."),
  ).toBeVisible();

  // o aviso está na tela logo antes do clique: o toHaveCount(0) abaixo não é vazio
  await expect(flash).toBeVisible();
  await page.getByRole("button", { name: "Entendi" }).click();
  await expect(flash).toHaveCount(0);
});
