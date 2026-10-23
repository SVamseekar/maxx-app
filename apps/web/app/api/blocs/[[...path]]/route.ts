import { NextResponse } from "next/server";
import { forwardHeaders, relayJson } from "../../../lib/upstream";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path?: string[] }> };

async function proxy(request: Request, context: Context) {
  const { path = [] } = await context.params;
  if (path.length > 2 || path.some(part => !/^[a-zA-Z0-9-]+$/.test(part))) {
    return NextResponse.json({ message: "Invalid Bloc route." }, { status: 404 });
  }
  const streaming = path[1] === "stream";
  try {
    const base = (process.env.API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
    const url = `${base}/blocs${path.length ? "/" + path.join("/") : ""}${new URL(request.url).search}`;
    const headers = forwardHeaders(request);
    if (request.headers.has("last-event-id")) headers["Last-Event-ID"] = request.headers.get("last-event-id")!;
    let body: string | undefined;
    if (request.method === "POST") {
      if (Number(request.headers.get("content-length")) > 4096) return NextResponse.json({ message: "Request too large." }, { status: 413 });
      body = await request.text();
      if (body.length > 4096) return NextResponse.json({ message: "Request too large." }, { status: 413 });
      headers["Content-Type"] = "application/json";
    }
    const upstream = await fetch(url, { method: request.method, headers, body, cache: "no-store", signal: streaming ? request.signal : AbortSignal.timeout(30000) });
    if (streaming && upstream.ok) return new Response(upstream.body, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no" } });
    return await relayJson(upstream);
  } catch {
    return NextResponse.json({ message: "Cannot reach the Bloc service. Check the API and retry." }, { status: 503 });
  }
}
export const GET = proxy;
export const POST = proxy;
