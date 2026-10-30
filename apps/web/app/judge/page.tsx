"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, Check, Cpu, FlaskConical, KeyRound, RefreshCw, ShieldCheck, UserMinus } from "lucide-react";
import { api } from "../blocs/types";
import { useAuth } from "../components/auth";
import { loginPath, type AccountUser } from "../lib/auth-helpers";
import { request } from "../lib/client";
import { moneyLabel, useMoneyConfig } from "../lib/money";
import { useQuery } from "../lib/use-query";
import { AppFooter, Badge, ErrorNotice, PageIntro, Working } from "../components/ui";
import SellerTour from "../components/seller-tour";
import { useServerReady } from "../components/server-wake";
const scenarios = [
  { id: "success", title: "Find common ground.", label: "Successful deal", description: "Watch seller offers compete, then see the group receive allocations within each buyer’s limit.", icon: Check },
  { id: "failure", title: "Know when to walk.", label: "No deal", description: "When offers cannot meet the group’s limits, Maxx ends the negotiation and releases commitments.", icon: ShieldCheck },
  { id: "flaky", title: "Adapt in real time.", label: "Seller withdrawal", description: "A seller leaves the table. Follow how the negotiation adjusts to the remaining offers and capacity.", icon: UserMinus },
];
type Modes = { scan: string; negotiation: string; matching: string };
type Models = { vision: string; negotiator: string; seller: string; embed: string };

/** Signs a judge in with the access code from the judging notes: a fresh account, no email step. */
function JudgeEntry({ onEntered }: { onEntered: (user: AccountUser) => void }) {
  const query = useQuery();
  const ready = useServerReady();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  useEffect(() => { const given = query?.get("code"); if (given) setCode(given); }, [query]);
  async function enter() {
    setBusy(true); setError("");
    try { const { user } = await request<{ user: AccountUser }>("/api/auth/judge", { body: { code } }); onEntered(user); }
    catch (e) { setError(e instanceof Error ? e.message : "Cannot enter. Try again."); }
    finally { setBusy(false); }
  }
  return <form className="notice-strip judge-entry" onSubmit={event => { event.preventDefault(); void enter(); }}>
    <KeyRound size={19} aria-hidden="true" />
    <div><p><strong>Judging?</strong> Enter with the access code from the judging notes. You get your own guest account at once: no email, no password.</p>
      <div className="inline-actions"><input aria-label="Judge access code" placeholder="Access code" value={code} onChange={event => setCode(event.target.value)} autoComplete="off" /><button className="primary" disabled={busy || !code.trim() || !ready}>{ready ? "Enter as a judge" : "Waking server…"}</button></div>
      {error && <p className="small warn" role="alert">{error}</p>}
      <p className="small muted">Not judging? <Link href={loginPath("/judge")}>Sign in</Link> or <Link href="/signup?next=/judge">create an account</Link>.</p></div>
  </form>;
}

export default function Judge() {
  const { user, status, setUser } = useAuth();
  const money = useMoneyConfig();
  const paying = !!money?.enabled;
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const [resetDone, setResetDone] = useState(false);
  const [entry, setEntry] = useState(false);
  const [modes, setModes] = useState<{ modes: Modes; configured_models: Models } | null>(null);
  const ready = useServerReady();
  useEffect(() => {
    if (!ready) return;
    void request<{ available: boolean }>("/api/auth/judge").then(r => setEntry(r.available)).catch(() => setEntry(false));
    void request<{ modes: Modes; configured_models: Models }>("/api/transparency").then(setModes).catch(() => setModes(null));
  }, [ready]);
  async function enter(scenario:string){setBusy(true);setError("");setResetDone(false);try{const { bloc_id } = await api<{ bloc_id: string }>(`/api/demo/lab/${scenario}`,{});if(!paying)await api(`/api/blocs/${bloc_id}/join`,{max_price:"150.00"});window.location.assign(`/blocs/${bloc_id}/room`);}catch(e){setError(e instanceof Error?e.message:"Cannot open this scenario. Try again.");setBusy(false);}}
  async function reset(){setBusy(true);setError("");setResetDone(false);try{await api("/api/demo/reset",{});setResetDone(true);}catch(e){setError(e instanceof Error?e.message:"Cannot reset.");}finally{setBusy(false);}}
  const live = modes?.modes.negotiation === "live";
  return <main id="main-content"><PageIntro title="Meet Maxx in action." description="Three ways a negotiation can unfold. Each opens your own private copy: a simulated crowd of buyers, eight simulated sellers, and you at the table."><Badge><FlaskConical size={13} /> Demo lab</Badge></PageIntro>
    {/* While the API wakes the code form shows anyway, so the judge can type during the wait. */}
    {!user && (ready ? status === "ready" && entry : true) && <JudgeEntry onEntered={setUser} />}
    {modes && <div className="notice-strip"><Cpu size={19} aria-hidden="true" /><p>{live ? <>Negotiations here call <strong>{modes.configured_models.negotiator}</strong> (negotiator) and <strong>{modes.configured_models.seller}</strong> (seller agents) on Nebius Token Factory. If today’s AI budget runs out, the room says so and runs the deterministic replay instead.</> : <>Negotiations here are a deterministic replay with no model calls. The live setup calls Nemotron on Nebius Token Factory.</>} Scans {modes.modes.scan === "live" ? <>read your own screenshot with <strong>{modes.configured_models.vision}</strong> and check prices with Tavily.</> : "replay the sample screenshots, with no live calls."} <Link href="/under-the-hood">Every call, model and cost</Link></p></div>}
    <div className="notice-strip"><ShieldCheck size={19} /><p>{user ? <>You enter as <strong>{user.display_name}</strong> {paying ? <> and place a PayPal hold from the room ({moneyLabel(money)}).</> : <> with a $150 simulated maximum.</>}</> : <>Sign in to enter a scenario.</>} {!paying ? "No real money." : user ? "" : `${moneyLabel(money)}.`} The other buyers are simulated and place no holds; replay outcomes are deterministic, live models may choose different offers.</p></div>
    {error&&<ErrorNotice message={error} />}
    <section className="bloc-grid" aria-label="Demo scenarios">{scenarios.map(s=><article key={s.id} className="bloc-card scenario-card"><div className="card-top"><div className="scenario-icon"><s.icon size={24} /></div><Badge>{s.label}</Badge></div><h2>{s.title}</h2><p>{s.description}</p>{!ready?<button className="primary" disabled>Waking server…</button>:status==="ready"&&!user?(entry?<button className="primary" disabled>Enter above to try this</button>:<Link className="button primary" href={loginPath("/judge")}>Sign in to try this <ArrowUpRight size={15} /></Link>):<button className="primary" disabled={busy||status==="loading"} onClick={()=>void enter(s.id)}>Try {s.label.toLowerCase()} <ArrowUpRight size={15} /></button>}</article>)}</section>
    {busy&&<Working label="Preparing your demo" />}{resetDone&&<p className="reset-success" role="status">Shared demo Blocs restored.</p>}
    {user?.is_admin && <div className="demo-controls"><button disabled={busy} onClick={()=>void reset()}><RefreshCw size={14} /> Reset shared demo Blocs</button><p>Restores the three listed demo Blocs: 600 simulated buyers in the successful deal, 100 in each of the others, eight simulated sellers each. Judges’ private copies and custom Blocs stay in place. Active negotiations must finish first.</p></div>}
    <SellerTour />
    <Link className="button secondary" href="/scan">Start with your own screenshot <ArrowUpRight size={15} /></Link><AppFooter /></main>;
}
