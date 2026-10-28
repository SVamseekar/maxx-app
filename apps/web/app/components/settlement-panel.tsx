"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { BadgeCheck, FlaskConical, Landmark, Receipt as ReceiptIcon } from "lucide-react";
import { request } from "../lib/client";
import { shortId, type Ledger, type MoneyConfig, type Receipt } from "../lib/money";
import { STATUS_LABEL, type OrderView } from "../lib/orders";
import { usd } from "../blocs/types";
import { useMotionPreferences } from "./motion-system";
import { Badge, Disclosure } from "./ui";

const STATE_TEXT: Record<string, string> = {
  CAPTURED: "Charged the winning price", VOIDED: "Hold released, nothing charged", AUTHORIZED: "Hold in place",
  CAPTURE_FAILED: "The final charge was declined", VOID_PENDING: "Releasing your hold", REFUNDED: "Refunded", FAILED: "Hold failed",
};

/** What happened to the money for a finished Bloc: your own receipt, then the books for the whole group. */
export default function SettlementPanel({ blocId, config, signedIn }: { blocId: string; config: MoneyConfig; signedIn: boolean }) {
  const { reduced } = useMotionPreferences();
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [mine, setMine] = useState<Receipt | null>(null);
  const [order, setOrder] = useState<OrderView | null>(null);
  useEffect(() => {
    let live = true, timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const books = await request<Ledger>(`/api/money/blocs/${blocId}/ledger`);
        if (!live) return;
        setLedger(books);
        if (signedIn) {
          const receipts = await request<Receipt[]>("/api/money/receipts");
          if (live) setMine(receipts.find(item => item.bloc_id === blocId) ?? null);
          const orders = await request<OrderView[]>("/api/orders").catch(() => [] as OrderView[]);
          if (live) setOrder(orders.find(item => item.bloc_id === blocId) ?? null);
        }
        if (books.settlement !== "DONE" && books.settlement !== "NOT_NEEDED") timer = setTimeout(load, 1500);
      } catch { if (live) timer = setTimeout(load, 4000); }
    }
    void load();
    return () => { live = false; if (timer) clearTimeout(timer); };
  }, [blocId, signedIn]);
  if (!ledger) return null;
  const working = ledger.settlement === "RUNNING" || ledger.settlement === "WAITING" || ledger.settlement === "PARTIAL";
  return <motion.section className="settlement" aria-label="Payment settlement" initial={{ opacity: 0, y: reduced ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : .35 }}>
    <div className="section-heading"><span><Landmark size={14} aria-hidden="true" /> Payment settlement</span><Badge tone={ledger.simulated ? "warn" : "accent"}>{ledger.simulated ? <><FlaskConical size={11} /> Simulated PayPal</> : "PayPal sandbox"}</Badge></div>
    {mine && <div className={`my-receipt status-${mine.status.toLowerCase()}`}>
      <div><span>Your hold</span><strong>{usd(mine.held)}</strong></div>
      <div><span>You paid</span><strong>{mine.paid === null ? "—" : usd(mine.paid)}</strong></div>
      <div><span>Kept in your pocket</span><strong>{mine.saved === null ? (mine.status === "VOIDED" ? usd(mine.held) : "—") : usd(mine.saved)}</strong></div>
      <p>{STATE_TEXT[mine.status] ?? mine.status}{mine.error && mine.status !== "VOIDED" ? ` · ${mine.error.toLowerCase().replaceAll("_", " ")}` : ""}.</p>
      <Link className="quiet-link" href="/receipts"><ReceiptIcon size={13} aria-hidden="true" /> All receipts and PayPal ids</Link>
    </div>}
    {order && <div className="notice-strip" role="status"><span><strong>{STATUS_LABEL[order.status]}.</strong> {order.status === "AWAITING_ADDRESS" ? "The seller can’t ship until you give a delivery address." : "Follow shipping and manage the order."} The seller, {order.seller.name}, ships and supports it; Maxx holds your payment until they do.</span> <Link className="quiet-link" href="/orders">Open your order</Link></div>}
    {working && <p className="muted small" role="status">{ledger.settlement === "WAITING" ? "Settlement starts when the negotiation ends." : "Settling with PayPal: capturing winners, releasing everyone else, paying sellers…"}</p>}
    <Disclosure title={<>Group books · {ledger.holds} holds {ledger.reconciled && <span className="reconciled"><BadgeCheck size={13} aria-hidden="true" /> Reconciled</span>}</>} defaultOpen={!mine}>
      <dl className="books">
        <div><dt>Captured from winners</dt><dd>{usd(ledger.captured_total)} <small>{ledger.captured_count} buyers</small></dd></div>
        <div><dt>Holds released</dt><dd>{usd(ledger.voided_total)} <small>{ledger.voided_count} buyers</small></dd></div>
        {Number(ledger.held_for_shipping) > 0 && <div><dt>Held until the seller ships</dt><dd>{usd(ledger.held_for_shipping)}</dd></div>}
        <div><dt>Maxx fee ({config.platform_fee_percent}%, from sellers{Number(ledger.held_for_shipping) > 0 ? ", taken at payout" : ""})</dt><dd>{usd(ledger.platform_fee)}</dd></div>
        <div><dt>Paid to sellers</dt><dd>{usd(ledger.seller_payouts)}</dd></div>
        {ledger.failed_count > 0 && <div className="warn"><dt>Needs attention</dt><dd>{ledger.failed_count} payments failed</dd></div>}
      </dl>
      {ledger.payouts.length > 0 && <table><thead><tr><th>Seller</th><th>Units</th><th>Gross</th><th>Fee</th><th>Net</th><th>Status</th></tr></thead><tbody>{ledger.payouts.map(row => <tr key={row.seller}><td>{row.seller}</td><td>{row.units}</td><td>{usd(row.gross)}</td><td>{usd(row.fee)}</td><td>{usd(row.net)}</td><td>{row.status === "SENT" ? "Sent" : row.status.toLowerCase()}</td></tr>)}</tbody></table>}
      <p className="small muted">Every dollar captured is Maxx’s fee, a seller payout, or held by Maxx until the seller ships. “Reconciled” means those lines add up to the captured total exactly{ledger.simulated ? ", here against the simulator’s ledger" : ", with PayPal ids behind each line"}. The simulated crowd seeded into demo Blocs places no holds: only real people’s PayPal holds appear here.</p>
      {mine && <p className="small muted">Your PayPal ids: order {shortId(mine.paypal.order)} · authorization {shortId(mine.paypal.authorization)} · capture {shortId(mine.paypal.capture)}</p>}
    </Disclosure>
  </motion.section>;
}
