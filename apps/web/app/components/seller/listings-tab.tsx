"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, Barcode, PackagePlus, Pause, Play } from "lucide-react";
import { request } from "../../lib/client";
import { useAction } from "../../lib/use-action";
import { usd } from "../../blocs/types";
import { Badge } from "../ui";
import { Field, FormMessage, SubmitButton } from "../auth-ui";
import AgentFields, { type AgentChoice } from "./agent-fields";
import type { Listing, Overview } from "./types";

const EMPTY = { title: "", gtin: "", category: "audio", typical_price: "", stock: "10", floor: "", opening_price: "" };

/** Products a seller publishes before any buyer has asked for them. Each opens a Bloc. */
export default function ListingsTab({ overview, listings, reload }: { overview: Overview; listings: Listing[]; reload: () => Promise<void> }) {
  const [form, setForm] = useState(EMPTY);
  const [agent, setAgent] = useState<AgentChoice>({ strategy: "balanced", agent: "ai", guidance: "" });
  const action = useAction();
  const set = (key: keyof typeof EMPTY, value: string) => setForm(current => ({ ...current, [key]: value }));
  const typical = Number(form.typical_price) || 0;
  const net = Number(form.floor || 0) * (1 - Number(overview.fee_percent) / 100);
  const live = listings.filter(row => row.active).length;
  return <div className="seller-orders">
    <section className="seller-card" aria-labelledby="new-listing-h">
      <h3 id="new-listing-h"><PackagePlus size={17} aria-hidden="true" /> List a product</h3>
      <p className="muted small">Publish a new product before anyone has asked for it. It opens a Bloc that buyers can join; when it closes, your agent negotiates with them. Only new, genuine goods you are allowed to sell. {live} of {overview.listing_limit} live listings used.</p>
      {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
      <form onSubmit={event => { event.preventDefault(); void action.run(async () => { await request("/api/seller/listings", { body: { ...form, stock: Number(form.stock), gtin: form.gtin.trim(), ...agent } }); setForm(EMPTY); await reload(); return "Listed. Your Bloc is open for buyers."; }); }}>
        <Field label="Exact product: brand, model and variant" value={form.title} onChange={event => set("title", event.target.value)} minLength={8} maxLength={160} required hint="Buyers join for exactly this item, so include colour or size." />
        <Field label="Barcode number (GTIN, UPC or EAN), if it has one" inputMode="numeric" value={form.gtin} onChange={event => set("gtin", event.target.value)} maxLength={20} hint="Checked with GS1's check digit. Listings with the same barcode share one Bloc." />
        <label className="select-field">Category<select value={form.category} onChange={event => set("category", event.target.value)}>{Object.entries(overview.categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <div className="offer-fields">
          <Field label="Typical retail price" inputMode="decimal" value={form.typical_price} onChange={event => set("typical_price", event.target.value)} required hint="Buyers set a maximum between half of this and this." />
          <Field label="Units you can supply" inputMode="numeric" value={form.stock} onChange={event => set("stock", event.target.value)} required />
          <Field label="Floor price (never below)" inputMode="decimal" value={form.floor} onChange={event => set("floor", event.target.value)} required />
          <Field label="Opening price" inputMode="decimal" value={form.opening_price} onChange={event => set("opening_price", event.target.value)} required />
        </div>
        <AgentFields overview={overview} value={agent} onChange={setAgent} />
        {typical > 0 && Number(form.floor) > 0 && <p className="small muted">At your floor you keep about {usd(net)} per unit after Maxx’s {overview.fee_percent}% fee.</p>}
        <details className="prohibited"><summary>What you may not list</summary><ul>{overview.prohibited.map(item => <li key={item}>{item}</li>)}</ul></details>
        <SubmitButton busy={action.busy}>Publish listing</SubmitButton>
      </form>
    </section>
    <section className="seller-card" aria-labelledby="my-listings-h">
      <h3 id="my-listings-h">Your listings</h3>
      {listings.length === 0 ? <p className="muted">None yet.</p> : <ul className="offer-list">{listings.map(row => <li key={row.id}>
        <div><strong>{row.title}</strong><small>{row.gtin && <><Barcode size={12} aria-hidden="true" /> {row.gtin} · </>}{overview.categories[row.category] ?? row.category} · {row.stock} units · floor {usd(row.floor)} · {row.agent === "ai" ? "AI agent" : "fixed rules"}</small><small>{row.bloc_id ? `${row.buyers} buyer${row.buyers === 1 ? "" : "s"} so far` : "No open Bloc right now; a new one opens with the next buyer."}</small></div>
        <Badge tone={row.active ? "good" : "neutral"}>{row.active ? "Live" : "Paused"}</Badge>
        {row.bloc_id && <Link className="icon-button" href={`/blocs/${row.bloc_id}/room`} aria-label={`Open the Bloc for ${row.title}`}><ArrowUpRight size={15} /></Link>}
        <button type="button" className="icon-button" aria-label={row.active ? "Pause listing" : "Resume listing"} onClick={() => void request(`/api/seller/offers/${row.id}/active`, { body: { active: !row.active } }).then(reload)}>{row.active ? <Pause size={15} /> : <Play size={15} />}</button>
      </li>)}</ul>}
    </section>
  </div>;
}
