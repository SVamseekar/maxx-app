"use client";
import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { ShieldCheck, X } from "lucide-react";
import { ApiError, request } from "../lib/client";
import type { MoneyConfig } from "../lib/money";
import { usd, type Bloc } from "../blocs/types";
import { useMotionPreferences } from "./motion-system";
import PayPalApproval from "./paypal-approval";
import { FormMessage } from "./auth-ui";

type Order = { order_id: string; amount: string; currency: string; simulated: boolean };

/**
 * Joining a Bloc with payments on: PayPal places a hold for the member's maximum. They are charged
 * only the winning price, and the hold is released if there is no deal.
 */
export default function HoldDialog({ bloc, maximum, config, onJoined, onClose }: { bloc: Bloc; maximum: number; config: MoneyConfig; onJoined: (bloc: Bloc) => void; onClose: () => void }) {
  const { reduced } = useMotionPreferences();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState("");
  const [testCase, setTestCase] = useState("");

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    return () => { document.body.style.overflow = ""; opener?.focus?.(); };
  }, []);
  useEffect(() => {
    let live = true;
    setOrder(null); setError("");
    request<Order>(`/api/money/blocs/${bloc.id}/hold`, { body: { max_price: maximum.toFixed(2), test_case: testCase } })
      .then(value => { if (live) setOrder(value); })
      .catch(cause => { if (live) setError(cause instanceof Error ? cause.message : "Could not start the hold."); });
    return () => { live = false; };
  }, [bloc.id, maximum, testCase]);

  async function authorize() {
    if (!order) return;
    try { onJoined(await request<Bloc>(`/api/money/holds/${order.order_id}/authorize`, { body: {} })); }
    catch (cause) { throw cause instanceof ApiError ? cause : new Error("Could not place the hold."); }
  }
  function cancel() { if (order) void request(`/api/money/holds/${order.order_id}/cancel`, { body: {} }).catch(() => undefined); onClose(); }
  function keys(event: React.KeyboardEvent) {
    if (event.key === "Escape") { event.stopPropagation(); cancel(); return; }
    if (event.key !== "Tab" || !panel.current) return;
    const items = [...panel.current.querySelectorAll<HTMLElement>("button:not([disabled]),input,select,a[href]")].filter(el => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0], last = items.at(-1)!;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  return <motion.div className="dialog-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: reduced ? 0 : .15 }} onPointerDown={event => { if (event.target === event.currentTarget) cancel(); }}>
    <motion.div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId} className="dialog hold-dialog" onKeyDown={keys} initial={{ opacity: 0, y: reduced ? 0 : 14, scale: reduced ? 1 : .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: reduced ? 0 : .2, ease: [.2, .8, .2, 1] }}>
      <button type="button" className="icon-button dialog-close" aria-label="Cancel" onClick={cancel}><X size={16} /></button>
      <div className="dialog-head"><ShieldCheck size={22} aria-hidden="true" /><div><h2 id={titleId}>Hold up to {usd(maximum)}</h2><p>{bloc.title}</p></div></div>
      <ul className="hold-terms">
        <li><strong>You are charged the winning price only.</strong> Never above {usd(maximum)}.</li>
        <li><strong>No deal, nothing charged.</strong> The hold is released the moment the Bloc fails or you leave.</li>
        <li><strong>PayPal keeps the hold</strong> for up to 29 days; Maxx never sees your card or PayPal login.</li>
        <li><strong>The seller ships, not Maxx.</strong> If you win you give a delivery address, and you are refunded in full if the seller does not ship.</li>
        <li><strong>AI agents negotiate for the group.</strong> They cannot spend your money or go above your maximum.</li>
      </ul>
      <p className="small muted">By approving you agree to the <Link href="/legal/terms" target="_blank">Terms</Link> and <Link href="/legal/refunds" target="_blank">refund policy</Link>.</p>
      {error && <FormMessage>{error}</FormMessage>}
      {!order && !error && <p className="muted small">Preparing your PayPal hold…</p>}
      {order && <PayPalApproval orderId={order.order_id} config={config} label={`Approve hold of ${usd(order.amount)}`} onApproved={authorize} onCancel={cancel} onError={setError} />}
      {config.negative_testing && <label className="test-case small muted">Test a failure (sandbox only)<select value={testCase} onChange={event => setTestCase(event.target.value)}><option value="">None</option><option value="capture_declined">Decline the final charge</option><option value="authorize_declined">Decline the hold</option></select></label>}
    </motion.div>
  </motion.div>;
}
