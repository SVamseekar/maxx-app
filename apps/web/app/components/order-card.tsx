"use client";
import { useConfirm } from "./confirm-provider";
import { useState } from "react";
import { Check, ChevronDown, MessageSquare, PackageCheck, Truck, Undo2, Building2 } from "lucide-react";
import { request } from "../lib/client";
import { useAction } from "../lib/use-action";
import { relativeTime } from "../lib/auth-helpers";
import { CASE_KINDS, STATUS_LABEL, deadlineText, type AddressSummary, type OrderView, type TraderInfo } from "../lib/orders";
import { countryName } from "../lib/countries";
import { usd } from "../blocs/types";
import { Badge } from "./ui";
import { FormMessage } from "./auth-ui";
import AddressForm from "./address-form";
import TrackingTimeline from "./tracking-timeline";

const TONE = { AWAITING_ADDRESS: "warn", AWAITING_SHIPMENT: "accent", SHIPPED: "accent", DELIVERED: "good", CANCELLED: "neutral", REFUNDED: "neutral" } as const;

export default function OrderCard({ order, addresses, onChange, onAddress }: { order: OrderView; addresses: AddressSummary[]; onChange: () => Promise<void>; onAddress: (address: AddressSummary) => void }) {
  const confirmAction = useConfirm();
  const action = useAction();
  const [choice, setChoice] = useState(addresses[0]?.id ?? "");
  const [adding, setAdding] = useState(addresses.length === 0);
  const [trader, setTrader] = useState<TraderInfo | null>(null);
  const [reporting, setReporting] = useState(false);
  const [kind, setKind] = useState("not_received");
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const active = order.cases.find(c => c.status === "OPEN") ?? null;
  const past = order.cases.filter(c => c.status !== "OPEN");
  const run = (task: () => Promise<unknown>, done?: string) => action.run(async () => { await task(); await onChange(); return done; });
  async function showTrader() { if (trader) { setTrader(null); return; } await action.run(async () => { setTrader(await request<TraderInfo>(`/api/sellers/${order.seller.code}`)); }); }

  return <article className="order-card" aria-label={order.title}>
    <header><div><h2>{order.title}</h2><p className="muted small">Sold by <strong>{order.seller.name}</strong> · ordered {relativeTime(order.created_at)}</p></div><div className="order-price"><strong>{usd(order.amount)}</strong><Badge tone={TONE[order.status]}>{STATUS_LABEL[order.status]}</Badge></div></header>
    {!["CANCELLED", "REFUNDED"].includes(order.status) && <ol className="order-timeline" aria-label="Order progress">{["Address", "Preparing", "Shipped", "Delivered"].map((label, index) => { const stage = ["AWAITING_ADDRESS", "AWAITING_SHIPMENT", "SHIPPED", "DELIVERED"].indexOf(order.status); return <li key={label} className={index < stage ? "done" : index === stage ? "current" : ""} aria-current={index === stage ? "step" : undefined}>{label}</li>; })}</ol>}
    {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}

    {order.status === "AWAITING_ADDRESS" && <section className="order-step" aria-label="Delivery address">
      <p><strong>Where should it go?</strong> The seller ships the goods, and needs an address. Give one {deadlineText(order.ship_by)} or the order is cancelled and refunded.</p>
      {addresses.length > 0 && !adding && <div className="address-choice"><label className="select-field">Saved address<select value={choice} onChange={event => setChoice(event.target.value)}>{addresses.map(a => <option key={a.id} value={a.id}>{a.label || a.name} · {a.line1}, {a.city} {a.postal}, {countryName(a.country)}</option>)}</select></label>
        <div className="inline-actions"><button type="button" className="button primary" disabled={action.busy || !choice} onClick={() => void run(() => request(`/api/orders/${order.id}/address`, { body: { address_id: choice } }), "Address sent to the seller.")}>Use this address</button><button type="button" className="quiet-button" onClick={() => setAdding(true)}>Add another</button></div></div>}
      {adding && <div><AddressForm onSaved={address => { onAddress(address); setChoice(address.id); setAdding(false); }} />{addresses.length > 0 && <button type="button" className="quiet-button" onClick={() => setAdding(false)}>Use a saved one</button>}</div>}
    </section>}

    {order.status === "AWAITING_SHIPMENT" && <p className="order-note"><Truck size={15} aria-hidden="true" /> The seller must ship {deadlineText(order.ship_by)}. If they do not, you are refunded in full. You can cancel any time before it ships.</p>}
    {order.simulated && <p className="order-note muted small">Sold by one of the demo’s simulated sellers. An automatic stand-in ships it with simulated tracking; your money moves exactly as with a real seller.</p>}
    {order.status === "SHIPPED" && <p className="order-note"><PackageCheck size={15} aria-hidden="true" /> Shipped with {order.carrier || "the seller’s carrier"}. Tracking <code>{order.tracking}</code>. {order.tracking_events.length ? "The carrier’s updates are below; it is marked delivered automatically." : "Tell us when it arrives."}</p>}
    {(order.status === "SHIPPED" || order.status === "DELIVERED") && <TrackingTimeline events={order.tracking_events} status={order.tracking_status} estimated={order.estimated_delivery} simulated={order.tracking_simulated} />}
    {order.status === "DELIVERED" && <p className="order-note"><Check size={15} aria-hidden="true" /> Delivered. You have 60 days from the order to report a problem.</p>}
    {(order.status === "CANCELLED" || order.status === "REFUNDED") && <p className="order-note"><Undo2 size={15} aria-hidden="true" /> Your full payment was refunded to your PayPal.</p>}

    <div className="order-actions">
      {(order.status === "AWAITING_ADDRESS" || order.status === "AWAITING_SHIPMENT") && <button type="button" disabled={action.busy} onClick={async () => { if (await confirmAction("Cancel this order? You get a full refund and the seller keeps nothing.")) void run(() => request(`/api/orders/${order.id}/cancel`, { body: {} }), "Order cancelled. Your refund is on its way."); }}>Cancel and refund</button>}
      {order.status === "SHIPPED" && <button type="button" className="button primary" disabled={action.busy} onClick={() => void run(() => request(`/api/orders/${order.id}/delivered`, { body: {} }))}>It arrived</button>}
      {(order.status === "SHIPPED" || order.status === "DELIVERED") && !active && <button type="button" disabled={action.busy} onClick={() => setReporting(value => !value)}><MessageSquare size={14} aria-hidden="true" /> Report a problem</button>}
      <button type="button" className="quiet-button" onClick={() => void showTrader()}><Building2 size={14} aria-hidden="true" /> Seller details <ChevronDown size={13} aria-hidden="true" /></button>
    </div>

    {trader && <dl className="trader-info">{trader.simulated && <div><dt>Note</dt><dd>This is a simulated seller in the Maxx demo, not a real business.</dd></div>}<div><dt>Seller</dt><dd>{trader.business_name} ({trader.business_type === "company" ? "company" : "individual"})</dd></div><div><dt>Legal name</dt><dd>{trader.legal_name}</dd></div><div><dt>Address</dt><dd>{trader.address}</dd></div><div><dt>Contact</dt><dd>{trader.support_email} · {trader.phone}</dd></div>{trader.trade_register_no && <div><dt>Register number</dt><dd>{trader.trade_register_no}</dd></div>}{trader.website && <div><dt>Website</dt><dd>{trader.website}</dd></div>}<div><dt>Ships within</dt><dd>{trader.ship_within_days} days</dd></div><div><dt>Returns</dt><dd>{trader.return_days} days · {trader.return_policy}</dd></div><div><dt>Certification</dt><dd>{trader.self_certified ? "The seller certified it sells only lawful, genuine, new goods." : "Not certified"}</dd></div></dl>}

    {reporting && !active && <form className="problem-form" onSubmit={event => { event.preventDefault(); void run(() => request(`/api/orders/${order.id}/problem`, { body: { kind, message } }), "Reported. The seller must reply within 24 hours or you are refunded.").then(() => { setReporting(false); setMessage(""); }); }}>
      <label className="select-field">What went wrong?<select value={kind} onChange={event => setKind(event.target.value)}>{Object.entries(CASE_KINDS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="select-field">Tell the seller what happened<textarea value={message} onChange={event => setMessage(event.target.value)} minLength={10} maxLength={2000} rows={4} required placeholder="What did you expect, and what happened instead?" /></label>
      <div className="inline-actions"><button className="button primary" disabled={action.busy || message.trim().length < 10}>Send report</button><button type="button" className="quiet-button" onClick={() => setReporting(false)}>Cancel</button></div></form>}

    {active && <section className="case-thread" aria-label="Problem report"><h3>Open problem: {CASE_KINDS[active.kind] ?? active.kind}</h3><p className="small muted">The seller must reply {deadlineText(active.respond_by)}, or you are refunded.</p>
      <ol>{active.messages.map((m, i) => <li key={i} className={`from-${m.actor}`}><strong>{m.actor === "buyer" ? "You" : m.actor === "seller" ? order.seller.name : "Maxx"}</strong><p>{m.body}</p></li>)}</ol>
      <form className="inline-form" onSubmit={event => { event.preventDefault(); void run(() => request(`/api/cases/${active.id}/message`, { body: { body: reply } })).then(() => setReply("")); }}><label className="select-field">Add a message<input value={reply} onChange={event => setReply(event.target.value)} maxLength={2000} minLength={2} required /></label><button className="button" disabled={action.busy || reply.trim().length < 2}>Send</button><button type="button" className="quiet-button" disabled={action.busy} onClick={() => void run(() => request(`/api/cases/${active.id}/withdraw`, { body: {} }), "Problem withdrawn.")}>It is sorted, withdraw</button></form></section>}
    {past.length > 0 && <details className="case-history"><summary>Earlier problems ({past.length})</summary>{past.map(c => <p key={c.id}>{CASE_KINDS[c.kind] ?? c.kind}: {c.status.replaceAll("_", " ").toLowerCase()}. {c.resolution}</p>)}</details>}
  </article>;
}
