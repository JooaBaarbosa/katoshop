import { ApiProblem } from "@katoshop/api-client";
import { describe, expect, it } from "vitest";
import { forbiddenKind, READ_FORBIDDEN } from "../lib/forbidden";

function problem(status: number, code: string, message = "x") {
  return new ApiProblem({ status, code, message });
}

describe("forbiddenKind (classificador único de 403, R25)", () => {
  it("auth.insufficient_permission é falta de permissão", () => {
    expect(forbiddenKind(problem(403, "auth.insufficient_permission"))).toBe("permission");
  });

  it("auth.forbidden é audiência errada, mesmo com detalhe de permissão", () => {
    expect(forbiddenKind(problem(403, "auth.forbidden", "Permissão insuficiente."))).toBe(
      "audience",
    );
  });

  it("outro código 403 desconhecido também encerra a sessão (lado conservador)", () => {
    expect(forbiddenKind(problem(403, "http.403"))).toBe("audience");
  });

  it("não é 403: sem classificação", () => {
    expect(forbiddenKind(problem(401, "auth.invalid_token"))).toBeNull();
    expect(forbiddenKind(new TypeError("x"))).toBeNull();
  });

  it("texto da página de leitura sem permissão", () => {
    expect(READ_FORBIDDEN).toBe("Você não tem permissão para acessar esta área.");
  });
});
