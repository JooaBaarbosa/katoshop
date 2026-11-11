import { expect, type Page } from "@playwright/test";

export const ADMIN_URL = process.env.E2E_ADMIN_URL ?? "http://admin.katoshop.localhost";
export const API_URL = process.env.E2E_API_URL ?? "http://api.katoshop.localhost";

// Conta demo do bootstrap (Ruling R14); na CI vem do .env.example.
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@katoshop.localhost";
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "katoshop-demo-2026";

export type Customer = { name: string; email: string; password: string };

/** Cliente novo a cada execução: o volume local guarda as contas das execuções anteriores. */
export function newCustomer(tag: string): Customer {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  return {
    name: `Cliente ${tag} ${stamp}`,
    email: `cliente.${tag}.${stamp}@katoshop.localhost`,
    password: `e2e-${stamp}-senha-longa`,
  };
}

/** Cria a conta pela loja; termina em /conta, já logado. */
export async function registerCustomer(page: Page, customer: Customer): Promise<void> {
  await page.goto("/criar-conta");
  await page.getByLabel("Nome", { exact: true }).fill(customer.name);
  await page.getByLabel("Email", { exact: true }).fill(customer.email);
  await page.getByLabel("Senha", { exact: true }).fill(customer.password);
  await page.getByRole("button", { name: "Criar conta" }).click();
  await expect(page).toHaveURL(/\/conta$/);
}

/** Entra no painel com a conta demo (formulário de /entrar do admin). */
export async function adminLogin(page: Page, email: string, password: string): Promise<void> {
  await page.goto(`${ADMIN_URL}/entrar`);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}
