import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "../src/components/badge";
import { Button } from "../src/components/button";
import { Checkbox } from "../src/components/checkbox";
import { TabsTrigger, Tabs, TabsList } from "../src/components/tabs";

const root = join(import.meta.dirname, "..");
const read = (p: string) => readFileSync(join(root, p), "utf8");

function lum(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = c.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)) as [
    number,
    number,
    number,
  ];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
export function ratio(a: string, b: string): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

function vars(block: RegExp): Record<string, string> {
  const css = read("src/styles/tokens.css");
  const body = block.exec(css)?.[1] ?? "";
  return Object.fromEntries(
    [...body.matchAll(/(--[\w-]+):\s*(#[0-9a-f]{6})/g)].map((m) => [m[1]!, m[2]!]),
  );
}

const store = { ...vars(/@theme static \{([^}]*)\}/), ...vars(/:root \{([^}]*)\}/) };
const admin = { ...store, ...vars(/\[data-theme="admin"\] \{([^}]*)\}/) };

describe.each([
  ["loja", store],
  ["admin", admin],
])("contraste WCAG (%s)", (_name, t) => {
  it("texto tem pelo menos 4.5:1", () => {
    const pairs: [string, string][] = [
      ["--ks-fg", "--ks-bg"],
      ["--ks-fg", "--ks-surface"],
      ["--ks-muted", "--ks-bg"],
      ["--ks-muted", "--ks-surface"],
      ["--ks-accent-fg", "--color-accent"],
    ];
    for (const [fg, bg] of pairs) {
      const a = t[fg];
      const b = t[bg];
      expect(a && b, `${fg}/${bg} definidos`).toBeTruthy();
      expect(ratio(a!, b!), `${fg} sobre ${bg}`).toBeGreaterThanOrEqual(4.5);
    }
  });
  it("foco tem pelo menos 3:1 sobre bg e surface", () => {
    for (const bg of ["--ks-bg", "--ks-surface"]) {
      expect(ratio(t["--ks-focus"]!, t[bg]!), `focus sobre ${bg}`).toBeGreaterThanOrEqual(3);
    }
  });
});

describe("componentes no contexto admin", () => {
  it("não usam classes de tema escuro cruas", () => {
    const dir = join(root, "src/components");
    const raw =
      /(^|[\s"'`:])(text-fg|text-muted|text-bg|bg-surface|border-border|border-fg|outline-accent|bg-fg|border-accent)(?![\w-])/;
    for (const f of readdirSync(dir)) {
      expect(raw.test(readFileSync(join(dir, f), "utf8")), f).toBe(false);
    }
  });
  it("Button secondary e ghost usam tokens semânticos", () => {
    render(
      <>
        <Button variant="secondary">A</Button>
        <Button variant="ghost">B</Button>
      </>,
    );
    expect(screen.getByText("A").className).toContain("border-ks-fg");
    expect(screen.getByText("A").className).toContain("text-ks-fg");
    expect(screen.getByText("B").className).toContain("text-ks-fg");
  });
  it("primary usa bg-accent com texto escuro semântico e foco semântico", () => {
    render(<Button>Ok</Button>);
    const c = screen.getByRole("button").className;
    expect(c).toContain("bg-accent");
    expect(c).toContain("text-ks-accent-fg");
    expect(c).toContain("focus-visible:outline-ks-focus");
  });
  it("Badge accent, Checkbox e Tabs não dependem do lima cru", () => {
    render(
      <>
        <Badge variant="accent">x</Badge>
        <Checkbox aria-label="c" />
        <Tabs defaultValue="a">
          <TabsList>
            <TabsTrigger value="a">Aba</TabsTrigger>
          </TabsList>
        </Tabs>
      </>,
    );
    expect(screen.getByText("x").className).toContain("text-ks-accent-fg");
    expect(screen.getByRole("checkbox").className).toContain("data-[state=checked]:bg-ks-fg");
    const tab = screen.getByRole("tab").className;
    expect(tab).toContain("text-ks-muted");
    expect(tab).toContain("data-[state=active]:text-ks-fg");
  });
  it("tokens.css define o contexto admin", () => {
    const css = read("src/styles/tokens.css");
    expect(css).toContain('[data-theme="admin"]');
    expect(admin["--ks-fg"]).toBe("#0e0e0e");
    expect(admin["--color-accent"]).toBe("#9dbf00");
  });
});
