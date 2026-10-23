"use client";
import FilterToolbar from "../filter-toolbar";
import { matchesQuery } from "../../lib/collection";
import { useState } from "react";
import { Pause, Play, TrendingDown } from "lucide-react";
import { request } from "../../lib/client";
import { useAction } from "../../lib/use-action";
import { usd } from "../../blocs/types";
import { Badge, Working } from "../ui";
import { Field, FormMessage, SubmitButton } from "../auth-ui";
import AgentFields, { type AgentChoice } from "./agent-fields";
import { STRATEGY_TEXT, type Offer, type Opportunity, type Overview, type Result } from "./types";

function OpportunityCard({ row, overview, onSaved }: { row: Opportunity; overview: Overview; onSaved: () => Promise<void> }) {
  const typical = Number(row.typical_price);
  const mine = row.my_offer;
  const [open, setOpen] = useState(false);
  const [stock, setStock] = useState(String(mine?.stock ?? 100));
  const [floor, setFloor] = useState(mine?.floor ?? (typical * .7).toFixed(2));
  const [opening, setOpening] = useState(mine?.opening_price ?? (typical * .9).toFixed(2));
  const [agent, setAgent] = useState<AgentChoice>({ strategy: mine?.strategy ?? "balanced", agent: mine?.agent ?? "rules", guidance: mine?.guidance ?? "" });
  const action = useAction();
  const top = Math.max(...row.curve.map(point => point.buyers), 1);
  const net = Number(floor) * (1 - Number(overview.fee_percent) / 100);
  return <article className="opportunity">
    <header><strong>{row.title}</strong>{mine && <Badge tone={mine.active ? "good" : "neutral"}>{mine.active ? "Your offer is live" : "Your offer is paused"}</Badge>}</header>
    <p className="small muted">{row.buyers} buyers · median maximum {row.median_max ? usd(row.median_max) : "—"} · typical price {usd(row.typical_price)}</p>
    <div className="curve" role="img" aria-label="Buyers who would pay at least each price">{row.curve.map(point => <div key={point.price}><span style={{ height: `${Math.max(6, (point.buyers / top) * 100)}%` }} /><small>{usd(point.price)}</small><small>{point.buyers}</small></div>)}</div>
    {!open ? <button type="button" className="button" onClick={() => setOpen(true)}><TrendingDown size={15} aria-hidden="true" /> {mine ? "Edit my offer" : "Make an offer"}</button> :
      <form onSubmit={event => { event.preventDefault(); void action.run(async () => { await request("/api/seller/offers", { body: { product_key: row.product_key, stock: Number(stock), floor, opening_price: opening, ...agent } }); await onSaved(); setOpen(false); return "Offer saved."; }); }}>
        <div className="offer-fields"><Field label="Units you can supply" inputMode="numeric" value={stock} onChange={event => setStock(event.target.value)} required /><Field label="Floor price (never below)" inputMode="decimal" value={floor} onChange={event => setFloor(event.target.value)} required /><Field label="Opening price" inputMode="decimal" value={opening} onChange={event => setOpening(event.target.value)} required /></div>
        <AgentFields overview={overview} value={agent} onChange={setAgent} />
        <p className="small muted">At your floor you keep about {usd(net)} per unit after Maxx’s {overview.fee_percent}% fee, and you ship every unit you win.</p>
        {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
        <div className="inline-actions"><SubmitButton busy={action.busy}>Save offer</SubmitButton><button type="button" className="quiet-button" onClick={() => setOpen(false)}>Cancel</button></div>
      </form>}
  </article>;
}

export default function OffersTab({ overview, opportunities, offers, results, reload }: { overview: Overview; opportunities: Opportunity[] | null; offers: Offer[]; results: Result[]; reload: () => Promise<void> }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const visibleOpportunities = opportunities?.filter(row => matchesQuery(row.title, query) && (filter === "all" || (filter === "new" ? !row.my_offer : !!row.my_offer)));
  const [offerQuery, setOfferQuery] = useState("");
  const [offerFilter, setOfferFilter] = useState("all");
  const visibleOffers = offers.filter(row => matchesQuery(row.title, offerQuery) && (offerFilter === "all" || (offerFilter === "active" ? row.active : !row.active)));
  return <div className="seller-orders">
    <section className="seller-card" aria-labelledby="opp-h">
      <div className="section-heading"><h3 id="opp-h">Demand waiting for a seller</h3><Badge>{opportunities?.length ?? 0} products</Badge></div>
      <p className="muted small">Buyers have set a maximum and put the money on hold. Your offer stays on file and joins every future Bloc for the same product. Maxx never shows buyer identities.</p>
      {opportunities && opportunities.length > 0 && <FilterToolbar query={query} onQuery={setQuery} filter={filter} onFilter={setFilter} count={visibleOpportunities?.length ?? 0} label="Search product demand" placeholder="Find a product with demand" options={[{value:"all",label:"All demand"},{value:"new",label:"New opportunities"},{value:"offered",label:"With your offer"}]} />}
      {visibleOpportunities?.length === 0 && opportunities?.length !== 0 && <p className="empty-state">No demand matches these filters.</p>}
      {!opportunities ? <Working label="Finding demand" /> : opportunities.length === 0 ? <p className="muted">No open Bloc has buyers right now. You can also list a product yourself in Listings.</p> : <div className="opportunity-grid">{visibleOpportunities?.map(row => <OpportunityCard key={row.product_key} row={row} overview={overview} onSaved={reload} />)}</div>}
    </section>
    <section className="seller-card" aria-labelledby="offers-h">
      <h3 id="offers-h">Your standing offers</h3>
      {offers.length > 0 && <FilterToolbar query={offerQuery} onQuery={setOfferQuery} filter={offerFilter} onFilter={setOfferFilter} count={visibleOffers.length} label="Search standing offers" placeholder="Find an offer" options={[{value:"all",label:"All offers"},{value:"active",label:"Active"},{value:"paused",label:"Paused"}]} />}
      {offers.length > 0 && visibleOffers.length === 0 && <p className="empty-state">No offers match these filters.</p>}
      {offers.length === 0 ? <p className="muted">None yet. Make one from the demand above.</p> : <ul className="offer-list">{visibleOffers.map(offer => <li key={offer.id}><div><strong>{offer.title}</strong><small>{offer.stock} units · floor {usd(offer.floor)} · opens at {usd(offer.opening_price)} · {offer.agent === "ai" ? "AI agent" : STRATEGY_TEXT[offer.strategy]}{offer.listing && " · your listing"}</small></div><Badge tone={offer.active ? "good" : "neutral"}>{offer.active ? "Active" : "Paused"}</Badge><button type="button" className="icon-button" aria-label={offer.active ? "Pause offer" : "Resume offer"} onClick={() => void request(`/api/seller/offers/${offer.id}/active`, { body: { active: !offer.active } }).then(reload)}>{offer.active ? <Pause size={15} /> : <Play size={15} />}</button></li>)}</ul>}
    </section>
    <section className="seller-card" aria-labelledby="res-h">
      <h3 id="res-h">Results and payouts</h3>
      {results.length === 0 ? <p className="muted">Results appear after a Bloc with your offer finishes negotiating.</p> : <div className="table-wrap"><table><thead><tr><th scope="col">Bloc</th><th scope="col">Units won</th><th scope="col">Real orders</th><th scope="col">Avg price</th><th scope="col">Gross</th><th scope="col">Maxx fee</th><th scope="col">Paid to you</th></tr></thead><tbody>{results.map(row => <tr key={row.bloc_id}><td>{row.title}</td><td>{row.units}</td><td>{row.paid_units}</td><td>{row.average_price ? usd(row.average_price) : "—"}</td><td>{row.payout ? usd(row.payout.gross) : "—"}</td><td>{row.payout ? usd(row.payout.fee) : "—"}</td><td>{row.payout ? usd(row.payout.net) : overview.payments ? "On shipping" : "Payments off"}</td></tr>)}</tbody></table></div>}
      <p className="small muted">Units won include simulated demo buyers, who are not charged. Real orders are the buyers who paid; you are paid for each when you ship it.</p>
    </section>
  </div>;
}
