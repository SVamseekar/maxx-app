"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, usd, type Bloc, type BlocEvent } from "../../types";
import { ApiError } from "../../../lib/client";
import { safeHref } from "../../../lib/safe-url";
import { loginPath } from "../../../lib/auth-helpers";
import { useAuth } from "../../../components/auth";
import { motion } from "motion/react";
import { ArrowLeft, Clock3, ShieldCheck, Users, Wallet } from "lucide-react";
import { AnimatePresence } from "motion/react";
import HoldDialog from "../../../components/hold-dialog";
import SettlementPanel from "../../../components/settlement-panel";
import { moneyLabel, useMoneyConfig } from "../../../lib/money";
import { AppFooter, Badge, Disclosure, ErrorNotice, Working } from "../../../components/ui";
import NegotiationChat from "../../../components/negotiation-chat";
import GroupDemand from "../../../components/group-demand";
import { AnimatedNumber, useMotionPreferences } from "../../../components/motion-system";
import { needsRoomSnapshot, statusLabel } from "../../../presentation";
import { mergeSnapshot } from "../../state";
import { callSummary, tokenLine } from "../../../lib/call-summary";

/** The starting point of the maximum slider. Beside a simulated crowd, many of whom share the
 * same round limits, 75% of typical would tie with them and lose on joining order. */
function suggestedShare(bloc: Bloc): number {
  return bloc.members.some(m => m.simulated) ? .85 : .75;
}

/** Says plainly who is bidding: replayed or live agents, simulated or verified sellers. */
function modeLine(bloc: Bloc): string {
  const verified = bloc.verified_sellers ?? 0, simulated = Math.max(0, (bloc.seller_count ?? 0) - verified);
  const table = [simulated && `${simulated} simulated ${simulated === 1 ? "seller" : "sellers"}`, verified && `${verified} verified ${verified === 1 ? "seller" : "sellers"} bidding by ${verified === 1 ? "its" : "their"} own rules`].filter(Boolean).join(" and ");
  return `${bloc.mode === "fixture" ? "Deterministic replay · no model calls" : "Live Nemotron on Nebius Token Factory"}${table ? ` · ${table}` : ""}`;
}

export default function Room({ id }: { id: string }) {
  const { reduced } = useMotionPreferences();
  const { user, status: authStatus } = useAuth();
  const [bloc, setBloc] = useState<Bloc | null>(null);
  const [maximum, setMaximum] = useState(0);
  const [now,setNow] = useState(0);
  useEffect(()=>{setNow(Date.now());const timer=setInterval(()=>setNow(Date.now()),1000);return ()=>clearInterval(timer);},[]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const money = useMoneyConfig();
  const paying = !!money?.enabled;
  const [holding, setHolding] = useState(false);
  const [connection, setConnection] = useState("Connecting…");
  const [reconnect, setReconnect] = useState(0);
  const source = useRef<EventSource | null>(null);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const initial = await api<Bloc>(`/api/blocs/${id}`);
        if (!active) return;
        setBloc(previous => mergeSnapshot(previous, initial)); setMaximum(Number([...initial.members].reverse().find(m => m.user_id === "me" && m.status !== "LEFT")?.max_price ?? (Number(initial.typical_price) * suggestedShare(initial)).toFixed(2)));
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
            if (needsRoomSnapshot(event.type)) {
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
    try { const fresh = await api<Bloc>(`/api/blocs/${id}/${name}`, name === "join" ? { max_price: maximum.toFixed(2) } : {}); setBloc(previous => mergeSnapshot(previous, fresh)); }
    catch (e) {
      if (e instanceof ApiError && e.status === 401) { window.location.assign(loginPath(`/blocs/${id}/room`)); return; }
      setError(e instanceof Error ? e.message : "Action failed. Try again.");
    }
    finally { setBusy(false); }
  }
  if (!bloc) return <main id="main-content"><Link className="back-link" href="/blocs"><ArrowLeft size={14} /> All Blocs</Link><div className="loading-surface">{error ? <ErrorNotice message={error} retry={() => setReconnect(r => r + 1)} /> : <Working label="Opening the negotiation room" />}</div></main>;
  const you = [...bloc.members].reverse().find(m => m.user_id === "me" && m.status !== "LEFT");
  const active = bloc.members.filter(m => m.status !== "LEFT");
  const rounds = bloc.events.filter(e => e.type === "tentative_allocation");
  // Seeded demo buyers are not people and place no PayPal hold: never count them as money.
  const crowd = active.filter(m => m.simulated), people = active.filter(m => !m.simulated);
  const replay = bloc.events.find(e => e.type === "live_unavailable")?.data.message;
  const done = ["SETTLED", "FAILED"].includes(bloc.status);
  const money_label = done ? (paying ? "Charged to real buyers" : "Real buyers’ deals") : paying ? "Real PayPal holds" : "Real buyers’ commitments";
  const money_value = done ? people.filter(m => m.status === "WIN").reduce((sum, m) => sum + Number(m.final_price ?? 0), 0) : people.filter(m => m.status === "HELD").reduce((sum, m) => sum + Number(m.max_price), 0);
  const settled = ["SETTLED", "FAILED"].includes(bloc.status);
  const remaining = Math.max(0, Math.ceil(bloc.closes_at - now / 1000));
  const countdown = now === 0 ? "Loading…" : remaining > 0 ? `${Math.floor(remaining / 60)}m ${String(remaining % 60).padStart(2, "0")}s` : "Awaiting start";
  return <main id="main-content" className="room"><Link className="back-link" href="/blocs"><ArrowLeft size={14} /> All Blocs</Link>
    <div className="room-title"><div><h1>{bloc.title}</h1><p>Your buying group. One shared negotiation. Your own maximum.</p></div><Badge tone={bloc.status === "FAILED" ? "warn" : "good"}>{bloc.status === "NEGOTIATING" && <span className="live-dot" aria-hidden="true" />}{statusLabel(bloc.status)}</Badge></div>
    <div className={`mode ${bloc.mode}`}>{modeLine(bloc)} · {paying ? moneyLabel(money) : "Demo commitments, no money moves"}</div>
    {replay && <p className="notice-strip" role="status">Live models were not used for this negotiation: {replay} The deterministic replay ran instead.</p>}
    {error && <ErrorNotice message={error} dismiss={() => setError("")} />}
    <section className="room-metrics" aria-label="Bloc summary"><div><span><Users size={14} /> Buyers together</span><strong><AnimatedNumber value={active.length} /></strong>{crowd.length > 0 && <small className="muted">{people.length} real · {crowd.length} simulated</small>}</div><div><span><Wallet size={14} /> {money_label}</span><strong><AnimatedNumber value={money_value} currency /></strong>{crowd.length > 0 && <small className="muted">{crowd.length} simulated {crowd.length === 1 ? "buyer" : "buyers"} · no money held</small>}</div><div><span><Clock3 size={14} /> {bloc.status === "OPEN" ? "Time to close" : "Negotiation rounds"}</span><strong>{bloc.status === "OPEN" ? countdown : `${bloc.round} / 5`}</strong>{bloc.status !== "OPEN" && <div className="round-track" aria-hidden="true">{[1, 2, 3, 4, 5].map(n => <span key={n} className={n < bloc.round || (settled && n <= bloc.round) ? "done" : n === bloc.round ? "current" : ""}><i /></span>)}</div>}</div></section>
    <div className="room-stack"><GroupDemand bloc={bloc} you={you} order={bloc.status === "OPEN" ? 0 : 2} />
    <motion.div layout="position" style={{ order: 1 }} className="room-grid"><section className="commit-panel">
      <Badge><ShieldCheck size={12} /> Your price is protected</Badge><h2>{settled ? "Your group’s outcome." : "Your maximum. Your limit."}</h2><p>Each winner pays their allocated seller’s price, never above their maximum. {paying ? "PayPal holds your maximum and releases whatever isn’t needed." : "All commitments are simulated."}</p>
      {bloc.status === "OPEN" && <><label className="maximum">Maximum price: <strong>{usd(maximum)}</strong><input aria-label="Maximum price" aria-valuetext={usd(maximum)} type="range" min={(Number(bloc.typical_price)/2).toFixed(2)} max={bloc.typical_price} step="0.01" value={maximum} disabled={busy || !!you || !user || (now > 0 && now/1000 >= bloc.closes_at)} onChange={e => setMaximum(Number(e.target.value))}/><span className="range-labels"><span>{usd(Number(bloc.typical_price) / 2)}</span><span>{usd(bloc.typical_price)}</span></span></label>{you ? <><p>You joined at {usd(you.max_price)}.</p><button disabled={busy} onClick={() => void action("leave")}>Leave Bloc</button></> : authStatus === "loading" ? <Working label="Checking your account" /> : !user ? <div className="join-gate"><p>Sign in to set your maximum and join this group. It takes a minute and costs nothing.</p><Link className="button primary" href={loginPath(`/blocs/${id}/room`)}>Sign in to join</Link><Link className="button" href={`/signup?next=${encodeURIComponent(`/blocs/${id}/room`)}`}>Create an account</Link></div> : <button className="primary" disabled={busy || (now > 0 && now/1000 >= bloc.closes_at)} onClick={() => paying ? setHolding(true) : void action("join")}>{paying ? "Join with a PayPal hold" : "Join with demo commitment"}</button>}{(you || bloc.viewer_is_owner) && <button className="close-bloc" disabled={busy || active.length === 0} onClick={() => void action("start")}>Close Bloc & negotiate</button>}<p className="muted">{you || bloc.viewer_is_owner ? "Anyone committed to this Bloc can close it and start the negotiation. Joining and leaving lock as soon as it starts." : "Once you join, you can close the Bloc to start the negotiation. Joining and leaving lock as soon as it starts."}</p></>}
      {bloc.status === "NEGOTIATING" && <div><Working label="Negotiating for your group" /><p>Round {bloc.round || 1} of at most 5. Your maximum is locked.</p></div>}
      {settled && <motion.div className="outcome" data-testid="outcome" initial={{ opacity: 0, y: reduced ? 0 : 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : .45 }}><div className={`outcome-seal ${bloc.status === "FAILED" ? "no-deal" : ""}`} aria-hidden="true"><ShieldCheck size={28} /></div><h2>{bloc.status === "FAILED" ? "No deal. Nothing charged." : you?.status === "WIN" ? "Your deal is in." : "Negotiation complete."}</h2>{you?.status === "WIN" ? <><div className="deal-price">{usd(you.final_price)}</div><p>Your maximum: {usd(you.max_price)} · Seller {you.seller_id}</p><p>Saving vs typical: {usd(Number(bloc.typical_price) - Number(you.final_price))}</p><p>{paying ? "Your hold is being settled below." : "Simulated allocation. No payment was taken."}</p></> : <p>{bloc.failure_reason ?? (you?.status === "BELOW_CLEARING" ? "Your maximum or seller capacity could not secure an allocation. Your hold was released." : "Join an open Bloc to get your own outcome.")}</p>}<p>{bloc.outcome?.allocations.length ?? 0} buyers allocated · {bloc.outcome?.unserved.length ?? 0} unserved</p>{bloc.status === "FAILED" && <p>{paying ? "Every PayPal hold is being released. Nothing was charged." : "Every active demo commitment has been released."}</p>}</motion.div>}
      {settled && paying && money && <SettlementPanel blocId={id} config={money} signedIn={!!user} />}
      <h3>Round history</h3>{rounds.length ? <table><thead><tr><th>Round</th><th>Avg price</th><th>Served</th></tr></thead><tbody>{rounds.map(e => <tr key={e.id}><td>{e.data.round}</td><td>{usd(e.data.avg_price ?? null)}</td><td>{e.data.served}</td></tr>)}</tbody></table> : <p className="muted">Round results will appear as offers arrive.</p>}
    </section><NegotiationChat bloc={bloc} you={you} connection={connection} reconnect={() => { source.current?.close(); setReconnect(r => r + 1); }} /></motion.div></div>
    <Disclosure title="Market evidence & reference target"><p>Typical {usd(bloc.typical_price)} · Reference target {usd(bloc.target_price)}</p><p>{bloc.target_reason}</p><p>{bloc.market_mode === "fixture" ? "Fixture price history · simulated reference prices" : bloc.market_mode === "live" ? "Tavily-sourced price history" : "Price history unavailable; no target inferred"}</p>{bloc.market_rows.map((row, i) => <p key={i}>{safeHref(row.url) ? <a href={safeHref(row.url)!} target="_blank" rel="noopener noreferrer nofollow">{row.title}</a> : row.title} · {usd(row.price)} + shipping {usd(row.shipping)}</p>)}</Disclosure>
    <Disclosure title={`Under the hood · ${callSummary(bloc.calls)}`}>{bloc.mode === "fixture" && <p>Deterministic fixture policy, no model calls. This does not measure AI negotiation quality.</p>}{bloc.calls.map((c,i) => <p key={i}>{c.purpose} · {c.model ?? "model listing"} · {c.status} · {c.latency_ms} ms · {tokenLine(c.tokens)} · cost {c.cost_usd === null ? "unmeasured" : `$${c.cost_usd} (${c.cost_status})`}</p>)}</Disclosure>
    <AnimatePresence>{holding && money && <HoldDialog key="hold" bloc={bloc} maximum={maximum} config={money} onJoined={fresh => { setBloc(previous => mergeSnapshot(previous, fresh)); setHolding(false); }} onClose={() => setHolding(false)} />}</AnimatePresence>
    <AppFooter />
  </main>;
}
