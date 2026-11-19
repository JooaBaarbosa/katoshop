import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

const ROOT = join(import.meta.dirname, "..");

describe("copy do painel", () => {
  it("não usa travessão (em dash ou en dash) em app, components e lib", () => {
    const files = ["app", "components", "lib"]
      .flatMap((dir) => walk(join(ROOT, dir)))
      .filter((f) => /\.(tsx?|css|svg|json)$/.test(f));
    expect(files.some((f) => f.includes("cupons"))).toBe(true);
    const offenders = files.filter((f) => /[–—]/.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });
});
