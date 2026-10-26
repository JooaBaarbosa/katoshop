import { describe, expect, it } from "vitest";
import { ApiProblem, unwrap } from "../src/errors";

function problemResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}

describe("unwrap", () => {
  it("devolve data quando a chamada deu certo", () => {
    const response = new Response(null, { status: 200 });
    expect(unwrap({ data: { id: 1 }, response })).toEqual({ id: 1 });
  });

  it("aceita data vazio em respostas 204", () => {
    const response = new Response(null, { status: 204 });
    expect(unwrap<undefined>({ data: undefined, response })).toBeUndefined();
  });

  it("lança ApiProblem com code, errors e trace_id vindos do problem+json", () => {
    const body = {
      type: "about:blank",
      title: "Unprocessable",
      status: 422,
      detail: "Dados inválidos",
      code: "identity.validation.failed",
      trace_id: "abc123",
      errors: { email: ["inválido"] },
    };
    const response = problemResponse(422, body);
    try {
      unwrap({ error: body, response });
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(ApiProblem);
      const problem = error as ApiProblem;
      expect(problem.status).toBe(422);
      expect(problem.code).toBe("identity.validation.failed");
      expect(problem.errors).toEqual({ email: ["inválido"] });
      expect(problem.traceId).toBe("abc123");
      expect(problem.message).toBe("Dados inválidos");
    }
  });

  it("cai em valores padrão quando o corpo não é problem+json", () => {
    const response = new Response("Bad Gateway", { status: 502 });
    try {
      unwrap({ error: "Bad Gateway", response });
      expect.unreachable();
    } catch (error) {
      const problem = error as ApiProblem;
      expect(problem).toBeInstanceOf(ApiProblem);
      expect(problem.status).toBe(502);
      expect(problem.code).toBe("http.502");
    }
  });
});
