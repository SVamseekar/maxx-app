import { NextResponse } from "next/server";
import { apiBase, forwardHeaders, relayJson } from "../../../lib/upstream";

export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  try {
    const upstream = await fetch(`${apiBase()}/me/blocs`, { headers: forwardHeaders(request), cache: "no-store", signal: AbortSignal.timeout(15000) });
    return await relayJson(upstream);
  } catch { return NextResponse.json({ message: "Cannot load your Blocs. Check the API and retry." }, { status: 503 }); }
}
