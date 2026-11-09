import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = fileURLToPath(new URL("..", import.meta.url));
const DASHES = /[\u2013\u2014]/;

function sourceFiles(dir: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) found.push(...sourceFiles(full));
    else if (/\.(tsx?|md)$/.test(entry) && !/\.test\.tsx?$/.test(entry)) found.push(full);
  }
  return found;
}

describe("regra: sem travessão em texto de interface", () => {
  const files = ["app", "components", "content", "lib"].flatMap((dir) =>
    sourceFiles(path.join(root, dir)),
  );

  it("varre os diretórios esperados", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it.each(files.map((file) => [path.relative(root, file), file] as const))(
    "%s não contém travessão (em ou en)",
    (_name, file) => {
      expect(readFileSync(file, "utf8")).not.toMatch(DASHES);
    },
  );
});

describe("páginas legais", () => {
  it.each(["privacidade", "termos"])("content/%s.md existe e traz o aviso de modelo", (name) => {
    const file = path.join(root, "content", `${name}.md`);
    expect(existsSync(file)).toBe(true);
    expect(readFileSync(file, "utf8")).toContain("Modelo para loja demonstrativa");
  });

  it("privacidade cobre dados, finalidade, base legal, direitos e contato", () => {
    const text = readFileSync(path.join(root, "content", "privacidade.md"), "utf8");
    for (const part of [
      "KatoShop (loja demonstrativa)",
      "nome",
      "email",
      "endereço",
      "Finalidade",
      "Base legal",
      "Direitos do titular",
      "privacidade@katoshop.localhost",
    ]) {
      expect(text).toContain(part);
    }
  });

  it("termos cobrem cadastro, preços, trocas em 30 dias e foro", () => {
    const text = readFileSync(path.join(root, "content", "termos.md"), "utf8");
    for (const part of ["Cadastro", "Preços", "30 dias", "Foro"]) expect(text).toContain(part);
  });

  it("manifest, ícones e páginas existem", () => {
    for (const file of [
      "app/manifest.ts",
      "app/icon.svg",
      "app/apple-icon.png",
      "app/not-found.tsx",
      "app/error.tsx",
      "app/global-error.tsx",
      "app/(shop)/privacidade/page.tsx",
      "app/(shop)/termos/page.tsx",
      "app/(shop)/creditos/page.tsx",
    ]) {
      expect(existsSync(path.join(root, file)), file).toBe(true);
    }
  });
});
