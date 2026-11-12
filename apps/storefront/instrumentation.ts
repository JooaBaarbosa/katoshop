import { trace } from "@opentelemetry/api";
import { registerOTel } from "@vercel/otel";
import type { Instrumentation } from "next";

// Exporta para OTEL_EXPORTER_OTLP_ENDPOINT (no compose, http://otel-collector:4318).
// Sem o perfil observability o collector não existe e a exportação só falha em silêncio.
export function register() {
  registerOTel({
    serviceName: "storefront",
    // O @vercel/otel só injeta traceparent em fetch para URLs listadas; sem isto o trace
    // do Next não continua no Traefik, no catalog e no Postgres.
    instrumentationConfig: {
      fetch: {
        propagateContextUrls: [
          /^https?:\/\/api\.katoshop\.localhost(?:[:/]|$)/,
        ],
      },
    },
  });
}

// A página de erro mostra o `digest` do Next como "código para suporte". Esta linha liga o
// digest ao trace id do request, para o suporte achar o trace no Jaeger a partir do código.
// Só método, caminho e rota: cabeçalhos (cookies de sessão) ficam fora do log.
export const onRequestError: Instrumentation.onRequestError = (error, request, context) => {
  const digest =
    typeof error === "object" && error !== null && "digest" in error ? String(error.digest) : null;
  console.error(
    JSON.stringify({
      level: "error",
      event: "request_error",
      digest,
      trace_id: trace.getActiveSpan()?.spanContext().traceId ?? null,
      method: request.method,
      path: request.path,
      route_path: context.routePath,
      route_type: context.routeType,
      error: error instanceof Error ? error.message : String(error),
    }),
  );
};
