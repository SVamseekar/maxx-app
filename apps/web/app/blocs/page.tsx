"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, usd, type Bloc } from "./types";
import { canCreateMatch } from "./matching";

export default function Blocs() {
  const [blocs, setBlocs] = useState<Bloc[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [price, setPrice] = useState("");
  const [match, setMatch] = useState<{mode:string;confidence:number;requires_confirmation:boolean;candidates:{product_key:string;title:string;confidence:number;reason:string}[]} | null>(null);
  const [key,setKey] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const load = useCallback(async () => { setError(""); setBusy(true); try { setBlocs(await api<Bloc[]>("/api/blocs")); } catch (e) { setError(e instanceof Error ? e.message : "Cannot load Blocs."); } finally { setBusy(false); } }, []);
  useEffect(() => { const params = new URLSearchParams(window.location.search); setTitle(params.get("title") ?? ""); setPrice(params.get("price") ?? ""); void load(); }, [load]);
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
  return <main><header><Link href="/" className="wordmark">maxx<span>✳</span></Link><Link href="/judge">Judge mode</Link><Link href="/under-the-hood">Under the hood</Link><Link href="/">Scan a screenshot</Link></header>
    <section className="bloc-heading"><h1>Buying together.<br/>Negotiating smarter.</h1><p>Demo commitments only. No money moves. Sellers and stock are simulated in both modes.</p></section>
    {error && <p className="error" role="alert">{error} <button onClick={() => void load()}>Retry</button></p>}
    <section className="bloc-grid" aria-label="Available Blocs">{blocs.map(b => <Link key={b.id} className="bloc-card" href={`/blocs/${b.id}/room`}><div className={`mode ${b.mode}`}>{b.mode === "fixture" ? "Fixture agents · simulated offers" : "Live Nebius models · simulated sellers"}</div><h2>{b.title}</h2><p>{b.id.startsWith("demo-") ? ({ success: "Successful deal scenario", failure: "No-deal scenario", flaky: "Seller withdrawal scenario" }[b.scenario]) : "Your confirmed product"}</p><p>{b.members.filter(m => m.status !== "LEFT").length} buyers · {b.status}</p><p>Typical {usd(b.typical_price)} · Target {usd(b.target_price)} · Committed {usd(b.committed_total)}</p><strong>Open negotiation room ↗</strong></Link>)}</section>
    <section className="create-bloc"><h2>Bring your screenshot into a Bloc.</h2><p>Confirm the exact model and variant. Match against the 50-identity demo catalogue. Uncertain matches require your confirmation; different variants stay separate. The reference target is the median of trusted delivered prices; it is not a guaranteed deal.</p><form onSubmit={e => { e.preventDefault(); void create(); }}><label>Exact product and variant<input value={title} onChange={e => { setTitle(e.target.value); setConfirmed(false); setMatch(null); setKey(""); }} required minLength={3} maxLength={300}/></label><label>Typical unit price in USD<input type="number" min="0.01" step="0.01" required value={price} onChange={e => setPrice(e.target.value)}/></label><button type="button" disabled={busy || title.trim().length<3} onClick={()=>void findMatch()}>Find matching product</button>{match && <section aria-label="Product match"><p>{match.mode === "fixture" ? "Fixture catalogue rules · no embedding call" : "Live Nebius embedding + variant rules"} · Confidence {(match.confidence*100).toFixed(0)}% · {match.requires_confirmation ? "Confirmation required" : "Exact product matched"}</p>{match.candidates.map(c=><label key={c.product_key}><input type="radio" name="product" checked={key===c.product_key} onChange={()=>{setKey(c.product_key);setConfirmed(false);}}/>{c.title} · {(c.confidence*100).toFixed(0)}% · {c.reason}</label>)}<label><input type="radio" name="product" checked={!key} onChange={()=>{setKey("");setConfirmed(false);}}/>Create a separate custom product</label></section>}<label className="checkbox"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>I confirm this exact product and variant</label><button className="primary" disabled={busy || !canCreateMatch(match,key,confirmed)}>Create my Bloc</button></form></section>
    <footer><button onClick={() => void reset()} disabled={busy}>Reset seeded demo Blocs</button><p>Reset restores the 800 seeded buyers across three scenarios and preserves your custom Blocs. Active negotiations must finish first.</p></footer>
  </main>;
}
