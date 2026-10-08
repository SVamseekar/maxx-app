"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "../blocs/types";
export default function Judge() {
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  async function enter(scenario:string){setBusy(true);setError("");try{await api(`/api/blocs/demo-${scenario}/join`,{user_id:"demo-you",max_price:"150.00"});window.location.assign(`/blocs/demo-${scenario}/room`);}catch(e){setError(e instanceof Error?e.message:"Cannot enter. Reset finished scenarios first.");setBusy(false);}}
  async function reset(){setBusy(true);setError("");try{await api("/api/demo/reset",{});}catch(e){setError(e instanceof Error?e.message:"Cannot reset.");}finally{setBusy(false);}}
  return <main><header><Link href="/" className="wordmark">maxx<span>✳</span></Link><Link href="/under-the-hood">Under the hood</Link></header><h1>Judge mode</h1><p>One-tap demo identity: demo-you. No signup, no real money. Scenarios use simulated sellers and stock. Fixture outcomes are deterministic; live models may choose different offers.</p>{error&&<p role="alert" className="error">{error}</p>}<section className="bloc-grid">{["success","failure","flaky"].map(s=><article key={s} className="bloc-card"><h2>{s==="success"?"Successful deal":s==="failure"?"No deal":"Seller withdrawal"}</h2><p>Enter with a $150 simulated maximum, then close the Bloc to watch.</p><button className="primary" disabled={busy} onClick={()=>void enter(s)}>Enter {s} scenario</button></article>)}</section><button disabled={busy} onClick={()=>void reset()}>Reset judge scenarios</button><p>Restores 800 seeded buyers and eight sellers per scenario; preserves custom Blocs. Active negotiations must finish before reset.</p><Link href="/">Start with a screenshot</Link>{busy&&<p role="status">Preparing demo…</p>}</main>;
}
