"use client";
import FilterToolbar from "../filter-toolbar";
import { matchesQuery } from "../../lib/collection";
import { useState } from "react";
import { MapPin, Package, Truck } from "lucide-react";
import { request } from "../../lib/client";
import { useAction } from "../../lib/use-action";
import { countryName } from "../../lib/countries";
import { deadlineText } from "../../lib/orders";
import { usd } from "../../blocs/types";
import { Badge } from "../ui";
import { Field, FormMessage, SubmitButton } from "../auth-ui";
import { CARRIERS, type SellerOrder } from "./types";

const LABEL: Record<string, string> = { AWAITING_ADDRESS: "Waiting for the buyer’s address", AWAITING_SHIPMENT: "Ready to ship", SHIPPED: "Shipped", DELIVERED: "Delivered", CANCELLED: "Cancelled and refunded", REFUNDED: "Refunded" };
const TONE: Record<string, "warn" | "accent" | "good" | "neutral"> = { AWAITING_ADDRESS: "warn", AWAITING_SHIPMENT: "accent", SHIPPED: "accent", DELIVERED: "good", CANCELLED: "neutral", REFUNDED: "neutral" };

function ShipForm({ order, onDone }: { order: SellerOrder; onDone: () => Promise<void> }) {
  const [carrier, setCarrier] = useState(CARRIERS[0]);
  const [tracking, setTracking] = useState("");
  const action = useAction();
  return <form className="ship-form" onSubmit={event => { event.preventDefault(); void action.run(async () => { await request(`/api/seller/orders/${order.id}/ship`, { body: { carrier, tracking } }); await onDone(); return "Marked as shipped. Your payout is on its way."; }); }}>
    {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
    <label className="select-field">Carrier<select value={carrier} onChange={event => setCarrier(event.target.value)}>{CARRIERS.map(name => <option key={name}>{name}</option>)}</select></label>
    <Field label="Tracking number" value={tracking} onChange={event => setTracking(event.target.value)} required minLength={3} maxLength={80} autoComplete="off" hint="Required. You are paid when you mark the order shipped." />
    <SubmitButton busy={action.busy} disabled={tracking.trim().length < 3}>Mark as shipped and get paid</SubmitButton>
  </form>;
}

export default function OrdersTab({ orders, reload }: { orders: SellerOrder[]; reload: () => Promise<void> }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const visible = orders.filter(o => matchesQuery(`${o.title} ${o.id} ${o.tracking}`, query) && (filter === "all" || (filter === "ready" ? o.status === "AWAITING_SHIPMENT" : filter === "transit" ? o.status === "SHIPPED" : ["DELIVERED", "CANCELLED", "REFUNDED"].includes(o.status))));
  if (orders.length === 0) return <div className="empty-state"><Package size={26} aria-hidden="true" /><h3>No orders yet.</h3><p>When a buyer wins a unit from your offer and is charged, the order shows up here. You ship it, and you are paid.</p></div>;
  const todo = orders.filter(o => o.status === "AWAITING_SHIPMENT").length;
  return <div className="seller-orders">
    <p className="muted small">You are responsible for shipping and supporting every order. Use each buyer’s details only to deliver and support that order, and delete them when you no longer need them. {todo > 0 && <strong>{todo} to ship.</strong>}</p>
    <FilterToolbar query={query} onQuery={setQuery} filter={filter} onFilter={setFilter} count={visible.length} label="Search seller orders" placeholder="Product, order or tracking number" options={[{value:"all",label:"All orders"},{value:"ready",label:"To ship",count:todo},{value:"transit",label:"In transit"},{value:"complete",label:"Completed"}]} />
    {visible.length === 0 && <p className="empty-state">No orders match these filters.</p>}
    {visible.map(order => <article key={order.id} className="seller-order">
      <header><div><h3>{order.title}</h3><p className="muted small">{usd(order.amount)} sale · you receive {usd(order.your_share)} after Maxx’s fee</p></div><Badge tone={TONE[order.status] ?? "neutral"}>{LABEL[order.status] ?? order.status}</Badge></header>
      {order.status === "AWAITING_ADDRESS" && <p className="order-note">Waiting for the buyer to give a delivery address. The order is cancelled and refunded if they do not, {deadlineText(order.ship_by)}.</p>}
      {order.status === "AWAITING_SHIPMENT" && <>
        <p className="order-note"><Truck size={15} aria-hidden="true" /> Ship {deadlineText(order.ship_by)}. After that and a 2-day grace period the buyer is refunded and you get a strike.</p>
        {order.address && <address className="ship-to"><MapPin size={14} aria-hidden="true" /><span><strong>{order.address.name}</strong><br />{order.address.line1}{order.address.line2 && <><br />{order.address.line2}</>}<br />{order.address.city}{order.address.region && `, ${order.address.region}`} {order.address.postal}<br />{countryName(order.address.country)}{order.address.phone && <><br />{order.address.phone}</>}</span></address>}
        <ShipForm order={order} onDone={reload} /></>}
      {order.status === "SHIPPED" && <p className="order-note"><Truck size={15} aria-hidden="true" /> Shipped with {order.carrier}. Tracking <code>{order.tracking}</code>.{order.case_id && <strong> The buyer opened a problem. See Problems.</strong>}</p>}
      {(order.status === "CANCELLED" || order.status === "REFUNDED") && <p className="order-note">The buyer was refunded. Nothing to ship. {order.status === "REFUNDED" ? "If you were already paid, the amount is deducted from your next payouts." : ""}</p>}
    </article>)}
  </div>;
}
