import js from "@eslint/js";

// Base mínima. As apps Next.js estendem com eslint-config-next (que traz as regras de TypeScript).
export default [
  { ignores: ["**/node_modules/**", "**/.next/**", "**/dist/**", "**/.turbo/**"] },
  js.configs.recommended,
];
