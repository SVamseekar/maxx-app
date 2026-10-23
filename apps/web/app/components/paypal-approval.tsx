"use client";
import { useEffect, useRef, useState } from "react";
import { FlaskConical, Lock } from "lucide-react";
import { request } from "../lib/client";
import type { MoneyConfig } from "../lib/money";

type Session = { start: (options: { presentationMode: string }, order: Promise<{ orderId: string }>) => Promise<void> };
type Sdk = { createInstance: (options: { clientId: string; components: string[]; pageType: string }) => Promise<{ createPayPalOneTimePaymentSession: (options: { onApprove: (data: { orderId: string }) => void | Promise<void>; onCancel?: () => void; onError?: (error: unknown) => void }) => Session }> };

let sdkLoading: Promise<Sdk> | null = null;
/** Load PayPal's v6 SDK once. The page's CSP only allows PayPal's sandbox origin, and only in sandbox mode. */
function loadSdk(url: string): Promise<Sdk> {
  sdkLoading ??= new Promise<Sdk>((resolve, reject) => {
    const existing = (window as unknown as { paypal?: Sdk }).paypal;
    if (existing) return resolve(existing);
    const script = document.createElement("script");
    script.src = url; script.async = true;
    script.onload = () => { const loaded = (window as unknown as { paypal?: Sdk }).paypal; if (loaded) resolve(loaded); else reject(new Error("PayPal did not load.")); };
    script.onerror = () => { sdkLoading = null; reject(new Error("PayPal could not be reached. Check your connection and retry.")); };
    document.head.append(script);
  });
  return sdkLoading;
}

type Props = {
  orderId: string; config: MoneyConfig; label: string; disabled?: boolean;
  /** Called once PayPal says the buyer approved. The caller then authorizes or captures on the server. */
  onApproved: () => Promise<void> | void; onCancel?: () => void; onError: (message: string) => void;
};

/** The buyer's approval step: PayPal's real popup in sandbox mode, a clearly labelled stand-in in simulator mode. */
export default function PayPalApproval({ orderId, config, label, disabled, onApproved, onCancel, onError }: Props) {
  const [busy, setBusy] = useState(false);
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);

  async function simulated() {
    setBusy(true);
    try { await request(`/api/money/holds/${orderId}/simulate-approve`, { body: {} }); await onApproved(); }
    catch (cause) { onError(cause instanceof Error ? cause.message : "Approval failed."); }
    finally { if (live.current) setBusy(false); }
  }
  async function sandbox() {
    setBusy(true);
    try {
      const sdk = await loadSdk(config.sdk_url);
      const instance = await sdk.createInstance({ clientId: config.client_id, components: ["paypal-payments"], pageType: "checkout" });
      const session = instance.createPayPalOneTimePaymentSession({
        onApprove: async () => { try { await onApproved(); } catch (cause) { onError(cause instanceof Error ? cause.message : "Approval failed."); } },
        onCancel: () => onCancel?.(),
        onError: () => onError("PayPal reported a problem. Nothing was charged."),
      });
      await session.start({ presentationMode: "auto" }, Promise.resolve({ orderId }));
    } catch (cause) { onError(cause instanceof Error ? cause.message : "PayPal could not start."); }
    finally { if (live.current) setBusy(false); }
  }

  if (config.simulated) return <div className="paypal-sheet" role="group" aria-label="Simulated PayPal approval">
    <div className="paypal-sheet-head"><span className="paypal-mark" aria-hidden="true">P</span><div><strong>Simulated PayPal</strong><small>Stands in for PayPal’s approval window. No real money, no real account.</small></div><span className="sim-tag"><FlaskConical size={12} aria-hidden="true" /> Simulator</span></div>
    <button type="button" className="button primary" disabled={busy || disabled} onClick={() => void simulated()}>{busy ? "Approving…" : label}</button>
  </div>;
  return <div className="paypal-sheet">
    <button type="button" className="button paypal-button" disabled={busy || disabled} onClick={() => void sandbox()}><Lock size={14} aria-hidden="true" /> {busy ? "Opening PayPal…" : label}</button>
    <small className="muted">Opens PayPal’s sandbox. Use a sandbox test buyer; no real money moves.</small>
  </div>;
}
