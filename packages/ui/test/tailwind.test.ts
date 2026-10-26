import { readFileSync } from "node:fs";
import { join } from "node:path";
import { compile } from "@tailwindcss/node";
import { describe, expect, it } from "vitest";

const stylesDir = join(import.meta.dirname, "..", "src", "styles");

async function build(file: string, candidates: string[]): Promise<string> {
  const compiler = await compile(readFileSync(join(stylesDir, file), "utf8"), {
    base: stylesDir,
    onDependency: () => {},
  });
  return compiler.build(candidates);
}

const candidates = [
  "rounded-[var(--radius)]",
  "bg-accent",
  "text-ks-fg",
  "font-display",
  "font-sans",
  "font-mono",
];

describe.each(["globals-store.css", "globals-admin.css"])("Tailwind compila %s", (file) => {
  it("emite tokens, utilitários e mapeamento de fontes", async () => {
    const css = await build(file, candidates);
    expect(css).toContain("--radius: 2px");
    expect(css).toContain("--duration-fast: 150ms");
    for (const [name, value] of [
      ["bg", "#0e0e0e"],
      ["surface", "#1e1e1e"],
      ["border", "#2a2a2a"],
      ["fg", "#f4f4f0"],
      ["muted", "#a9a9a4"],
      ["accent", "#d7ff3a"],
      ["accent-on-light", "#9dbf00"],
      ["admin-bg", "#f7f7f4"],
      ["admin-sidebar", "#0e0e0e"],
    ] as const) {
      expect(css).toContain(`--color-${name}: ${value}`);
    }
    expect(css).toContain(String.raw`.rounded-\[var\(--radius\)\]`);
    expect(css).toContain("var(--font-anton-nf)");
    expect(css).toContain("var(--font-inter-nf)");
    expect(css).toContain("var(--font-jetbrains-nf)");
    expect(css).toMatch(/\.font-sans \{[^}]*var\(--font-inter-nf\)/);
    expect(css).toMatch(/\.font-mono \{[^}]*var\(--font-jetbrains-nf\)/);
    expect(css).toMatch(/\.font-display \{[^}]*var\(--font-anton-nf\)/);
    expect(css).toContain('[data-theme="admin"]');
  });
});
