import { expect, test } from "@playwright/test";

// Produto do seed com PRT esgotado no M e os outros tamanhos com estoque (Ruling R4).
const SOLD_OUT_PRODUCT = "/p/moletom-canguru-pesado?cor=PRT";

test("filtra moletons por M e Preto; tamanho esgotado fica indisponível", async ({ page }) => {
  await page.goto("/c/moletons");
  const filters = page.getByRole("complementary", { name: "Filtros" });
  await filters.locator('input[name="tamanho"][value="M"]').check();
  await filters.locator('input[name="cor"][value="PRT"]').check();
  await filters.getByRole("button", { name: "Aplicar filtros" }).click();
  await expect(page).toHaveURL(/[?&]tamanho=M(&|$)/);
  await expect(page).toHaveURL(/[?&]cor=PRT(&|$)/);

  // Os cards mostram a lista de cores (R5): todo card filtrado precisa incluir o Preto.
  const cards = page.getByRole("main").getByRole("article");
  await expect(cards.first()).toBeVisible();
  const total = await cards.count();
  expect(total).toBeGreaterThan(0);
  for (let i = 0; i < total; i++) {
    const colors = cards.nth(i).getByRole("list", { name: "Cores" });
    await expect(colors.getByRole("img", { name: "Preto", exact: true })).toBeVisible();
  }

  await page.goto(SOLD_OUT_PRODUCT);
  const sizes = page.getByRole("group", { name: /^Tamanho/ });
  await expect(sizes.getByRole("button", { name: "M esgotado" })).toHaveAttribute(
    "aria-disabled",
    "true",
  );
  // os outros tamanhos da mesma cor continuam escolhíveis
  await expect(sizes.getByRole("link", { name: "G", exact: true })).toBeVisible();
});
