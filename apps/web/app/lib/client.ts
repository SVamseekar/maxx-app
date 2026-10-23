/** Browser-side JSON client. Errors carry the server's message and HTTP status. */
export class ApiError extends Error {
  status: number;
  /** Machine-readable reason the interface can act on, e.g. "reauth_required" or "captcha_required". */
  code?: string;
  constructor(message: string, status: number, code?: string) { super(message); this.status = status; this.code = code; }
}

/** FastAPI validation errors arrive as a list of { loc, msg }. Show the first one in plain words. */
export function validationText(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const first = detail[0] as { loc?: unknown[]; msg?: string };
  const field = String(first.loc?.at(-1) ?? "").replaceAll("_", " ");
  const text = String(first.msg ?? "").replace(/^Value error, /, "");
  return field && field !== "body" && !text.toLowerCase().includes(field) ? `${field[0].toUpperCase()}${field.slice(1)}: ${text}` : text || null;
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";
export async function request<T>(url: string, options: { method?: Method; body?: unknown; timeout?: number } = {}): Promise<T> {
  const method = options.method ?? (options.body === undefined ? "GET" : "POST");
  let response: Response;
  try {
    response = await fetch(url, {
      method, credentials: "same-origin", cache: "no-store",
      headers: options.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: AbortSignal.timeout(options.timeout ?? 35000),
    });
  } catch { throw new ApiError("Cannot reach Maxx. Check your connection and try again.", 0); }
  const text = await response.text();
  let data: unknown = null;
  if (text) { try { data = JSON.parse(text); } catch { data = null; } }
  if (!response.ok) {
    const body = (data ?? {}) as { message?: string; detail?: unknown; code?: string };
    const message = body.message ?? (typeof body.detail === "string" ? body.detail : validationText(body.detail) ?? (response.status === 429 ? "Too many attempts. Wait a moment and try again." : "Check the fields and retry."));
    throw new ApiError(message, response.status, typeof body.code === "string" ? body.code : undefined);
  }
  return data as T;
}
