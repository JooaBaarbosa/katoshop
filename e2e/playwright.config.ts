import { defineConfig, devices } from "@playwright/test";

const CI = Boolean(process.env.CI);

/**
 * Roda contra o compose completo com o seed (pnpm dev:up && pnpm seed). Um worker só: toda
 * Server Action passa pelo limite por IP do Traefik (R24), então os fluxos andam em ritmo humano.
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_STORE_URL ?? "http://katoshop.localhost",
    locale: "pt-BR",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      // E2E_BROWSER_CHANNEL=chrome usa o Chrome instalado (máquinas que bloqueiam o binário
      // baixado pelo Playwright); sem ela, o Chromium do `playwright install`.
      use: { ...devices["Desktop Chrome"], channel: process.env.E2E_BROWSER_CHANNEL },
    },
  ],
});
