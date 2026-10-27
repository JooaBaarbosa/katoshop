import { registerOTel } from "@vercel/otel";

// Exporta para OTEL_EXPORTER_OTLP_ENDPOINT (no compose, http://otel-collector:4318).
// Sem o perfil observability o collector não existe e a exportação só falha em silêncio.
export function register() {
  registerOTel({ serviceName: "storefront" });
}
