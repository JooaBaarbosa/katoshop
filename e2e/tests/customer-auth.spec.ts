import { expect, test } from "@playwright/test";
import { newCustomer, registerCustomer } from "./support";

test("cria conta, vê o nome em /conta, sai e /conta volta para /entrar", async ({ page }) => {
  const customer = newCustomer("auth");

  await registerCustomer(page, customer);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(`Olá, ${customer.name}`);

  await page.getByRole("button", { name: "Sair", exact: true }).click();
  await expect(page).not.toHaveURL(/\/conta$/);

  await page.goto("/conta");
  await expect(page).toHaveURL(/\/entrar(\?|$)/);
  await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
});
