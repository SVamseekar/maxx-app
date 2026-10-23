"use client";
import FilterToolbar from "../components/filter-toolbar";
import { matchesQuery } from "../lib/collection";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Package } from "lucide-react";
import { ErrorNotice, PageIntro, Working } from "../components/ui";
import { useAuth } from "../components/auth";
import OrderCard from "../components/order-card";
import { request } from "../lib/client";
import { loginPath } from "../lib/auth-helpers";
import type { AddressSummary, OrderView } from "../lib/orders";

export default function Orders() {
  const { user, status } = useAuth();
  const router = useRouter();
  const [orders, setOrders] = useState<OrderView[] | null>(null);
  const [addresses, setAddresses] = useState<AddressSummary[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  useEffect(() => { if (status === "ready" && !user) router.replace(loginPath("/orders")); }, [status, user, router]);
  const load = useCallback(async () => {
    try { const [o, a] = await Promise.all([request<OrderView[]>("/api/orders"), request<AddressSummary[]>("/api/addresses")]); setOrders(o); setAddresses(a); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Cannot load your orders."); }
  }, []);
  useEffect(() => { if (user) void load(); }, [user?.id, load]); // eslint-disable-line react-hooks/exhaustive-deps
  const needs = orders?.filter(o => o.status === "AWAITING_ADDRESS").length ?? 0;
  const visible = (orders ?? []).filter(o => matchesQuery(`${o.title} ${o.seller.name}`, query) && (filter === "all" || (filter === "action" ? o.status === "AWAITING_ADDRESS" : filter === "progress" ? ["AWAITING_SHIPMENT", "SHIPPED"].includes(o.status) : ["DELIVERED", "CANCELLED", "REFUNDED"].includes(o.status))));
  return <main id="main-content" className="orders-page">
    <PageIntro title="Your orders." description="What you won, where it is, and what to do if something is wrong. The seller ships and supports each order; Maxx holds your money until they do."><Link className="button" href="/receipts">Payments and receipts <ArrowUpRight size={15} aria-hidden="true" /></Link></PageIntro>
    {error && <ErrorNotice message={error} retry={() => void load()} />}
    {!orders && !error && <div className="loading-surface"><Working label="Loading your orders" /></div>}
    {needs > 0 && <p className="notice-strip" role="status">{needs === 1 ? "One order needs" : `${needs} orders need`} a delivery address before the seller can ship.</p>}
    {orders && orders.length === 0 && <div className="empty-state"><Package size={28} aria-hidden="true" /><h2>No orders yet.</h2><p>When you win a Bloc from a seller on Maxx, the order appears here, ready for your delivery address.</p><Link className="button primary" href="/blocs">Browse Blocs</Link></div>}
    {orders && orders.length > 0 && <><FilterToolbar query={query} onQuery={setQuery} filter={filter} onFilter={setFilter} options={[{value:"all",label:"All orders"},{value:"action",label:"Needs you"},{value:"progress",label:"On the way"},{value:"complete",label:"Completed"}]} count={visible.length} label="Search orders" placeholder="Product or seller…" />{visible.length === 0 && <div className="empty-state"><h2>No matching orders</h2><p>Try another search or reset your filters.</p></div>}</>}
    <section className="order-list" aria-label="Orders">{visible.map(order => <OrderCard key={order.id} order={order} addresses={addresses} onChange={load} onAddress={address => setAddresses(current => [address, ...current])} />)}</section>
  </main>;
}
