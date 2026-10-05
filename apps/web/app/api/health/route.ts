import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const base = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
    const upstream = await fetch(`${base.replace(/\/$/, "")}/health/ready`, {
      cache: "no-store", signal: AbortSignal.timeout(5000),
    });
    const health = await upstream.json();
    if (!upstream.ok || health.status !== "ok" || health.service !== "maxx-api" || health.database !== "ok") {
      return NextResponse.json({ status: "unavailable", message: "API or database is unavailable." }, { status: 503 });
    }
    return NextResponse.json(health);
  } catch {
    return NextResponse.json({ status: "unavailable", message: "Cannot reach the API. Check that it is running." }, { status: 503 });
  }
}
