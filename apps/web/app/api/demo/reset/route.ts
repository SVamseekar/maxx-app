import { NextResponse } from "next/server";
export async function POST() {
  try {
    const base = (process.env.API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
    const response = await fetch(`${base}/demo/reset`, { method: "POST", cache: "no-store", signal: AbortSignal.timeout(15000) });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch { return NextResponse.json({ message: "Reset failed. Check the API and retry." }, { status: 503 }); }
}
