import { NextResponse } from "next/server";
import { apiBase, forwardHeaders, relayJson } from "../../../../lib/upstream";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ scenario: string }> };

/** Opens the signed-in judge's own copy of a demo scenario. */
export async function POST(request: Request, context: Context) {
  const { scenario } = await context.params;
  if (!/^[a-z]{1,20}$/.test(scenario)) return NextResponse.json({ message: "Not found." }, { status: 404 });
  try {
    const response = await fetch(`${apiBase()}/demo/lab/${scenario}`, { method: "POST", headers: forwardHeaders(request), cache: "no-store", signal: AbortSignal.timeout(15000) });
    return await relayJson(response);
  } catch { return NextResponse.json({ message: "Cannot open the demo. Check the API and retry." }, { status: 503 }); }
}
