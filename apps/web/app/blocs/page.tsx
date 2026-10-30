"use client";
import Link from "next/link";
import FilterToolbar from "../components/filter-toolbar";
import ProductIdentity from "../components/product-identity";
import { matchesQuery } from "../lib/collection";
import { AnimatePresence, motion } from "motion/react";
import { useMotionPreferences } from "../components/motion-system";
import { useCallback, useEffect, useState } from "react";
import { api, usd, type Bloc, type BlocSummary } from "./types";
import { ArrowUpRight, Plus, Search, Users } from "lucide-react";
import { AppFooter, Badge, ErrorNotice, PageIntro, SellerWhy, Working } from "../components/ui";
import { useServerReady } from "../components/server-wake";
import { useAuth } from "../components/auth";
import { loginPath } from "../lib/auth-helpers";
import { statusLabel } from "../presentation";
import { canCreateMatch } from "./matching";

export default function Blocs() {
  const { reduced } = useMotionPreferences();
  const { user, status: authStatus } = useAuth();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [loaded, setLoaded] = useState(false);
  const [blocs, setBlocs] = useState<BlocSummary[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [price, setPrice] = useState("");
  const [match, setMatch] = useState<{mode:string;confidence:number;requires_confirmation:boolean;candidates:{product_key:string;title:string;confidence:number;reason:string}[]} | null>(null);
  const [key,setKey] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const load = useCallback(async () => { setError(""); setBusy(true); try { setBlocs(await api<BlocSummary[]>("/api/blocs")); } catch (e) { setError(e instanceof Error ? e.message : "Cannot load Blocs."); } finally { setBusy(false); setLoaded(true); } }, []);
  const ready = useServerReady();
  useEffect(() => { const params = new URLSearchParams(window.location.search); setTitle(params.get("title") ?? ""); setPrice(params.get("price") ?? ""); }, []);
  useEffect(() => { if (ready) void load(); }, [load, ready]);
  async function findMatch() {
    setBusy(true); setError(""); setConfirmed(false); setKey("");
    try { const result = await api<NonNullable<typeof match>>("/api/catalog/match", {title}); setMatch(result); if (!result.requires_confirmation) setKey(result.candidates[0]?.product_key ?? ""); }
    catch(e) { setError(e instanceof Error ? e.message : "Matching failed."); }
    finally { setBusy(false); }
  }
  async function create() {
    setBusy(true); setError("");
    try { const bloc = await api<Bloc>("/api/blocs", { title, typical_price: price, confirmed_variant: confirmed, ...(key ? {product_key:key,item:{title}} : {}) }); window.location.assign(`/blocs/${bloc.id}/room`); }
    catch (e) { setError(e instanceof Error ? e.message : "Cannot create Bloc."); setBusy(false); }
  }
  async function reset() {
    setBusy(true); setError("");
    try { await api("/api/demo/reset", {}); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Cannot reset demo."); setBusy(false); }
  }
  const options = [{ value: "all", label: "All Blocs" }, { value: "open", label: "Open to join" }, { value: "negotiating", label: "Negotiating" }, { value: "completed", label: "Completed" }];
  const visible = blocs.filter(b => matchesQuery(b.title, search) && (filter === "all" || (filter === "open" ? b.status === "OPEN" : filter === "negotiating" ? b.status === "NEGOTIATING" : ["SETTLED", "FAILED"].includes(b.status))));
  return <main id="main-content">
    <PageIntro title="Find your buying group" description="Bring your demand together. Set your own limit. Let Maxx negotiate with seller agents on behalf of the group."><a className="button primary" href="#create-bloc"><Plus size={16} /> Create a Bloc</a></PageIntro>
    <FilterToolbar query={search} onQuery={setSearch} filter={filter} onFilter={setFilter} options={options} count={visible.length} label="Search Blocs" placeholder="Find a product or model…" />
    {error && <ErrorNotice message={error} retry={() => void load()} />}
    {!loaded && <div className="loading-surface"><Working label="Finding your Blocs" /></div>}
    <section className="bloc-grid" aria-label="Available Blocs"><AnimatePresence initial={false}>{visible.map(b => <motion.div layout={!reduced} key={b.id} initial={{ opacity: 0, scale: reduced ? 1 : .97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: reduced ? 1 : .97 }} transition={{ duration: reduced ? 0 : .22 }}><Link className="bloc-card" href={`/blocs/${b.id}/room`}><div className="card-top"><ProductIdentity title={b.title} /><Badge tone={b.status === "OPEN" ? "good" : b.status === "FAILED" ? "warn" : "accent"}>{statusLabel(b.status)}</Badge></div><h2>{b.title}</h2><p className="scenario-label">{b.id.startsWith("demo-") ? ({ success: "Successful deal scenario", failure: "No-deal scenario", flaky: "Seller withdrawal scenario" }[b.scenario]) : "Your confirmed product"}</p><div className="card-price"><div><span>Reference target</span><strong>{usd(b.target_price)}</strong></div><div><span>Typical price</span><strong>{usd(b.typical_price)}</strong></div></div><div className="card-members"><Users size={15} /><span>{b.buyers} {b.id.startsWith("demo-") ? "simulated buyers" : "buyers together"}</span></div><p>{b.id.startsWith("demo-") ? "Simulated crowd · no money held" : `${usd(b.committed_total)} in commitments`}</p><Badge tone={b.mode === "fixture" ? "warn" : "neutral"}>{b.mode === "fixture" ? "Replayed offers" : "Live Nemotron agents"}</Badge><div className="card-link">Open negotiation room <ArrowUpRight size={17} /></div></Link></motion.div>)}</AnimatePresence></section>
    {loaded && !error && visible.length === 0 && <div className="empty-state"><Search size={28} /><h2>{blocs.length ? "No matching Blocs" : "Start something together."}</h2><p>{blocs.length ? "Try another product name or select all Blocs." : "Create a Bloc for your exact product, or load the demo scenarios below."}</p>{blocs.length > 0 && <button onClick={() => { setSearch(""); setFilter("all"); }}>Clear filters</button>}</div>}
    <div className="create-layout" id="create-bloc"><div><h2>Your next purchase.<br />With people on your side.</h2><p>A Bloc brings buyers of the exact same product together. Confirm your model and variant, then choose the most you would pay.</p><SellerWhy compact /><p className="small muted">Sellers, stock and commitments are simulated. A reference target is not a guaranteed deal.</p></div>
    <section className="create-bloc" aria-label="Create a Bloc">{authStatus === "ready" && !user ? <div className="join-gate"><h3>Sign in to create a Bloc.</h3><p>Bloc creators can close their group and start the negotiation. Browsing is open to everyone; creating and joining need a free account.</p><Link className="button primary" href={loginPath("/blocs#create-bloc")}>Sign in</Link><Link className="button" href="/signup?next=%2Fblocs%23create-bloc">Create an account</Link></div> : <form onSubmit={e => { e.preventDefault(); void create(); }}><label>Exact product and variant<input value={title} onChange={e => { setTitle(e.target.value); setConfirmed(false); setMatch(null); setKey(""); }} placeholder="e.g. Aurora Q5 wireless headphones, Black" required minLength={3} maxLength={300}/></label><label>Typical unit price in USD<input type="number" min="0.01" step="0.01" required value={price} onChange={e => setPrice(e.target.value)}/></label><button type="button" disabled={busy || title.trim().length<3} onClick={()=>void findMatch()}>Find matching product</button>{match && <section aria-label="Product match"><p>{match.mode === "fixture" ? "Fixture catalogue rules · no embedding call" : "Live Nebius embedding + variant rules"} · Confidence {(match.confidence*100).toFixed(0)}% · {match.requires_confirmation ? "Confirmation required" : "Exact product matched"}</p>{match.candidates.map(c=><label key={c.product_key}><input type="radio" name="product" checked={key===c.product_key} onChange={()=>{setKey(c.product_key);setConfirmed(false);}}/>{c.title} · {(c.confidence*100).toFixed(0)}% · {c.reason}</label>)}<label><input type="radio" name="product" checked={!key} onChange={()=>{setKey("");setConfirmed(false);}}/>Create a separate custom product</label></section>}<label className="checkbox"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>I confirm this exact product and variant</label><button className="primary" disabled={busy || !canCreateMatch(match,key,confirmed)}>Create my Bloc</button></form>}</section></div>
    <div className="demo-controls"><button onClick={() => void reset()} disabled={busy || !user} title={user ? undefined : "Sign in to reset the demo"}>Reset seeded demo Blocs</button><p>Reset restores the 800 seeded buyers across three scenarios and preserves your custom Blocs. Active negotiations must finish first.</p></div><AppFooter />
  </main>;
}
