import { describe, expect, it } from "vitest";
import { renderMarkdown } from "../lib/markdown";

describe("renderMarkdown", () => {
  it("renderiza títulos, listas e ênfase", () => {
    const html = renderMarkdown("## Título\n\n- um\n- **dois**\n");
    expect(html).toContain("<h2>Título</h2>");
    expect(html).toContain("<li>um</li>");
    expect(html).toContain("<strong>dois</strong>");
  });

  it("não deixa HTML bruto passar", () => {
    const html = renderMarkdown('<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>');
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;script&gt;");
  });

  it("neutraliza links javascript:", () => {
    const html = renderMarkdown("[x](javascript:alert(1))");
    expect(html).not.toContain("javascript:");
  });
});
