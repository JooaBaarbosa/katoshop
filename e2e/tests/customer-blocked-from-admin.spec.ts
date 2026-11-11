import { expect, test } from "@playwright/test";
import { ADMIN_URL, adminLogin, newCustomer, registerCustomer } from "./support";

test("cliente não entra no admin: mesma mensagem de credencial inválida", async ({ page }) => {
  const customer = newCustomer("admin");
  await registerCustomer(page, customer);

  await adminLogin(page, customer.email, customer.password);

  // o formulário mostra o erro (o anunciador de rotas do Next também tem role=alert)
  await expect(page.locator("form").getByRole("alert")).toHaveText("Email ou senha incorretos.");
  await expect(page).toHaveURL(new RegExp(`^${ADMIN_URL}/entrar(\\?|$)`));
});
