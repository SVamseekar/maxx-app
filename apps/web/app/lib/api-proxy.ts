import { NextResponse } from "next/server";
import { apiBase, forwardHeaders, relayJson } from "./upstream";

type Context = { params: Promise<{ path?: string[] }> };

/**
 * A same-origin bridge to one API prefix. The browser only ever talks to Next.js, so the session
 * cookie stays first-party and the API's origin checks apply. PayPal webhooks are deliberately not
 * reachable through here: PayPal calls the API directly and is authenticated by signature.
 */
export function bridge(prefix: string, options: { maxDepth: number; blocked?: string[]; root?: boolean }) {
  async function proxy(request: Request, context: Context) {
    const { path = [] } = await context.params;
    if ((path.length === 0 && !options.root) || path.length > options.maxDepth || path.some(part => !/^[a-zA-Z0-9_-]+$/.test(part)) || options.blocked?.includes(path[0])) {
      return NextResponse.json({ message: "Not found." }, { status: 404 });
    }
    try {
      const headers = forwardHeaders(request);
      let body: string | undefined;
      if (request.method === "POST") {
        if (Number(request.headers.get("content-length")) > 8192) return NextResponse.json({ message: "Request too large." }, { status: 413 });
        body = await request.text();
        if (body.length > 8192) return NextResponse.json({ message: "Request too large." }, { status: 413 });
        headers["content-type"] = "application/json";
      }
      const upstream = await fetch(`${apiBase()}/${prefix}${path.length ? "/" + path.join("/") : ""}${new URL(request.url).search}`, {
        method: request.method, headers, body, cache: "no-store", signal: AbortSignal.timeout(30000),
      });
      return await relayJson(upstream);
    } catch {
      return NextResponse.json({ message: "Cannot reach the payments service. Check that the API is running, then retry." }, { status: 503 });
    }
  }
  return { GET: proxy, POST: proxy };
}
