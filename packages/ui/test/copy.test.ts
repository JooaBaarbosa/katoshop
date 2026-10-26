import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

describe("copy de UI", () => {
  it("não usa travessão (em dash ou en dash) em packages/ui/src", () => {
    const textFiles = walk(join(import.meta.dirname, "..", "src")).filter((f) =>
      /\.(tsx?|css|svg|json)$/.test(f),
    );
    expect(textFiles.length).toBeGreaterThan(0);
    const offenders = textFiles.filter((f) => /[\u2013\u2014]/.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });
});
