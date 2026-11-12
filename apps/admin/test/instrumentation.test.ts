import { trace } from "@opentelemetry/api";
import { afterEach, describe, expect, it, type MockInstance, vi } from "vitest";
import { onRequestError } from "../instrumentation";

const TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736";
const REQUEST = { path: "/conta", method: "GET", headers: { cookie: "ks_access=segredo" } };
const CONTEXT = {
  routerKind: "App Router",
  routePath: "/conta",
  routeType: "render",
  revalidateReason: undefined,
} as const;

function loggedLine(spy: MockInstance<typeof console.error>): Record<string, unknown> {
  expect(spy).toHaveBeenCalledTimes(1);
  const [line] = spy.mock.calls[0] as [string];
  return JSON.parse(line) as Record<string, unknown>;
}

describe("onRequestError", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loga o digest junto com o trace id do span ativo", async () => {
    vi.spyOn(trace, "getActiveSpan").mockReturnValue(
      trace.wrapSpanContext({ traceId: TRACE_ID, spanId: "00f067aa0ba902b7", traceFlags: 1 }),
    );
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const error = Object.assign(new Error("falhou"), { digest: "123456789" });

    await onRequestError(error, REQUEST, CONTEXT);

    expect(loggedLine(spy)).toEqual({
      level: "error",
      event: "request_error",
      digest: "123456789",
      trace_id: TRACE_ID,
      method: "GET",
      path: "/conta",
      route_path: "/conta",
      route_type: "render",
      error: "falhou",
    });
  });

  it("sem span ativo nem digest, os campos ficam null e nada de cabeçalho vaza", async () => {
    vi.spyOn(trace, "getActiveSpan").mockReturnValue(undefined);
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    await onRequestError("texto", REQUEST, CONTEXT);

    const line = loggedLine(spy);
    expect(line.digest).toBeNull();
    expect(line.trace_id).toBeNull();
    expect(line.error).toBe("texto");
    expect(JSON.stringify(line)).not.toContain("segredo");
  });
});
