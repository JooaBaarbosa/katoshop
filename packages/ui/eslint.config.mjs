import base from "@katoshop/config/eslint";
import globals from "globals";

export default [
  ...base,
  { files: ["scripts/**/*.mjs"], languageOptions: { globals: globals.node } },
  { ignores: ["src/brand/generated/**"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { parserOptions: { tsconfigRootDir: import.meta.dirname } },
  },
];
