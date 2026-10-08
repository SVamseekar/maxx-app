import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const max = 8 * 1024 * 1024;
  if (Number(request.headers.get("content-length")) > max) {
    return NextResponse.json({ message: "Choose an image up to 8 MB." }, { status: 413 });
  }
  try {
    const reader = request.body?.getReader();
    if (!reader) return NextResponse.json({ message: "Choose a screenshot." }, { status: 422 });
    const chunks: Uint8Array[] = [];
    let length = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > max) {
        await reader.cancel();
        return NextResponse.json({ message: "Choose an image up to 8 MB." }, { status: 413 });
      }
      chunks.push(value);
    }
    const body = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.length; }
    const base = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
    const query = new URL(request.url).search;
    const upstream = await fetch(`${base.replace(/\/$/, "")}/scan${query}`, {
      method: "POST", headers: { "Content-Type": request.headers.get("content-type") ?? "application/octet-stream" },
      body, cache: "no-store", signal: AbortSignal.timeout(105000),
    });
    return NextResponse.json(await upstream.json(), { status: upstream.status });
  } catch {
    return NextResponse.json({ message: "Cannot complete the scan. Check that the API is running, then retry." }, { status: 503 });
  }
}
