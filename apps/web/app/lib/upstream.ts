import { NextResponse } from "next/server";
import { clientAddress } from "./forwarded";
export { safeLocation } from "./safe-url";

/** Server-only helpers for forwarding browser requests to the FastAPI service with the session. */
export const apiBase = () => (process.env.API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

/** Headers the API needs to identify the person and judge the request. Nothing else is forwarded. */
export function forwardHeaders(request: Request, extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  // Fetch Metadata is forwarded so the API can refuse requests that did not start on our own site.
  for (const name of ["cookie", "origin", "referer", "user-agent", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest"]) {
    const value = request.headers.get(name);
    if (value) headers[name] = value;
  }
  const address = clientAddress(request.headers);
  if (address) headers["x-forwarded-for"] = address;
  return headers;
}

/** Copy every Set-Cookie from the API response, so sessions are created and cleared by one owner. */
export function relayCookies(upstream: Response, response: Response): Response {
  for (const cookie of upstream.headers.getSetCookie()) response.headers.append("set-cookie", cookie);
  return response;
}

/** Relay a JSON (or empty) API answer, including its status and cookies. */
export async function relayJson(upstream: Response): Promise<Response> {
  const text = await upstream.text();
  let response: Response;
  if ((upstream.headers.get("content-type") ?? "").startsWith("text/html")) {
    // The OAuth form_post relay page. Passed through verbatim and never cached.
    const headers: Record<string, string> = { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "referrer-policy": "no-referrer" };
    const csp = upstream.headers.get("content-security-policy");
    if (csp) headers["content-security-policy"] = csp;
    response = new Response(text, { status: upstream.status, headers });
  } else if (!text) response = new Response(null, { status: upstream.status });
  else {
    try { response = NextResponse.json(JSON.parse(text), { status: upstream.status }); }
    catch { response = NextResponse.json({ message: "Unexpected response from the service." }, { status: 502 }); }
  }
  const retry = upstream.headers.get("retry-after");
  if (retry) response.headers.set("retry-after", retry);
  response.headers.set("cache-control", "no-store"); // account and Bloc data is never cached by browsers or proxies
  return relayCookies(upstream, response);
}
