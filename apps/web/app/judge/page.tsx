"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, Check, FlaskConical, RefreshCw, ShieldCheck, UserMinus } from "lucide-react";
import { api } from "../blocs/types";
import { useAuth } from "../components/auth";
import { loginPath } from "../lib/auth-helpers";
import { moneyLabel, useMoneyConfig } from "../lib/money";
import { AppFooter, Badge, ErrorNotice, PageIntro, Working } from "../components/ui";
import SellerTour from "../components/seller-tour";
const scenarios = [
  { id: "success", title: "Find common ground.", label: "Successful deal", description: "Watch seller offers compete, then see the group receive allocations within each buyer’s limit.", icon: Check },
  { id: "failure", title: "Know when to walk.", label: "No deal", description: "When offers cannot meet the group’s limits, Maxx ends the negotiation and releases commitments.", icon: ShieldCheck },
  { id: "flaky", title: "Adapt in real time.", label: "Seller withdrawal", description: "A seller leaves the table. Follow how the negotiation adjusts to the remaining offers and capacity.", icon: UserMinus },
];
export default function Judge() {
  const { user, status } = useAuth();
  const money = useMoneyConfig();
  const paying = !!money?.enabled;
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const [resetDone, setResetDone] = useState(false);
  async function enter(scenario:string){setBusy(true);setError("");setResetDone(false);try{if(!paying)await api(`/api/blocs/demo-${scenario}/join`,{max_price:"150.00"});window.location.assign(`/blocs/demo-${scenario}/room`);}catch(e){setError(e instanceof Error?e.message:"Cannot enter. Reset finished scenarios first.");setBusy(false);}}
  async function reset(){setBusy(true);setError("");setResetDone(false);try{await api("/api/demo/reset",{});setResetDone(true);}catch(e){setError(e instanceof Error?e.message:"Cannot reset.");}finally{setBusy(false);}}
  return <main id="main-content"><PageIntro title="Meet Maxx in action." description="Three ways a negotiation can unfold. Step into a buying group, take a seat at the table, and follow every move."><Badge><FlaskConical size={13} /> Demo lab</Badge></PageIntro>
    <div className="notice-strip"><ShieldCheck size={19} /><p>{user ? <>You enter as <strong>{user.display_name}</strong> {paying ? <> and place a PayPal hold from the room ({moneyLabel(money)}).</> : <> with a $150 simulated maximum.</>}</> : <>Sign in to enter a scenario.</>} {paying ? "" : "No real money."} Fixture outcomes are deterministic; live models may choose different offers.</p></div>
    {error&&<ErrorNotice message={error} />}
    <section className="bloc-grid" aria-label="Demo scenarios">{scenarios.map(s=><article key={s.id} className="bloc-card scenario-card"><div className="card-top"><div className="scenario-icon"><s.icon size={24} /></div><Badge>{s.label}</Badge></div><h2>{s.title}</h2><p>{s.description}</p>{status==="ready"&&!user?<Link className="button primary" href={loginPath("/judge")}>Sign in to try this <ArrowUpRight size={15} /></Link>:<button className="primary" disabled={busy||status==="loading"} onClick={()=>void enter(s.id)}>Try {s.label.toLowerCase()} <ArrowUpRight size={15} /></button>}</article>)}</section>
    {busy&&<Working label="Preparing your demo" />}{resetDone&&<p className="reset-success" role="status">Scenarios restored. Choose a scenario to begin.</p>}
    <div className="demo-controls"><button disabled={busy||!user} onClick={()=>void reset()} title={user?undefined:"Sign in to reset the demo"}><RefreshCw size={14} /> Reset demo scenarios</button><p>Restores 800 seeded buyers and eight sellers per scenario. Your custom Blocs stay in place. Active negotiations must finish before reset.</p></div>
    <SellerTour />
    <Link className="button secondary" href="/scan">Start with your own screenshot <ArrowUpRight size={15} /></Link><AppFooter /></main>;
}
