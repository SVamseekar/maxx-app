"use client";
import { useCallback, useEffect, useState } from "react";

type State = { kind: "loading" | "ok" | "error"; message: string };
export default function Home() {
  const [state, setState] = useState<State>({ kind: "loading", message: "Checking the connection…" });
  const check = useCallback(async () => {
    setState({ kind: "loading", message: "Checking the connection…" });
    try {
      const response = await fetch("/api/health", { cache: "no-store", signal: AbortSignal.timeout(7000) });
      const result = await response.json();
      if (!response.ok || result.status !== "ok") throw new Error(result.message ?? "Health check failed.");
      setState({ kind: "ok", message: "Connected · API healthy · Postgres ready" });
    } catch (error) {
      setState({ kind: "error", message: error instanceof Error ? error.message : "Health check failed." });
    }
  }, []);
  useEffect(() => { void check(); }, [check]);
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-6 py-16">
      <p className="mb-6 text-sm font-bold uppercase tracking-[0.25em] text-lime-300">Maxx / Foundation</p>
      <h1 className="text-5xl font-bold tracking-tight sm:text-6xl">Ready to build.</h1>
      <p className="mt-5 text-lg leading-8 text-stone-300">The local foundation for Maxx. This page checks the connection to FastAPI and Postgres.</p>
      <section className="mt-10 rounded-2xl border border-stone-700 bg-white/5 p-6" aria-label="Connection health">
        <p role="status" aria-live="polite" className={state.kind === "error" ? "text-red-300" : "text-lime-200"}>{state.message}</p>
        <button onClick={() => void check()} disabled={state.kind === "loading"} className="mt-6 rounded-lg bg-lime-300 px-5 py-3 font-bold text-stone-950 hover:bg-lime-200 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-lime-300 disabled:opacity-50">Check again</button>
      </section>
      <p className="mt-8 text-sm text-stone-400">Foundation milestone · Product features come next.</p>
    </main>
  );
}
