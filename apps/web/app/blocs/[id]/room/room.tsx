"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, usd, type Bloc, type BlocEvent } from "../../types";
import { mergeSnapshot } from "../../state";

export default function Room({ id }: { id: string }) {
  const [bloc, setBloc] = useState<Bloc | null>(null);
  const [maximum, setMaximum] = useState(0);
  const [now,setNow] = useState(0);
  useEffect(()=>{setNow(Date.now());const timer=setInterval(()=>setNow(Date.now()),1000);return ()=>clearInterval(timer);},[]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [connection, setConnection] = useState("Connecting…");
  const [reconnect, setReconnect] = useState(0);
  const source = useRef<EventSource | null>(null);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const initial = await api<Bloc>(`/api/blocs/${id}`);
        if (!active) return;
        setBloc(previous => mergeSnapshot(previous, initial)); setMaximum(Number([...initial.members].reverse().find(m => m.user_id === "demo-you" && m.status !== "LEFT")?.max_price ?? (Number(initial.typical_price) * .75).toFixed(2)));
        if (["SETTLED", "FAILED"].includes(initial.status)) { setConnection("Outcome saved"); return; }
        const cursor = initial.events.at(-1)?.id ?? 0;
        const stream = new EventSource(`/api/blocs/${id}/stream?after=${cursor}`);
        source.current = stream;
        stream.onopen = () => setConnection("Live event stream connected");
        stream.onmessage = message => {
          if (!active) return;
          try {
            const event = JSON.parse(message.data) as BlocEvent;
            if (!Number.isInteger(event.id) || typeof event.type !== "string") return;
            setBloc(previous => previous ? { ...previous, round: event.data.round ?? previous.round, status: event.type === "state_changed" ? event.data.status ?? previous.status : previous.status, events: previous.events.some(e => e.id === event.id) ? previous.events : [...previous.events, event] } : previous);
            if (["cleared", "failed", "member_joined"].includes(event.type)) {
              void api<Bloc>(`/api/blocs/${id}`).then(fresh => { if (active) setBloc(previous => mergeSnapshot(previous, fresh)); }).catch(() => { if (active) setError("Cannot refresh the saved outcome. Reconnect to retry."); });
            }
            if (["cleared", "failed"].includes(event.type)) { stream.close(); setConnection("Outcome saved"); }
          } catch { setError("Unreadable stream event. Reconnect to reload saved events."); }
        };
        stream.addEventListener("reset", () => { stream.close(); setError("Demo was reset. Reconnect to reload the room."); });
        stream.onerror = () => { setConnection("Reconnecting to saved events…"); void api<Bloc>(`/api/blocs/${id}`).then(fresh => { if (!active) return; setBloc(previous => mergeSnapshot(previous, fresh)); if (["SETTLED", "FAILED"].includes(fresh.status)) { stream.close(); setConnection("Outcome saved"); } }).catch(() => { if (active) setError("Connection interrupted. Reconnect to retry."); }); };
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Cannot open this room."); }
    }
    setError(""); void load();
    return () => { active = false; source.current?.close(); };
  }, [id, reconnect]);

  async function action(name: "join" | "leave" | "start") {
    setBusy(true); setError("");
    try { const fresh = await api<Bloc>(`/api/blocs/${id}/${name}`, name === "join" ? { user_id: "demo-you", max_price: maximum.toFixed(2) } : name === "leave" ? { user_id: "demo-you" } : {}); setBloc(previous => mergeSnapshot(previous, fresh)); }
    catch (e) { setError(e instanceof Error ? e.message : "Action failed. Try again."); }
    finally { setBusy(false); }
  }
  if (!bloc) return <main><header><Link href="/blocs">Back to Blocs</Link></header><p role={error ? "alert" : "status"}>{error || "Loading the room…"}</p><button onClick={() => setReconnect(r => r + 1)}>Retry</button></main>;
  const you = [...bloc.members].reverse().find(m => m.user_id === "demo-you" && m.status !== "LEFT");
  const active = bloc.members.filter(m => m.status !== "LEFT");
  const rounds = bloc.events.filter(e => e.type === "tentative_allocation");
  const transcript = bloc.events.filter(e => ["round_start", "seller_offer", "negotiator_message", "seller_withdrew", "seller_unavailable", "provider_retry", "reserve_set"].includes(e.type));
  const settled = ["SETTLED", "FAILED"].includes(bloc.status);
  return <main className="room"><header><Link href="/" className="wordmark">maxx<span>✳</span></Link><Link href="/blocs">All Blocs</Link><Link href="/under-the-hood">Under the hood</Link></header>
    <div className={`mode ${bloc.mode}`}>{bloc.mode === "fixture" ? "Fixture agents · all offers are simulated" : "Live Nebius models · sellers and stock are simulated"} · Demo commitment, no money moves</div>
    <div className="room-title"><div><h1>{bloc.title}</h1><p>{active.length} buyers · Typical {usd(bloc.typical_price)} · Reference target {usd(bloc.target_price)}</p></div><span className="move">{bloc.status}</span></div>
    <p role="status" className="stream-status">{connection} <button onClick={() => { source.current?.close(); setReconnect(r => r + 1); }}>Reconnect</button></p>
    {error && <p className="error" role="alert">{error}</p>}
    <section><p>Active demo commitments: <strong>{usd(bloc.committed_total)}</strong></p>{bloc.status === "OPEN" && <p role="timer">{now === 0 ? "Loading countdown…" : Math.max(0,Math.ceil(bloc.closes_at-now/1000)) > 0 ? `Closes in ${Math.max(0,Math.ceil(bloc.closes_at-now/1000))} seconds` : "Countdown ended. Waiting for negotiation to start."}</p>}<p>{bloc.target_reason}</p><p>{bloc.market_mode === "fixture" ? "Fixture price history · simulated reference prices" : bloc.market_mode === "live" ? "Tavily-sourced price history" : "Price history unavailable; no target inferred"}</p><ul>{bloc.market_rows.map((r,i)=><li key={i}><a href={r.url} target="_blank" rel="noopener noreferrer">{r.title}</a> · {usd(r.price)} + shipping {usd(r.shipping)}</li>)}</ul></section>
    <div className="room-grid"><section className="commit-panel">
      <h2>Your maximum. Your limit.</h2><p>Each winner pays their allocated seller’s price, never above their maximum. All commitments are simulated.</p>
      {bloc.status === "OPEN" && <><label className="maximum">Maximum price: <strong>{usd(maximum)}</strong><input aria-label="Maximum price" type="range" min={(Number(bloc.typical_price)/2).toFixed(2)} max={bloc.typical_price} step="0.01" value={maximum} disabled={busy || !!you || (now > 0 && now/1000 >= bloc.closes_at)} onChange={e => setMaximum(Number(e.target.value))}/></label>{you ? <><p>You joined at {usd(you.max_price)}.</p><button disabled={busy} onClick={() => void action("leave")}>Leave Bloc</button></> : <button className="primary" disabled={busy || (now > 0 && now/1000 >= bloc.closes_at)} onClick={() => void action("join")}>Join with demo commitment</button>}<button className="close-bloc" disabled={busy || active.length === 0} onClick={() => void action("start")}>Close Bloc & negotiate</button><p className="muted">Judge control starts the negotiation. Joining and leaving lock as soon as it starts.</p></>}
      {bloc.status === "NEGOTIATING" && <div role="status"><div className="spinner"/><p>Round {bloc.round || 1} of at most 5. Your maximum is locked.</p></div>}
      {settled && <div className="outcome" data-testid="outcome"><h2>{bloc.status === "FAILED" ? "No deal. Nothing charged." : you?.status === "WIN" ? "Your deal is in." : "Negotiation complete."}</h2>{you?.status === "WIN" ? <><div className="deal-price">{usd(you.final_price)}</div><p>Your maximum: {usd(you.max_price)} · Seller {you.seller_id}</p><p>Saving vs typical: {usd(Number(bloc.typical_price) - Number(you.final_price))}</p><p>Simulated allocation. No payment was taken.</p></> : <p>{bloc.failure_reason ?? (you?.status === "BELOW_CLEARING" ? "Your maximum or seller capacity could not secure an allocation. Your demo commitment was released." : "Join an open Bloc to get your own outcome.")}</p>}<p>{bloc.outcome?.allocations.length ?? 0} buyers allocated · {bloc.outcome?.unserved.length ?? 0} unserved</p>{bloc.status === "FAILED" && <p>Every active demo commitment has been released.</p>}</div>}
      <h3>Round history</h3>{rounds.length ? <table><thead><tr><th>Round</th><th>Avg price</th><th>Served</th></tr></thead><tbody>{rounds.map(e => <tr key={e.id}><td>{e.data.round}</td><td>{usd(e.data.avg_price ?? null)}</td><td>{e.data.served}</td></tr>)}</tbody></table> : <p className="muted">Round results will appear as offers arrive.</p>}
    </section><section className="transcript" aria-label="Negotiation transcript"><h2>Negotiation room</h2><p className="muted">Durable event history. Seller private floors stay on the server.</p>{transcript.length === 0 && <p>Close the Bloc to start. Up to eight seller agents will submit offers each round.</p>}<ol>{transcript.map(e => <li key={e.id} className={e.type === "seller_offer" ? "seller-line" : "maxx-line"}><strong>{e.type === "seller_offer" ? `Seller ${e.data.seller}` : e.type === "round_start" ? `Round ${e.data.round}` : "Maxx"}</strong><p>{e.type === "seller_offer" ? `${usd(e.data.price ?? null)} · up to ${e.data.qty} units` : e.type === "negotiator_message" ? `To seller ${e.data.to}: ${e.data.text}` : e.type === "reserve_set" ? `Reserve ${usd(e.data.price ?? null)}` : e.type === "seller_withdrew" ? `Seller ${e.data.seller} withdrew. Recalculating without their offer.` : e.type === "seller_unavailable" ? `Seller ${e.data.seller} unavailable; excluded.` : e.type === "provider_retry" ? "Provider call failed; one bounded retry." : "Requesting this round’s offers."}</p></li>)}</ol></section></div>
    <details><summary>Under the hood · {bloc.calls.length} provider calls</summary>{bloc.mode === "fixture" && <p>Deterministic fixture policy, no model calls. This does not measure AI negotiation quality.</p>}{bloc.calls.map((c,i) => <p key={i}>{c.purpose} · {c.model ?? "model listing"} · {c.status} · {c.latency_ms} ms · tokens {c.tokens ? JSON.stringify(c.tokens) : "unavailable"} · cost {c.cost_usd === null ? "unmeasured" : `$${c.cost_usd} (${c.cost_status})`}</p>)}</details>
    <footer>USD only · One unit per member · Simulated sellers and commitments · PayPal deferred</footer>
  </main>;
}
