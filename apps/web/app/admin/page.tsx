"use client";
import FilterToolbar from "../components/filter-toolbar";
import SectionNav from "../components/section-nav";
import { matchesQuery } from "../lib/collection";
import { useConfirm } from "../components/confirm-provider";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ShieldAlert } from "lucide-react";
import { Badge, ErrorNotice, PageIntro, Working } from "../components/ui";
import { FormMessage } from "../components/auth-ui";
import { useAuth } from "../components/auth";
import { useSecure } from "../components/reauth";
import { request } from "../lib/client";
import { useAction } from "../lib/use-action";
import { loginPath, relativeTime } from "../lib/auth-helpers";
import { CASE_KINDS } from "../lib/orders";
import { countryName } from "../lib/countries";
import { aiSpendRows, guardSummary, type AiOverview } from "./ai-spend";

type Hit = { entry_id: string; name: string; program: string; score: number; cleared?: boolean };
type SellerRow = { code: string; business_name: string; legal_name: string; business_type: string; country: string; address_line1: string; address_city: string; address_postal: string; phone: string; support_email: string; website: string; trade_register_no: string; ship_within_days: number; ships_to: string; return_days: number; return_policy: string; status: string; review_note: string; strikes: number; payout_email: string; payout_verified: boolean; identity_status: string; identity_name: string; identity_country: string; screening_status: string; screening_hits: Hit[]; tax_id_last4: string; demo: boolean; next_step: string | null };
type FlaggedOrder = { id: string; title: string; seller: string; status: string; carrier: string; tracking_status: string; flag: string };
type ListingRow = { id: string; title: string; seller: string; seller_name: string; gtin: string; category: string; active: boolean; created_at: number };
type CaseRow = { id: string; order_id: string; kind: string; opened_at: number; respond_by: number; overdue: boolean; messages: { actor: string; body: string; at: number }[] };
type Overview = { payments_frozen: boolean; mode: string; review_mode: string; modes: Record<string, string>; health: Record<string, number | null | Record<string, number>>; pending_sellers: SellerRow[]; recent_sellers: SellerRow[]; open_cases: CaseRow[]; flagged_orders: FlaggedOrder[]; listings: ListingRow[]; audit: { id: number; at: number; actor: string; action: string; subject: string; detail: string }[]; ai: AiOverview };

export default function Admin() {
  const confirmAction = useConfirm();
  const { user, status } = useAuth();
  const router = useRouter();
  const secure = useSecure();
  const [data, setData] = useState<Overview | null>(null);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [recon, setRecon] = useState("");
  const action = useAction();
  const [auditQuery, setAuditQuery] = useState("");
  const [auditFilter, setAuditFilter] = useState("all");
  const [sellerQuery, setSellerQuery] = useState("");
  const [sellerFilter, setSellerFilter] = useState("all");
  useEffect(() => { if (status === "ready" && !user) router.replace(loginPath("/admin")); }, [status, user, router]);
  const load = useCallback(async () => {
    try { setData(await request<Overview>("/api/admin/overview")); setError(""); }
    catch (cause) { if ((cause as { status?: number }).status === 403) setDenied(true); else setError(cause instanceof Error ? cause.message : "Cannot load the console."); }
  }, []);
  useEffect(() => { if (user) void load(); }, [user?.id, load]); // eslint-disable-line react-hooks/exhaustive-deps
  const decide = (code: string, decision: string) => action.run(async () => { await secure(() => request(`/api/admin/sellers/${code}/decision`, { body: { action: decision, note } })); setNote(""); await load(); return `Seller ${decision}d.`.replace("ee", "e"); });
  const screen = (code: string, decision: "clear" | "block") => action.run(async () => { await secure(() => request(`/api/admin/sellers/${code}/screening`, { body: { decision, note } })); setNote(""); await load(); return decision === "clear" ? "Screening cleared." : "Seller blocked and suspended."; });
  if (denied) return <main id="main-content"><div className="empty-state"><ShieldAlert size={28} /><h2>Administrators only.</h2><p>This console is for people who run Maxx. Set ADMIN_EMAILS on the server to grant access.</p></div></main>;
  if (!data) return <main id="main-content">{error ? <ErrorNotice message={error} retry={() => void load()} /> : <div className="loading-surface"><Working label="Loading the operator console" /></div>}</main>;
  const count = (key: string) => (typeof data.health[key] === "number" ? (data.health[key] as number) : 0);
  const attention = count("failed_payouts") + count("stuck_payments") + count("partial_settlements") + count("flagged_shipments");
  const outbox = (data.health.email_outbox ?? {}) as Record<string, number>;
  const metrics = Object.entries(data.health).filter(([, value]) => typeof value === "number" || value === null) as [string, number | null][];
  const auditRows = data.audit.filter(row => matchesQuery(`${row.actor} ${row.action} ${row.subject} ${row.detail}`, auditQuery) && (auditFilter === "all" || row.action === auditFilter));
  const sellerRows = data.recent_sellers.filter(row => matchesQuery(`${row.code} ${row.business_name} ${row.legal_name}`, sellerQuery) && (sellerFilter === "all" || row.status === sellerFilter));
  return <main id="main-content" className="admin-page">
    <PageIntro title="Operator console." description="Seller review, disputes, payment health and the emergency brake. Every action here is written to the audit log."><Badge tone={data.payments_frozen ? "warn" : "good"}>{data.payments_frozen ? "Payments paused" : "Payments running"}</Badge></PageIntro>
    <SectionNav items={[{id:"health-h",label:"Payment health"},{id:"ai-h",label:"AI spend"},{id:"queue-h",label:"Review queue"},{id:"flags-h",label:"Delivery problems"},{id:"cases-h",label:"Problems"},{id:"listings-h",label:"Listings"},{id:"sellers-h",label:"Sellers"},{id:"audit-h",label:"Audit log"}]} />
    {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
    <section className="seller-card" aria-labelledby="health-h">
      <h2 id="health-h">Payment health</h2>
      <div className="health-grid">{metrics.map(([key, value]) => <div key={key} className={(value ?? 0) > 0 && ["failed_payouts", "stuck_payments", "partial_settlements", "flagged_shipments"].includes(key) || (key === "sanctions_list_age_hours" && (value === null || value > 48)) ? "warn" : ""}><strong>{value ?? "never"}</strong><span>{key.replaceAll("_", " ")}</span></div>)}<div className={(outbox.failed ?? 0) > 0 ? "warn" : ""}><strong>{outbox.failed ?? 0}</strong><span>emails failed · {outbox.queued ?? 0} queued · {outbox.sent ?? 0} sent today</span></div></div>
      <p className="muted small">Payments: {data.mode} · tracking: {data.modes.tracking} · identity checks: {data.modes.identity} · negotiation: {data.modes.negotiation} · seller review: {data.review_mode}{attention > 0 && <> · <AlertTriangle size={13} aria-hidden="true" /> {attention} item{attention > 1 ? "s" : ""} need attention</>}</p>
      <div className="inline-actions">
        <button type="button" className={data.payments_frozen ? "button primary" : ""} disabled={action.busy} onClick={async () => { if (await confirmAction(data.payments_frozen ? "Resume new holds, charges and payouts?" : "Pause ALL new holds, charges and payouts? Existing holds stay safe.")) void action.run(async () => { await secure(() => request("/api/admin/payments/freeze", { body: { frozen: !data.payments_frozen } })); await load(); return data.payments_frozen ? "Payments resumed." : "Payments paused."; }); }}>{data.payments_frozen ? "Resume payments" : "Pause all payments"}</button>
        <button type="button" disabled={action.busy} onClick={() => void action.run(async () => { const result = await request<{ checked: number; mismatches: unknown[] }>("/api/admin/reconcile"); setRecon(`Checked ${result.checked} payments against PayPal. ${result.mismatches.length === 0 ? "No differences." : `${result.mismatches.length} differ: ${JSON.stringify(result.mismatches).slice(0, 300)}`}`); })}>Reconcile with PayPal</button>
      </div>
      {recon && <p className="small" role="status">{recon}</p>}
    </section>

    <section className="seller-card" aria-labelledby="ai-h">
      <h2 id="ai-h">AI spend <Badge tone={data.ai.paused ? "warn" : "good"}>{data.ai.paused ? "Live AI paused" : "Live AI running"}</Badge></h2>
      <div className="health-grid">{aiSpendRows(data.ai.budget).map(row => <div key={row.label} className={row.warn ? "warn" : ""}><strong>{row.text}</strong><span>{row.label}</span></div>)}</div>
      <p className="muted small">Last 24 hours: {Object.entries(data.ai.roles).filter(([role]) => role !== "models").map(([role, r]) => `${role} ${r.calls} call${r.calls === 1 ? "" : "s"}${r.refused ? `, ${r.refused} refused` : ""}${r.rejected ? `, ${r.rejected} rejected` : ""} ($${Number(r.cost_usd).toFixed(4)})`).join(" · ") || "no model calls"}.</p>
      <p className="muted small">Guards fired: {guardSummary(data.ai.guards).join(" · ") || "none"}. Days reset at 00:00 UTC; spend is an estimate from Token Factory list prices.</p>
      <div className="inline-actions">
        <button type="button" className={data.ai.paused ? "button primary" : ""} disabled={action.busy} onClick={async () => { if (await confirmAction(data.ai.paused ? "Resume live AI calls?" : "Pause ALL live AI calls? Scans and negotiations say why; the rest of Maxx keeps working.")) void action.run(async () => { await secure(() => request("/api/admin/ai/pause", { body: { paused: !data.ai.paused } })); await load(); return data.ai.paused ? "Live AI resumed." : "Live AI paused."; }); }}>{data.ai.paused ? "Resume live AI" : "Pause live AI"}</button>
      </div>
    </section>

    <section className="seller-card" aria-labelledby="queue-h">
      <h2 id="queue-h">Sellers awaiting review ({data.pending_sellers.length})</h2>
      {data.pending_sellers.length === 0 ? <p className="muted">Nothing waiting.</p> : data.pending_sellers.map(seller => <article key={seller.code} className="seller-order"><header><div><h3>{seller.business_name} <span className="muted small">({seller.code})</span></h3><p className="muted small">{seller.legal_name} · {seller.business_type} · {countryName(seller.country)}</p></div><Badge tone="warn">Under review</Badge></header>
        <dl className="trader-info"><div><dt>Address</dt><dd>{seller.address_line1}, {seller.address_city} {seller.address_postal}</dd></div><div><dt>Contact</dt><dd>{seller.support_email} · {seller.phone}</dd></div>{seller.website && <div><dt>Website</dt><dd>{seller.website}</dd></div>}<div><dt>Register no.</dt><dd>{seller.trade_register_no || "none given"}</dd></div><div><dt>Ships</dt><dd>within {seller.ship_within_days} days to {seller.ships_to}</dd></div><div><dt>Returns</dt><dd>{seller.return_days} days · {seller.return_policy}</dd></div><div><dt>Payout</dt><dd>{seller.payout_email} {seller.payout_verified ? "(confirmed)" : "(not confirmed)"}</dd></div><div><dt>Identity</dt><dd>{seller.identity_status}{seller.identity_name && ` · ${seller.identity_name} (${seller.identity_country || "?"})`}</dd></div><div><dt>Waiting on</dt><dd>{seller.next_step ?? "nothing"}</dd></div></dl>
        {seller.screening_status === "review" && <div className="screening"><p><ShieldAlert size={14} aria-hidden="true" /> <strong>Possible sanctions match.</strong> Compare against the OFAC entry before deciding. The seller is not told about this.</p><ul>{seller.screening_hits.filter(hit => !hit.cleared).map(hit => <li key={hit.entry_id}>{hit.name} · {hit.program || "OFAC SDN"} · similarity {Math.round(hit.score * 100)}%{/^\d+$/.test(hit.entry_id) && <> · entry {hit.entry_id}</>}</li>)}</ul><div className="inline-actions"><button disabled={action.busy || note.trim().length < 3} onClick={() => void screen(seller.code, "clear")}>Not the same party: clear</button><button disabled={action.busy || note.trim().length < 3} onClick={async () => { if (await confirmAction("Block this seller for good? Their listings end and every buyer's hold is released.")) void screen(seller.code, "block"); }}>Confirmed match: block</button></div></div>}
        <label className="select-field">Note (kept on record, shown to the seller on rejection)<input value={note} onChange={event => setNote(event.target.value)} maxLength={500} /></label>
        <div className="inline-actions"><button className="button primary" disabled={action.busy} onClick={() => void decide(seller.code, "approve")}>Approve</button><button disabled={action.busy || note.trim().length < 3} onClick={() => void decide(seller.code, "reject")}>Reject (needs a note)</button></div></article>)}
    </section>

    <section className="seller-card" aria-labelledby="flags-h">
      <h2 id="flags-h">Delivery problems ({data.flagged_orders.length})</h2>
      <p className="muted small">Payouts held because a parcel was returned, never scanned, sent to another country, or its tracking number was questioned. Release one only after checking with the carrier.</p>
      {data.flagged_orders.length === 0 ? <p className="muted">Nothing held.</p> : data.flagged_orders.map(item => <article key={item.id} className="seller-order"><header><div><h3>{item.title}</h3><p className="muted small">Order {item.id.slice(0, 8)} · seller {item.seller} · {item.carrier} · {item.tracking_status.replaceAll("_", " ") || "no carrier status"}</p></div><Badge tone="warn">Payout held</Badge></header><p className="order-note">{item.flag}</p>
        <label className="select-field">What you checked (kept on record)<input value={note} onChange={event => setNote(event.target.value)} maxLength={500} /></label>
        <div className="inline-actions"><button disabled={action.busy || note.trim().length < 3} onClick={() => void action.run(async () => { const result = await secure(() => request<{ payout: string }>(`/api/admin/orders/${item.id}/clear-flag`, { body: { note } })); setNote(""); await load(); return `Released. Payout: ${result.payout.toLowerCase()}.`; })}>Release the payout</button></div></article>)}
    </section>

    <section className="seller-card" aria-labelledby="cases-h">
      <h2 id="cases-h">Open problems ({data.open_cases.length})</h2>
      {data.open_cases.length === 0 ? <p className="muted">No open problems.</p> : data.open_cases.map(item => <article key={item.id} className="seller-order"><header><div><h3>{CASE_KINDS[item.kind] ?? item.kind}</h3><p className="muted small">Order {item.order_id.slice(0, 8)} · opened {relativeTime(item.opened_at)}</p></div><Badge tone={item.overdue ? "warn" : "neutral"}>{item.overdue ? "Seller overdue" : "Open"}</Badge></header>
        <ol className="case-messages">{item.messages.map((m, i) => <li key={i} className={`from-${m.actor}`}><strong>{m.actor}</strong><p>{m.body}</p></li>)}</ol>
        <label className="select-field">Reason for your decision (sent to both sides)<input value={note} onChange={event => setNote(event.target.value)} maxLength={500} /></label>
        <div className="inline-actions"><button className="button primary" disabled={action.busy || note.trim().length < 3} onClick={() => void action.run(async () => { await secure(() => request(`/api/admin/cases/${item.id}/resolve`, { body: { refund: true, note } })); setNote(""); await load(); return "Buyer refunded."; })}>Refund the buyer</button><button disabled={action.busy || note.trim().length < 3} onClick={() => void action.run(async () => { await secure(() => request(`/api/admin/cases/${item.id}/resolve`, { body: { refund: false, note } })); setNote(""); await load(); return "Declined."; })}>Decline the refund</button></div></article>)}
    </section>

    <section className="seller-card" aria-labelledby="listings-h">
      <h2 id="listings-h">Seller listings ({data.listings.filter(row => row.active).length} live)</h2>
      {data.listings.length === 0 ? <p className="muted">No listings yet.</p> : <div className="table-wrap"><table><thead><tr><th scope="col">Product</th><th scope="col">Seller</th><th scope="col">GTIN</th><th scope="col">Category</th><th scope="col">Status</th><th scope="col">Action</th></tr></thead><tbody>{data.listings.map(row => <tr key={row.id}><td>{row.title}</td><td>{row.seller_name} ({row.seller})</td><td>{row.gtin || "—"}</td><td>{row.category}</td><td>{row.active ? "live" : "ended"}</td><td>{row.active && <button disabled={action.busy || note.trim().length < 3} title="Write the reason in a note field first" onClick={async () => { if (await confirmAction(`Take down "${row.title}"? Its Bloc ends and every buyer's hold is released.`)) void action.run(async () => { await secure(() => request(`/api/admin/listings/${row.id}/takedown`, { body: { note } })); setNote(""); await load(); return "Listing removed; holds are being released."; }); }}>Take down</button>}</td></tr>)}</tbody></table></div>}
      <label className="select-field">Reason for a take-down (kept on record)<input value={note} onChange={event => setNote(event.target.value)} maxLength={500} /></label>
    </section>

    <section className="seller-card" aria-labelledby="sellers-h">
      <h2 id="sellers-h">Recent sellers</h2>
      <FilterToolbar query={sellerQuery} onQuery={setSellerQuery} filter={sellerFilter} onFilter={setSellerFilter} count={sellerRows.length} label="Search sellers" placeholder="Business name or seller code" options={[{value:"all",label:"All sellers"},{value:"ACTIVE",label:"Active"},{value:"SUSPENDED",label:"Suspended"},{value:"UNDER_REVIEW",label:"Under review"}]} />
      {sellerRows.length === 0 && <p className="empty-state">No sellers match these filters.</p>}
      <div className="table-wrap"><table><thead><tr><th scope="col">Code</th><th scope="col">Business</th><th scope="col">Status</th><th scope="col">Strikes</th><th scope="col">Action</th></tr></thead><tbody>{sellerRows.map(seller => <tr key={seller.code}><td>{seller.code}</td><td>{seller.business_name}</td><td>{seller.status.replaceAll("_", " ").toLowerCase()}</td><td>{seller.strikes}</td><td>{seller.status === "ACTIVE" && <button disabled={action.busy} onClick={async () => { if (await confirmAction(`Suspend ${seller.business_name}? Offers pause and payouts stop.`)) void decide(seller.code, "suspend"); }}>Suspend</button>}{seller.status === "SUSPENDED" && <button disabled={action.busy} onClick={() => void decide(seller.code, "reinstate")}>Reinstate</button>}</td></tr>)}</tbody></table></div>
    </section>

    <section className="seller-card" aria-labelledby="audit-h">
      <h2 id="audit-h">Audit log (latest)</h2>
      <FilterToolbar query={auditQuery} onQuery={setAuditQuery} filter={auditFilter} onFilter={setAuditFilter} count={auditRows.length} label="Search audit records" placeholder="Person, action or reference" options={[{value:"all",label:"All actions"}, ...Array.from(new Set(data.audit.map(row => row.action))).map(action => ({value:action,label:action.replaceAll("_"," ")}))]} />
      {auditRows.length === 0 && <p className="empty-state">No audit records match these filters.</p>}
      <div className="table-wrap"><table><thead><tr><th scope="col">When</th><th scope="col">Who</th><th scope="col">What</th><th scope="col">Subject</th><th scope="col">Detail</th></tr></thead><tbody>{auditRows.map(row => <tr key={row.id}><td>{relativeTime(row.at)}</td><td>{row.actor}</td><td>{row.action}</td><td>{row.subject.slice(0, 18)}</td><td>{row.detail}</td></tr>)}</tbody></table></div>
    </section>
  </main>;
}
