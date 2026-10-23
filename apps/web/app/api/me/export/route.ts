import { NextResponse } from "next/server";
import { apiBase, forwardHeaders } from "../../../lib/upstream";

export const dynamic = "force-dynamic";
/** Pass the data-export download through, keeping the attachment headers and never caching it. */
export async function GET(request: Request) {
  try {
    const upstream = await fetch(`${apiBase()}/me/export`, { headers: forwardHeaders(request), cache: "no-store", signal: AbortSignal.timeout(30000) });
    if (!upstream.ok) {
      const text = await upstream.text();
      let body: unknown = { message: "Could not export your data." };
      try { body = JSON.parse(text); } catch { /* keep the generic message */ }
      return NextResponse.json(body, { status: upstream.status, headers: { "cache-control": "no-store" } });
    }
    return new Response(upstream.body, { headers: { "content-type": "application/json", "content-disposition": upstream.headers.get("content-disposition") ?? 'attachment; filename="maxx-my-data.json"', "cache-control": "no-store" } });
  } catch { return NextResponse.json({ message: "Cannot reach Maxx. Retry shortly." }, { status: 503 }); }
}
