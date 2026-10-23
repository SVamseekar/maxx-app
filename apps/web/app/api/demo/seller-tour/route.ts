import { NextResponse } from "next/server";
import { apiBase, forwardHeaders, relayJson } from "../../../lib/upstream";

export const dynamic = "force-dynamic";

async function relay(request: Request, method: "GET" | "POST") {
  try {
    const response = await fetch(`${apiBase()}/demo/seller-tour`, { method, headers: forwardHeaders(request), cache: "no-store", signal: AbortSignal.timeout(30000) });
    return await relayJson(response);
  } catch { return NextResponse.json({ message: "The seller tour could not start. Check the API and retry." }, { status: 503 }); }
}

export const GET = (request: Request) => relay(request, "GET");
export const POST = (request: Request) => relay(request, "POST");
