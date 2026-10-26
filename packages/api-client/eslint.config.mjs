import base from "@katoshop/config/eslint";

export default [
  ...base,
  { ignores: ["src/generated/**"] },
  {
    files: ["**/*.ts"],
    languageOptions: { parserOptions: { tsconfigRootDir: import.meta.dirname } },
  },
];
