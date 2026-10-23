"use client";
import { useCallback, useState } from "react";

export type Notice = { tone: "error" | "success"; text: string } | null;

/** One async action with a busy flag and a single success or error notice. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Notice>(null);
  const run = useCallback(async (task: () => Promise<string | void>) => {
    setBusy(true); setMessage(null);
    try { const text = await task(); if (text) setMessage({ tone: "success", text }); }
    catch (cause) {
      const code = (cause as { code?: string } | null)?.code;
      if (code === "reauth_cancelled") return; // the person chose not to confirm; nothing to report
      setMessage({ tone: "error", text: cause instanceof Error ? cause.message : "Something went wrong." });
    }
    finally { setBusy(false); }
  }, []);
  return { busy, message, run, clear: () => setMessage(null), setMessage };
}
