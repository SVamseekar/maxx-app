"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Hourglass, RefreshCw } from "lucide-react";
import { useAuth } from "./auth";
import { nextWakeState, WAKE_BANNER_DELAY_MS, WAKE_POLL_MS, type WakeState } from "../lib/server-wake";

const WakeContext = createContext<{ state: WakeState; retry: () => void }>({ state: "ready", retry: () => {} });

/** True once the API answers its health check; until then actions that need it stay disabled. */
export const useServerReady = () => useContext(WakeContext).state === "ready";

/** Checks the API when the page opens and keeps checking while free hosting starts it. */
export function ServerWakeProvider({ children }: { children: ReactNode }) {
  const { refresh } = useAuth();
  const [state, setState] = useState<WakeState>("checking");
  const [attempt, setAttempt] = useState(0);
  const missed = useRef(false);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    // A sleeping API makes the first check slow; the banner appears before it returns.
    const banner = setTimeout(() => setState(current => current === "checking" ? "waking" : current), WAKE_BANNER_DELAY_MS);
    async function check() {
      const healthy = await fetch("/api/health", { cache: "no-store", signal: AbortSignal.timeout(10_000) }).then(r => r.ok, () => false);
      if (stopped) return;
      const next = nextWakeState(healthy, Date.now() - started);
      setState(current => current === "waking" && next === "checking" ? current : next);
      if (healthy) {
        // Calls made while the API slept failed; read the session again now that it answers.
        if (missed.current) void refresh();
        return;
      }
      missed.current = true;
      if (next !== "stuck") timer = setTimeout(() => void check(), WAKE_POLL_MS);
    }
    void check();
    return () => { stopped = true; clearTimeout(timer); clearTimeout(banner); };
  }, [attempt, refresh]);
  const retry = useCallback(() => { setState("checking"); setAttempt(n => n + 1); }, []);
  return <WakeContext.Provider value={{ state, retry }}>{children}</WakeContext.Provider>;
}

export function ServerWakeBanner() {
  const { state, retry } = useContext(WakeContext);
  if (state === "waking") return <div className="verify-banner wake-banner" role="status">
    <Hourglass size={16} aria-hidden="true" />
    <span><strong>Waking the demo server.</strong> Free hosting sleeps when no one is using it, so the first visit takes about a minute. Live Nemotron is ready when this bar fills.</span>
    <span className="wake-bar" aria-hidden="true"><span /></span>
  </div>;
  if (state === "stuck") return <div className="verify-banner" role="alert">
    <span><strong>The demo server is taking longer than usual.</strong> Try again in a minute.</span>
    <button type="button" className="button quiet-button" onClick={retry}><RefreshCw size={14} /> Try again</button>
  </div>;
  return null;
}
