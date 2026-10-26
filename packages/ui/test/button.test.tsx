import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "../src/components/button";

describe("Button", () => {
  it("nunca é pílula e usa o raio do token", () => {
    render(<Button>Comprar</Button>);
    const el = screen.getByRole("button", { name: "Comprar" });
    expect(el.className).not.toContain("rounded-full");
    expect(el.className).toContain("rounded-[var(--radius)]");
  });
  it("primary usa bg-accent", () => {
    render(<Button variant="primary">Comprar</Button>);
    expect(screen.getByRole("button").className).toContain("bg-accent");
  });
});
