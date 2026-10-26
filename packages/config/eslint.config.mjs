import js from "@eslint/js";
import tseslint from "typescript-eslint";

// Base compartilhada. As apps Next.js estendem com eslint-config-next.
// Regras tipadas só valem para arquivos TS; quem usa precisa de um tsconfig.json no pacote.
export default [
  { ignores: ["**/node_modules/**", "**/.next/**", "**/dist/**", "**/.turbo/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked.map((config) => ({
    ...config,
    files: ["**/*.{ts,tsx,mts,cts}"],
  })),
  {
    files: ["**/*.{ts,tsx,mts,cts}"],
    languageOptions: { parserOptions: { projectService: true } },
  },
];
