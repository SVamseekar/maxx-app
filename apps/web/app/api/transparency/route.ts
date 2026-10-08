import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export async function GET() {
  try {
    const response = await fetch(`${process.env.API_BASE_URL ?? "http://127.0.0.1:8000"}/transparency`,{cache:"no-store",signal:AbortSignal.timeout(10000)});
    return NextResponse.json(await response.json(),{status:response.status});
  } catch { return NextResponse.json({message:"Cannot load call metadata. Check API and retry."},{status:503}); }
}
