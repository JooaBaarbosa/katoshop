import { expect, test } from "@playwright/test";
import { openApi } from "./support";

// Fronteiras do gateway (Traefik): barra codificada e rotas internas nunca chegam aos serviços.
test("gateway recusa barra codificada e esconde as rotas internas", async ({ context }) => {
  const api = await openApi(context);
  const variant = "01a1c5e9-34b7-7690-8550-db0207d95ffc";

  expect((await api.call("POST", "/identity/v1/auth%2Flogin", { body: {} })).status).toBe(400);
  expect((await api.call("GET", `/catalogv1/internal/variants/${variant}`)).status).toBe(404);
  expect((await api.call("GET", `/catalog/v1/internal/variants/${variant}`)).status).toBe(404);
  expect((await api.call("POST", "/identity/v1/auth/service-token", { body: {} })).status).toBe(
    404,
  );
  expect((await api.call("POST", "/promotions/v1/promotions/evaluate", { body: {} })).status).toBe(
    404,
  );
  await api.close();
});
