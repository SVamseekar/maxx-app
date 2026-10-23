"use client";
import { useConfirm } from "../confirm-provider";
import FilterToolbar from "../filter-toolbar";
import { matchesQuery } from "../../lib/collection";
import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { request } from "../../lib/client";
import { useAction } from "../../lib/use-action";
import { CASE_KINDS, deadlineText } from "../../lib/orders";
import { usd } from "../../blocs/types";
import { Badge } from "../ui";
import { FormMessage } from "../auth-ui";
import type { SellerCase } from "./types";

function CaseCard({ item, reload }: { item: SellerCase; reload: () => Promise<void> }) {
  const confirmAction = useConfirm();
  const [text, setText] = useState("");
  const action = useAction();
  const open = item.status === "OPEN";
  const answered = item.messages.some(m => m.actor === "seller");
  return <article className="seller-order">
    <header><div><h3>{item.title}</h3><p className="muted small">{usd(item.amount)} · {CASE_KINDS[item.kind] ?? item.kind}</p></div><Badge tone={open ? "warn" : "neutral"}>{open ? "Open" : item.status.replaceAll("_", " ").toLowerCase()}</Badge></header>
    {open && !answered && <p className="order-note" role="status"><strong>Reply {deadlineText(item.respond_by)}.</strong> If you do not, the buyer is refunded in full and you receive a strike.</p>}
    <ol className="case-messages">{item.messages.map((m, i) => <li key={i} className={`from-${m.actor}`}><strong>{m.actor === "buyer" ? "Buyer" : m.actor === "seller" ? "You" : "Maxx"}</strong><p>{m.body}</p></li>)}</ol>
    {item.resolution && !open && <p className="muted small">Outcome: {item.resolution}</p>}
    {open && <>{action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
      <form className="inline-form" onSubmit={event => { event.preventDefault(); void action.run(async () => { await request(`/api/seller/cases/${item.id}/reply`, { body: { body: text } }); setText(""); await reload(); return "Sent."; }); }}>
        <label className="select-field">Your reply<input value={text} onChange={event => setText(event.target.value)} minLength={2} maxLength={2000} required /></label><button className="button primary" disabled={action.busy || text.trim().length < 2}>Send reply</button>
        <button type="button" disabled={action.busy} onClick={async () => { if (await confirmAction("Refund this buyer in full? The amount you were paid is deducted from your future payouts.")) void action.run(async () => { await request(`/api/seller/cases/${item.id}/refund`, { body: {} }); await reload(); return "Refunded."; }); }}>Agree to refund</button></form></>}
  </article>;
}

export default function CasesTab({ cases, reload }: { cases: SellerCase[]; reload: () => Promise<void> }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const visible = cases.filter(c => matchesQuery(`${c.title} ${c.id} ${c.order_id}`, query) && (filter === "all" || (filter === "open" ? c.status === "OPEN" : c.status !== "OPEN")));
  if (cases.length === 0) return <div className="empty-state"><MessageSquare size={26} aria-hidden="true" /><h3>No problems reported.</h3><p>If a buyer reports a problem you will see it here, and you have 24 hours to reply. Replying promptly protects your account.</p></div>;
  return <div className="seller-orders"><FilterToolbar query={query} onQuery={setQuery} filter={filter} onFilter={setFilter} count={visible.length} label="Search reported problems" placeholder="Product or case reference" options={[{value:"all",label:"All problems"},{value:"open",label:"Open"},{value:"closed",label:"Resolved"}]} />{visible.length === 0 && <p className="empty-state">No problems match these filters.</p>}{visible.map(item => <CaseCard key={item.id} item={item} reload={reload} />)}</div>;
}
