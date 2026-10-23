"use client";
import FilterToolbar from "../components/filter-toolbar";
import { matchesQuery } from "../lib/collection";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Bitcoin, CreditCard, Receipt as ReceiptIcon } from "lucide-react";
import { AppFooter, Badge, ErrorNotice, PageIntro, Working } from "../components/ui";
import { useAuth } from "../components/auth";
import { request } from "../lib/client";
import { loginPath, relativeTime } from "../lib/auth-helpers";
import { shortId, useMoneyConfig, type Receipt } from "../lib/money";
import { usd } from "../blocs/types";

const TONE = { CAPTURED: "good", VOIDED: "neutral", AUTHORIZED: "accent", CAPTURE_FAILED: "warn", FAILED: "warn", REFUNDED: "neutral" } as const;
const LABEL: Record<string, string> = { CAPTURED: "Paid", VOIDED: "Hold released", AUTHORIZED: "Hold in place", CAPTURE_FAILED: "Declined", VOID_PENDING: "Releasing", CREATED: "Not completed", APPROVED: "Not completed", FAILED: "Failed", REFUNDED: "Refunded" };

export default function Receipts() {
  const { user, status } = useAuth();
  const router = useRouter();
  const config = useMoneyConfig();
  const [items, setItems] = useState<Receipt[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  useEffect(() => { if (status === "ready" && !user) router.replace(loginPath("/receipts")); }, [status, user, router]);
  async function load() { setError(""); try { setItems(await request<Receipt[]>("/api/money/receipts")); } catch (cause) { setError(cause instanceof Error ? cause.message : "Cannot load your receipts."); } }
  useEffect(() => { if (user && config?.enabled) void load(); }, [user?.id, config?.enabled]); // eslint-disable-line react-hooks/exhaustive-deps
  const paid = (items ?? []).reduce((sum, item) => sum + (item.paid ? Number(item.paid) : 0), 0);
  const saved = (items ?? []).reduce((sum, item) => sum + (item.kind === "hold" && item.saved ? Number(item.saved) : 0), 0);
  const visible = (items ?? []).filter(item => matchesQuery(`${item.title} ${item.paypal.order} ${LABEL[item.status] ?? item.status}`, query) && (filter === "all" || (filter === "paid" ? item.status === "CAPTURED" : filter === "held" ? item.status === "AUTHORIZED" : ["VOIDED", "VOID_PENDING", "REFUNDED"].includes(item.status))));
  return <main id="main-content">
    <PageIntro title="Receipts." description="Every PayPal hold, charge and release for your account, with the ids to check them against PayPal."><Link className="button" href="/blocs">Browse Blocs <ArrowUpRight size={15} /></Link></PageIntro>
    {config && !config.enabled && <div className="empty-state"><ReceiptIcon size={28} /><h2>Payments are off.</h2><p>This server runs the no-money demo, so there is nothing to show. Turn on PAYPAL_MODE=simulator to try holds, charges and payouts.</p></div>}
    {error && <ErrorNotice message={error} retry={() => void load()} />}
    {config?.enabled && !items && !error && <div className="loading-surface"><Working label="Loading your receipts" /></div>}
    {items && items.length === 0 && <div className="empty-state"><ReceiptIcon size={28} /><h2>No payments yet.</h2><p>Join a Bloc to place a hold, or let the checkout agent buy something from a scan.</p><Link className="button primary" href="/blocs">Browse Blocs</Link></div>}
    {items && items.length > 0 && <div className="receipt-totals"><div><span>Paid</span><strong>{usd(paid)}</strong></div><div><span>Saved vs your maximums</span><strong>{usd(saved)}</strong></div><Badge tone={config?.simulated ? "warn" : "accent"}>{config?.simulated ? "Simulated PayPal" : "PayPal sandbox"}</Badge></div>}
    {items && items.length > 0 && <><FilterToolbar query={query} onQuery={setQuery} filter={filter} onFilter={setFilter} options={[{value:"all",label:"All receipts"},{value:"paid",label:"Paid"},{value:"held",label:"On hold"},{value:"released",label:"Released / refunded"}]} count={visible.length} label="Search receipts" placeholder="Product or payment ID…" />{visible.length === 0 && <div className="empty-state"><h2>No matching receipts</h2><p>Try another payment ID or reset the filters.</p></div>}</>}
    <section className="receipt-list" aria-label="Receipts">{visible.map(item => <article key={item.id} className="receipt-card">
      <header><div className="receipt-kind">{item.method === "pyusd" ? <Bitcoin size={16} aria-hidden="true" /> : <CreditCard size={16} aria-hidden="true" />}<strong>{item.title || (item.kind === "hold" ? "Group buy hold" : "Checkout")}</strong></div><Badge tone={TONE[item.status as keyof typeof TONE] ?? "neutral"}>{LABEL[item.status] ?? item.status}</Badge></header>
      <div className="receipt-amounts"><div><span>{item.kind === "hold" ? "Held" : "Total"}</span><strong>{usd(item.held)}</strong></div><div><span>Paid</span><strong>{item.paid === null ? "—" : usd(item.paid)}</strong></div>{item.saved && Number(item.saved) > 0 && <div><span>Saved</span><strong>{usd(item.saved)}</strong></div>}</div>
      <dl className="receipt-ids"><div><dt>{item.method === "pyusd" ? "Order" : "PayPal order"}</dt><dd title={item.paypal.order}>{shortId(item.paypal.order)}</dd></div>{item.paypal.authorization && <div><dt>Authorization</dt><dd title={item.paypal.authorization}>{shortId(item.paypal.authorization)}</dd></div>}{item.paypal.capture && <div><dt>Capture</dt><dd title={item.paypal.capture}>{shortId(item.paypal.capture)}</dd></div>}{item.paypal.pyusd_tx && <div><dt>PYUSD transaction</dt><dd title={item.paypal.pyusd_tx}>{shortId(item.paypal.pyusd_tx)}</dd></div>}</dl>
      <footer><span>{relativeTime(item.at)}{item.simulated ? " · simulated" : ""}</span>{item.bloc_id && <Link href={`/blocs/${item.bloc_id}/room`}>Open Bloc <ArrowUpRight size={12} /></Link>}</footer>
    </article>)}</section>
    <AppFooter />
  </main>;
}
