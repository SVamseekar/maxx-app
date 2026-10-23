"use client";
import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, Clock, Mail, ShieldCheck, XCircle } from "lucide-react";
import { request } from "../lib/client";
import { useAction } from "../lib/use-action";
import { Field, FormMessage, SubmitButton } from "./auth-ui";
import { ErrorNotice, Working } from "./ui";
import { usd } from "../blocs/types";
import ApplyForm from "./seller/apply-form";
import OffersTab from "./seller/offers-tab";
import OrdersTab from "./seller/orders-tab";
import CasesTab from "./seller/cases-tab";
import ProfileTab from "./seller/profile-tab";
import type { Offer, Opportunity, Overview, Profile, Result, SellerCase, SellerOrder } from "./seller/types";

export default function SellerConsole() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => { try { setOverview(await request<Overview>("/api/seller")); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Cannot load the seller console."); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (error) return <ErrorNotice message={error} retry={() => void load()} />;
  if (!overview) return <div className="loading-surface"><Working label="Loading the seller console" /></div>;
  const seller = overview.seller;
  if (!seller) return <ApplyForm overview={overview} onDone={load} />;
  if (seller.status === "SUSPENDED") return <Notice icon={<ShieldCheck size={28} />} title="This seller account is suspended." body={seller.review_note || "Offers are paused and no payouts are sent. Contact seller support to resolve it."} />;
  if (seller.status === "REJECTED") return <Notice icon={<XCircle size={28} />} title="This application was not approved." body={seller.review_note || "You can write to seller support if you think this is a mistake."} />;
  if (seller.status === "CLOSED") return <Notice icon={<XCircle size={28} />} title="This seller account is closed." body="Trader records are kept for the period the law requires." />;
  if (!seller.payout_verified) return <Verify profile={seller} onDone={load} />;
  if (seller.status === "UNDER_REVIEW") return <Notice icon={<Clock size={28} />} title="Your application is under review." body="Your payout email is confirmed. A person at Maxx is checking your details, and you will be able to publish offers as soon as you are approved. We will email you." />;
  return <Console overview={overview} profile={seller} reload={load} />;
}

function Notice({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return <div className="empty-state" role="status">{icon}<h2>{title}</h2><p>{body}</p></div>;
}

function Verify({ profile, onDone }: { profile: Profile; onDone: () => Promise<void> }) {
  const [code, setCode] = useState("");
  const action = useAction();
  return <section className="seller-card" aria-labelledby="verify-h">
    <h2 id="verify-h"><Mail size={18} aria-hidden="true" /> Confirm your payout email</h2>
    <p className="muted">We sent a six-digit code to <strong>{profile.payout_email}</strong>. It expires in 10 minutes. You cannot publish offers or be paid until it is confirmed.</p>
    {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
    <form onSubmit={event => { event.preventDefault(); void action.run(async () => { await request("/api/seller/payout-verify", { body: { code } }); await onDone(); }); }}>
      <Field label="Six-digit code" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={event => setCode(event.target.value)} maxLength={6} required />
      <SubmitButton busy={action.busy} disabled={code.length !== 6}>Confirm</SubmitButton>
    </form>
    <button type="button" className="quiet-button" disabled={action.busy} onClick={() => void action.run(async () => { await request("/api/seller/payout-code", { body: {} }); return "A new code is on its way."; })}>Send a new code</button>
  </section>;
}

const TABS = [{ id: "offers", label: "Offers and demand" }, { id: "orders", label: "Orders to ship" }, { id: "problems", label: "Problems" }, { id: "account", label: "Account" }] as const;
type TabId = (typeof TABS)[number]["id"];

function Console({ overview, profile, reload }: { overview: Overview; profile: Profile; reload: () => Promise<void> }) {
  const [tab, setTab] = useState<TabId>("offers");
  const [opportunities, setOpportunities] = useState<Opportunity[] | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [results, setResults] = useState<Result[]>([]);
  const [orders, setOrders] = useState<SellerOrder[]>([]);
  const [cases, setCases] = useState<SellerCase[]>([]);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try {
      const [o, mine, r, ord, cs] = await Promise.all([request<Opportunity[]>("/api/seller/opportunities"), request<Offer[]>("/api/seller/offers"), request<Result[]>("/api/seller/results"), request<SellerOrder[]>("/api/seller/orders"), request<SellerCase[]>("/api/seller/cases")]);
      setOpportunities(o); setOffers(mine); setResults(r); setOrders(ord); setCases(cs); setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Cannot load your console."); }
  }, []);
  useEffect(() => { void refresh(); const timer = setInterval(() => void refresh(), 15000); return () => clearInterval(timer); }, [refresh]);
  const toShip = orders.filter(o => o.status === "AWAITING_SHIPMENT").length;
  const openCases = cases.filter(c => c.status === "OPEN").length;
  const earned = results.reduce((sum, row) => sum + (row.payout?.status === "SENT" ? Number(row.payout.net) : 0), 0);
  const badge: Record<TabId, number> = { offers: 0, orders: toShip, problems: openCases, account: 0 };
  const both = async () => { await refresh(); await reload(); };
  return <div className="seller-console">
    <div className="seller-head"><div><h2>{profile.business_name}</h2><p className="muted small">Seller {profile.code} · payouts to {profile.payout_email} <BadgeCheck size={13} aria-label="verified" /></p></div><div className="seller-earned"><span>Paid out so far</span><strong>{usd(earned)}</strong></div></div>
    {error && <ErrorNotice message={error} retry={() => void refresh()} />}
    {(toShip > 0 || openCases > 0) && <p className="notice-strip" role="status">{toShip > 0 && `${toShip} order${toShip > 1 ? "s" : ""} to ship. `}{openCases > 0 && `${openCases} open problem${openCases > 1 ? "s" : ""}: reply within 24 hours.`}</p>}
    <div className="tabs" role="tablist" aria-label="Seller console">{TABS.map(item => <button key={item.id} role="tab" id={`tab-${item.id}`} tabIndex={tab === item.id ? 0 : -1} onKeyDown={event => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; event.preventDefault(); const index = TABS.findIndex(t => t.id === tab); const next = event.key === "Home" ? TABS[0] : event.key === "End" ? TABS[TABS.length - 1] : TABS[(index + (event.key === "ArrowRight" ? 1 : -1) + TABS.length) % TABS.length]; setTab(next.id); document.getElementById(`tab-${next.id}`)?.focus(); }} aria-selected={tab === item.id} aria-controls={`panel-${item.id}`} className={tab === item.id ? "is-selected" : ""} onClick={() => setTab(item.id)}>{item.label}{badge[item.id] > 0 && <span className="tab-count">{badge[item.id]}</span>}</button>)}</div>
    <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
      {tab === "offers" && <OffersTab overview={overview} opportunities={opportunities} offers={offers} results={results} reload={refresh} />}
      {tab === "orders" && <OrdersTab orders={orders} reload={refresh} />}
      {tab === "problems" && <CasesTab cases={cases} reload={refresh} />}
      {tab === "account" && <ProfileTab overview={overview} profile={profile} reload={both} />}
    </div>
  </div>;
}
