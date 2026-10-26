import { NextResponse } from "next/server";
import { apiBase, forwardHeaders } from "../../lib/upstream";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  try {
    const response = await fetch(`${apiBase()}/transparency`,{headers:forwardHeaders(request),cache:"no-store",signal:AbortSignal.timeout(10000)});
    return NextResponse.json(await response.json(),{status:response.status});
  } catch { return NextResponse.json({message:"Cannot load call metadata. Check API and retry."},{status:503}); }
}
