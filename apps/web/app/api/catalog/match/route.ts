import { NextResponse } from "next/server";
import { apiBase, forwardHeaders } from "../../../lib/upstream";
export async function POST(request: Request) {
  try {
    if (Number(request.headers.get("content-length")) > 16000) return NextResponse.json({message:"Request too large."},{status:413});
    const body = await request.text();
    if (body.length > 16000) return NextResponse.json({message:"Request too large."},{status:413});
    const response = await fetch(`${apiBase()}/catalog/match`,{method:"POST",body,headers:forwardHeaders(request,{"Content-Type":"application/json"}),cache:"no-store",signal:AbortSignal.timeout(25000)});
    return NextResponse.json(await response.json(),{status:response.status});
  } catch { return NextResponse.json({message:"Matching unavailable. Check the API and matching configuration."},{status:503}); }
}
