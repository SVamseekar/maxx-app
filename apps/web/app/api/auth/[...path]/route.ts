import { NextResponse } from "next/server";
import { apiBase, forwardHeaders, relayCookies, relayJson } from "../../../lib/upstream";
import { safeLocation } from "../../../lib/safe-url";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path?: string[] }> };

/** Same-origin bridge to the account API. Redirects (OAuth) and cookies pass through untouched. */
async function proxy(request: Request, context: Context) {
  const { path = [] } = await context.params;
  if (path.length === 0 || path.length > 4 || path.some(part => !/^[a-zA-Z0-9_-]+$/.test(part))) {
    return NextResponse.json({ message: "Not found." }, { status: 404 });
  }
  try {
    let body: string | undefined;
    const headers = forwardHeaders(request);
    if (!["GET", "HEAD"].includes(request.method)) {
      if (Number(request.headers.get("content-length")) > 8192) return NextResponse.json({ message: "Request too large." }, { status: 413 });
      body = await request.text();
      if (body.length > 8192) return NextResponse.json({ message: "Request too large." }, { status: 413 });
      // Providers using response_mode=form_post (Apple) send a form; everything else is JSON.
      const form = (request.headers.get("content-type") ?? "").startsWith("application/x-www-form-urlencoded");
      if (body) headers["content-type"] = form ? "application/x-www-form-urlencoded" : "application/json";
    }
    const upstream = await fetch(`${apiBase()}/auth/${path.join("/")}${new URL(request.url).search}`, {
      method: request.method, headers, body, cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(20000),
    });
    const location = upstream.headers.get("location");
    if (upstream.status >= 300 && upstream.status < 400 && location) {
      const target = safeLocation(location);
      if (!target) return NextResponse.json({ message: "Blocked an unexpected redirect." }, { status: 502 });
      return relayCookies(upstream, new Response(null, { status: upstream.status, headers: { location: target, "cache-control": "no-store" } }));
    }
    return await relayJson(upstream);
  } catch {
    return NextResponse.json({ message: "Cannot reach the account service. Check that the API is running, then retry." }, { status: 503 });
  }
}
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
