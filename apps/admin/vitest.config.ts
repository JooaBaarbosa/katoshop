import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    // "server-only" lança fora do runtime do React Server Components; nos testes vira no-op.
    alias: { "server-only": fileURLToPath(new URL("./test/server-only-stub.ts", import.meta.url)) },
  },
  test: { include: ["test/**/*.test.ts"], environment: "node" },
});
