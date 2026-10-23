"use client";
import { useEffect, useState } from "react";
import { Bot, Check, Copy, FlaskConical, ShieldCheck, Wallet } from "lucide-react";
import { ApiError, request } from "../lib/client";
import { useAuth } from "./auth";
import { useMoneyConfig, type MoneyConfig, type Offer } from "../lib/money";
import { usd } from "../blocs/types";
import type { ScanResult } from "../scan-types";
import { Badge } from "./ui";
import PayPalApproval from "./paypal-approval";
import { FormMessage } from "./auth-ui";

type Pyusd = { address: string; contract: string; chain: string; amount: string; units: number; simulated: boolean };
type Order = { order_id: string; amount: string; method?: "pyusd"; pyusd?: Pyusd };
type Done = { order_id: string; status: string; capture_id?: string; tx_hash?: string };

/**
 * "Let the agent buy it." The agent proposes the cheapest verified offer. A server-side guard checks
 * every charge against what you were shown, and nothing is created until you type the total.
 */
export default function AgentCheckout({ result }: { result: ScanResult }) {
  const config = useMoneyConfig();
  const { user } = useAuth();
  const [offer, setOffer] = useState<Offer | null>(null);
  const [refusal, setRefusal] = useState("");
  const [typed, setTyped] = useState("");
  const [method, setMethod] = useState<"paypal" | "pyusd">("paypal");
  const [order, setOrder] = useState<Order | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [hash, setHash] = useState("");
  const [copied, setCopied] = useState(false);
  const eligible = result.rows.some(row => row.same_item && row.in_stock && row.shipping !== null);
  useEffect(() => { setOffer(null); setOrder(null); setDone(null); setRefusal(""); setError(""); setTyped(""); }, [result.request_id]);
  if (!config?.enabled || !eligible) return null;

  async function propose() {
    setBusy(true); setError(""); setRefusal("");
    try {
      setOffer(await request<Offer>("/api/checkout/propose", { body: { item_title: result.item.title ?? "Scanned item", qty: 1, current_price: result.item.currency === "USD" ? result.item.price : null, rows: result.rows.map(row => ({ title: row.title, url: row.url, price: row.price, shipping: row.shipping, same_item: row.same_item, in_stock: row.in_stock, evidence: row.evidence })) } }));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) { setRefusal("Sign in to let the agent buy for you."); return; }
      setRefusal(cause instanceof Error ? cause.message : "The agent could not make an offer.");
    } finally { setBusy(false); }
  }
  async function confirm() {
    if (!offer) return;
    setBusy(true); setError("");
    try { setOrder(await request<Order>("/api/checkout/confirm", { body: { proposal_token: offer.proposal_token, confirm_total: typed, method } })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not create the order."); }
    finally { setBusy(false); }
  }
  async function capture() {
    if (!order) return;
    setDone(await request<Done>(`/api/checkout/orders/${order.order_id}/capture`, { body: {} }));
  }
  async function verifyPyusd(tx: string) {
    if (!order) return;
    setBusy(true); setError("");
    try { setDone(await request<Done>("/api/checkout/pyusd/verify", { body: { order_id: order.order_id, tx_hash: tx } })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not verify that transaction."); }
    finally { setBusy(false); }
  }
  async function simulateSend() {
    if (!order) return;
    setBusy(true); setError("");
    try { const sent = await request<{ tx_hash: string }>("/api/checkout/pyusd/simulate-send", { body: { order_id: order.order_id } }); setHash(sent.tx_hash); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Simulated send failed."); }
    finally { setBusy(false); }
  }
  async function copy(text: string) { try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* Copy is a convenience. */ } }
  const match = typed.trim() === offer?.total;

  return <section className="agent-checkout" aria-label="Checkout agent">
    <div className="section-heading"><span><Bot size={14} aria-hidden="true" /> Checkout agent</span><Badge tone={config.simulated ? "warn" : "accent"}>{config.simulated ? <><FlaskConical size={11} /> Simulated PayPal</> : "PayPal sandbox"}</Badge></div>
    {!offer && !done && <><p>The agent picks the cheapest offer it can verify as the exact item, in stock, with a known delivered price, and prepares a PayPal order. It cannot spend anything until you approve the exact total.</p>
      <button type="button" className="button primary" disabled={busy || !user} onClick={() => void propose()}><Bot size={16} aria-hidden="true" /> {busy ? "Looking…" : user ? "Ask the agent for an offer" : "Sign in to use the agent"}</button>
      {refusal && <p className="warning" role="status">{refusal}</p>}</>}
    {offer && !done && <div className="offer">
      <div className="offer-main"><div><strong>{offer.merchant}</strong><p>{offer.title}</p></div><div className="offer-total"><span>Delivered total</span><strong>{usd(offer.total)}</strong>{offer.saves && Number(offer.saves) > 0 && <small>{usd(offer.saves)} less than your screenshot</small>}</div></div>
      <ol className="agent-plan" aria-label="What the agent will do">{offer.plan.map(step => <li key={step.tool}><code>{step.tool}</code><span>{step.when}{step.amount ? ` · ${usd(step.amount)}` : ""}</span></li>)}</ol>
      <p className="small muted"><ShieldCheck size={12} aria-hidden="true" /> A guard compares every charge with this offer ({usd(offer.unit_price)} + {usd(offer.shipping)} shipping). Tool names match PayPal’s Agent Toolkit. In this demo the payment goes to the Maxx sandbox account; no goods are shipped.</p>
      {!order && <>
        <fieldset className="pay-method"><legend>Pay with</legend>
          <label className={method === "paypal" ? "is-selected" : ""}><input type="radio" name="method" checked={method === "paypal"} onChange={() => setMethod("paypal")} /> PayPal</label>
          {config.crypto.enabled && <label className={method === "pyusd" ? "is-selected" : ""}><input type="radio" name="method" checked={method === "pyusd"} onChange={() => setMethod("pyusd")} /> PYUSD stablecoin</label>}
        </fieldset>
        <label className="confirm-total">Type the total to approve it: <strong>{offer.total}</strong><input inputMode="decimal" autoComplete="off" value={typed} onChange={event => setTyped(event.target.value)} placeholder={offer.total} aria-invalid={typed !== "" && !match} /></label>
        {error && <FormMessage>{error}</FormMessage>}
        <button type="button" className="button primary" disabled={busy || !match} onClick={() => void confirm()}><Check size={16} aria-hidden="true" /> {busy ? "Preparing…" : `Approve ${usd(offer.total)}`}</button></>}
      {order && order.method !== "pyusd" && <>
        {error && <FormMessage>{error}</FormMessage>}
        <PayPalApproval orderId={order.order_id} config={config as MoneyConfig} label={`Pay ${usd(order.amount)} with PayPal`} onApproved={capture} onError={setError} /></>}
      {order?.method === "pyusd" && order.pyusd && <div className="pyusd-box">
        <p>Send exactly <strong>{order.pyusd.amount} PYUSD</strong> on {order.pyusd.chain || "the configured network"} to:</p>
        <div className="address"><code>{order.pyusd.address}</code><button type="button" className="icon-button" aria-label="Copy address" onClick={() => void copy(order.pyusd!.address)}>{copied ? <Check size={14} /> : <Copy size={14} />}</button></div>
        <p className="small muted">The last three digits identify your order, so send the exact amount. Maxx reads the transaction from the chain and never holds a wallet key.</p>
        {order.pyusd.simulated && <button type="button" className="button" disabled={busy} onClick={() => void simulateSend()}><Wallet size={15} aria-hidden="true" /> Simulate sending from a wallet</button>}
        <label className="confirm-total">Transaction hash<input value={hash} onChange={event => setHash(event.target.value)} placeholder="0x…" autoComplete="off" spellCheck={false} /></label>
        {error && <FormMessage>{error}</FormMessage>}
        <button type="button" className="button primary" disabled={busy || hash.trim().length < 66} onClick={() => void verifyPyusd(hash.trim())}>{busy ? "Checking the chain…" : "Verify payment"}</button></div>}
    </div>}
    {done && <div className="checkout-done" role="status"><Check size={20} aria-hidden="true" /><div><strong>Paid {offer ? usd(offer.total) : ""}</strong><p>{done.tx_hash ? `PYUSD transaction ${done.tx_hash.slice(0, 12)}…` : `PayPal capture ${done.capture_id ?? ""}`}. See it under Receipts.</p></div></div>}
  </section>;
}
