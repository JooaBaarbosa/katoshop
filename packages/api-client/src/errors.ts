export interface ApiProblemInit {
  status: number;
  code: string;
  message: string;
  errors?: Record<string, string[]>;
  traceId?: string;
  cause?: unknown;
}

/** Erro de API no formato application/problem+json dos serviços. */
export class ApiProblem extends Error {
  readonly status: number;
  readonly code: string;
  readonly errors?: Record<string, string[]>;
  readonly traceId?: string;

  constructor(init: ApiProblemInit) {
    super(init.message, init.cause === undefined ? undefined : { cause: init.cause });
    this.name = "ApiProblem";
    this.status = init.status;
    this.code = init.code;
    if (init.errors !== undefined) this.errors = init.errors;
    if (init.traceId !== undefined) this.traceId = init.traceId;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFieldErrors(value: unknown): value is Record<string, string[]> {
  return (
    isRecord(value) &&
    Object.values(value).every(
      (items) => Array.isArray(items) && items.every((item) => typeof item === "string"),
    )
  );
}

export function problemFrom(error: unknown, response: Response): ApiProblem {
  const body = isRecord(error) ? error : {};
  const detail = typeof body.detail === "string" ? body.detail : undefined;
  const title = typeof body.title === "string" ? body.title : undefined;
  return new ApiProblem({
    status: response.status,
    code: typeof body.code === "string" ? body.code : `http.${response.status}`,
    message: detail ?? title ?? (response.statusText || `HTTP ${response.status}`),
    ...(isFieldErrors(body.errors) ? { errors: body.errors } : {}),
    ...(typeof body.trace_id === "string" ? { traceId: body.trace_id } : {}),
  });
}

/** Devolve `data` ou lança `ApiProblem` quando a chamada openapi-fetch falhou. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    throw problemFrom(result.error, result.response);
  }
  return result.data as T;
}
