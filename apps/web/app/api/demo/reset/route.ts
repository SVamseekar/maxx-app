import { NextResponse } from "next/server";
import { forwardHeaders, relayJson } from "../../../lib/upstream";
export async function POST(request: Request) {
  try {
    const base = (process.env.API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
    const response = await fetch(`${base}/demo/reset`, { method: "POST", headers: forwardHeaders(request), cache: "no-store", signal: AbortSignal.timeout(15000) });
    return await relayJson(response);
  } catch { return NextResponse.json({ message: "Reset failed. Check the API and retry." }, { status: 503 }); }
}
