"use client";

import { useEffect, useRef } from "react";

type Turnstile = { render: (el: HTMLElement, options: Record<string, unknown>) => string; reset: (id?: string) => void; remove: (id?: string) => void };
declare global { interface Window { turnstile?: Turnstile } }

let loader: Promise<void> | null = null;
function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  loader ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    // Added by our own (nonce-approved) code, so a strict CSP trusts it without an inline allowance.
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true; script.onload = () => resolve(); script.onerror = () => { loader = null; reject(new Error("blocked")); };
    document.head.appendChild(script);
  });
  return loader;
}

/** Cloudflare Turnstile. Renders nothing when the server has no site key. Tokens are single use. */
export default function Turnstile({ siteKey, onToken, resetSignal = 0 }: { siteKey: string; onToken: (token: string | null) => void; resetSignal?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const widget = useRef<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    const theme = document.documentElement.dataset.theme === "light" ? "light" : "dark";
    loadScript().then(() => {
      if (cancelled || !host.current || !window.turnstile) return;
      widget.current = window.turnstile.render(host.current, { sitekey: siteKey, theme, callback: (token: string) => onToken(token), "expired-callback": () => onToken(null), "error-callback": () => onToken(null) });
    }).catch(() => onToken(null));
    return () => { cancelled = true; if (widget.current && window.turnstile) window.turnstile.remove(widget.current); widget.current = null; };
  }, [siteKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (resetSignal && widget.current) { window.turnstile?.reset(widget.current); onToken(null); } }, [resetSignal]); // eslint-disable-line react-hooks/exhaustive-deps
  return <div ref={host} className="turnstile" aria-label="Verification check" />;
}
