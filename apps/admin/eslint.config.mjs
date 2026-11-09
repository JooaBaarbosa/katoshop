import base from "@katoshop/config/eslint";
import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...base,
  ...nextVitals,
  { ignores: ["next-env.d.ts"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { parserOptions: { tsconfigRootDir: import.meta.dirname } },
  },
];

export default config;
