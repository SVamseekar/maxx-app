"use client";

import { useMoneyConfig } from "../lib/money";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowDown, Check, ChevronDown, Copy, MessageSquare, RefreshCw, Search, X } from "lucide-react";
import { type Bloc, type BlocEvent, type Member, usd } from "../blocs/types";
import { conversationGroups, previousOfferPrice, type ConversationGroup } from "../blocs/conversation";
import { latestOffers } from "../presentation";
import { AnimatedNumber, useMotionPreferences } from "./motion-system";
import { ShimmerText, StreamText } from "./ambient";
import NegotiationMap from "./negotiation-map";

type EntryProps = { group: ConversationGroup; events: BlocEvent[]; stream: boolean; onStream: () => void };

function OfferReplies({ group, events }: Pick<EntryProps, "group" | "events">) {
  const { reduced } = useMotionPreferences();
  const [open, setOpen] = useState(false);
  const panel = useId();
  const rows = group.events.map(event => ({
    id: event.id,
    seller: event.data.seller,
    qty: event.data.qty,
    price: Number(event.data.price),
    before: previousOfferPrice(events, event.data.seller, event.id),
  })).filter(row => Number.isFinite(row.price));
  const best = rows.length ? Math.min(...rows.map(row => row.price)) : null;
  return <div className="chat-offer-details">
    <button type="button" className="chat-offer-toggle" aria-expanded={open} aria-controls={panel} onClick={() => setOpen(!open)}>
      <motion.span animate={{ rotate: open ? 0 : -90 }} transition={{ duration: reduced ? 0 : .18 }}><ChevronDown size={14} aria-hidden="true" /></motion.span>
      <span>{group.events.length} seller {group.events.length === 1 ? "offer" : "offers"}</span>
      {best !== null && <span className="chat-sub">best <strong>{usd(best)}</strong></span>}
    </button>
    <AnimatePresence initial={false}>{open && <motion.div id={panel} className="chat-offer-list" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: reduced ? 0 : .24, ease: [.2, .8, .2, 1] }}>
      {rows.map((row, index) => {
        const change = row.before === null ? null : Math.round((row.price - row.before) * 100) / 100;
        return <motion.div key={row.id} className={row.price === best ? "is-best" : ""} initial={{ opacity: 0, x: reduced ? 0 : -6 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: reduced ? 0 : .22, delay: reduced ? 0 : index * .035 }}>
          <span>Seller {row.seller}</span>
          <span>{row.qty} units available</span>
          {change !== null && change !== 0 && <em className={change < 0 ? "drop" : "rise"}>{change < 0 ? "−" : "+"}{usd(Math.abs(change))}</em>}
          <strong>{usd(row.price)}</strong>
        </motion.div>;
      })}
    </motion.div>}</AnimatePresence>
  </div>;
}

function Sender({ name, role, detail }: { name: string; role?: string; detail?: string }) {
  return <div className="chat-reply-meta"><strong>{name}</strong>{role && <span className="role">{role}</span>}{detail && <span>{detail}</span>}</div>;
}

function Body({ text, stream, onStream }: { text: string; stream: boolean; onStream: () => void }) {
  return <p>{stream ? <StreamText text={text} onProgress={onStream} /> : text}</p>;
}

function ConversationEntry({ group, events, stream, onStream }: EntryProps) {
  const event = group.events[0];
  if (group.kind === "round_start") return <div className="chat-round"><span>Round {group.round}</span><span /></div>;
  if (group.kind === "reserve_set") return <div className="chat-tool"><Check size={12} aria-hidden="true" /><span>Reserve set</span><strong>{usd(event.data.price ?? null)}</strong></div>;
  if (group.kind === "seller_offer") return <OfferReplies group={group} events={events} />;
  if (group.kind === "negotiator_message") {
    const recipients = [...new Set(group.events.map(e => e.data.to).filter(Boolean))];
    return <div className="chat-reply">
      <Sender name="Maxx" role="Negotiator" detail={`to ${recipients.length > 1 ? `${recipients.length} sellers` : `seller ${recipients[0] ?? "—"}`}`} />
      <Body text={event.data.text ?? "No message text recorded."} stream={stream} onStream={onStream} />
      {recipients.length > 1 && <span className="chat-recipients">Sellers {recipients.join(", ")}</span>}
    </div>;
  }
  if (group.kind === "tentative_allocation") {
    const text = `${event.data.served ?? 0} buyers can be served${event.data.avg_price ? ` at an average of ${usd(event.data.avg_price)}` : " at this point"}.${event.data.unserved !== undefined ? ` ${event.data.unserved} remain unserved.` : ""}`;
    return <div className="chat-reply"><Sender name="Allocation check" role="Deterministic" detail={`Round ${group.round}`} /><Body text={text} stream={stream} onStream={onStream} /></div>;
  }
  const text = group.kind === "seller_withdrew" ? `Seller ${event.data.seller} withdrew. Their offer is excluded from the negotiation.` : group.kind === "seller_unavailable" ? `Seller ${event.data.seller} is unavailable. Continuing with the remaining sellers.` : "A provider call failed. Retrying once.";
  return <div className="chat-reply chat-exception"><Sender name={group.kind === "provider_retry" ? "Connection update" : "Seller update"} detail={`Round ${group.round}`} /><Body text={text} stream={stream} onStream={onStream} /></div>;
}

/** Layout adapted from Beautiful UI ChatComposer (MIT; see THIRD_PARTY_NOTICES.md).
 * Uses persisted negotiation events in place of the gallery's scripted conversation.
 */
export default function NegotiationChat({ bloc, you, connection, reconnect }: { bloc: Bloc; you?: Member; connection: string; reconnect: () => void }) {
  const money = useMoneyConfig();
  const { reduced } = useMotionPreferences();
  const [tab, setTab] = useState<"conversation" | "offers">("conversation");
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [copyState, setCopyState] = useState("");
  const [unread, setUnread] = useState(0);
  const feed = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const followLatest = useRef(true);
  const lastScrollTop = useRef(0);
  const seenGroups = useRef(0);
  const id = useId();
  const groups = useMemo(() => conversationGroups(bloc.events), [bloc.events]);
  const offers = useMemo(() => latestOffers(bloc.events), [bloc.events]);
  // Entries present when the room opened (saved history) appear instantly; only live arrivals animate.
  const [initialIds] = useState(() => new Set(groups.map(group => group.id)));
  const settled = ["SETTLED", "FAILED"].includes(bloc.status);
  const visible = groups.filter(group => !query || JSON.stringify(group).toLowerCase().includes(query.toLowerCase()));
  const lastEvent = bloc.events.at(-1);
  const best = offers.length ? offers.reduce((low, offer) => Number(offer.price) < Number(low.price) ? offer : low) : null;

  const pin = useCallback((behavior: ScrollBehavior = "auto") => {
    const node = feed.current;
    if (node) node.scrollTo({ top: node.scrollHeight, behavior: reduced ? "auto" : behavior });
  }, [reduced]);

  useEffect(() => {
    const added = groups.length - seenGroups.current;
    seenGroups.current = groups.length;
    if (query || tab !== "conversation") return;
    if (followLatest.current) { pin("smooth"); setUnread(0); }
    else if (added > 0) setUnread(count => count + added);
  }, [groups.length, bloc.status, query, tab, pin]);
  useEffect(() => { if (searchOpen) search.current?.focus(); }, [searchOpen]);

  async function copyTranscript() {
    try {
      await navigator.clipboard.writeText(bloc.events.map(event => `${event.type}: ${JSON.stringify(event.data)}`).join("\n"));
      setCopyState("Transcript copied");
    } catch { setCopyState("Copy unavailable in this browser"); }
  }
  function selectTab(value: "conversation" | "offers") {
    setTab(value); setQuery(""); setSearchOpen(false); setCopyState("");
  }
  const streamFrom = groups.length - 2;
  return <section className="negotiation-chat" aria-label="Negotiation conversation">
    <div className="chat-tabs-bar"><div role="tablist" aria-label="Negotiation view">{(["conversation", "offers"] as const).map((value, index) => <button key={value} id={`${id}-${value}-tab`} role="tab" aria-selected={tab === value} aria-controls={`${id}-${value}`} tabIndex={tab === value ? 0 : -1} onClick={() => selectTab(value)} onKeyDown={event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? "conversation" : event.key === "End" ? "offers" : index === 0 ? "offers" : "conversation";
      selectTab(next); document.getElementById(`${id}-${next}-tab`)?.focus();
    }} className={tab === value ? "is-selected" : ""}>
      {tab === value && <motion.span className="chat-tab-pill" layoutId={`${id}-tab-pill`} transition={{ type: "spring", stiffness: 420, damping: 36 }} />}
      <span className="chat-tab-label">{value === "conversation" ? "Conversation" : "Seller offers"}</span>
      {value === "offers" && offers.length > 0 && <span className="chat-tab-count">{offers.length}</span>}
    </button>)}</div><div className="chat-actions"><button aria-label={searchOpen ? "Close conversation search" : "Search conversation"} disabled={tab !== "conversation"} onClick={() => { setSearchOpen(!searchOpen); setQuery(""); }}>{searchOpen ? <X size={16} /> : <Search size={16} />}</button><button aria-label="Copy transcript" onClick={() => void copyTranscript()}>{copyState === "Transcript copied" ? <Check size={16} /> : <Copy size={16} />}</button></div></div>
    <AnimatePresence initial={false}>{searchOpen && <motion.div className="chat-search" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: reduced ? 0 : .18 }}><Search size={15} /><input ref={search} aria-label="Search negotiation messages" placeholder="Find a message, seller or price…" value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === "Escape") { setSearchOpen(false); setQuery(""); document.getElementById(`${id}-conversation-tab`)?.focus(); } }} /><span>{visible.length} results</span></motion.div>}</AnimatePresence>
    <div className="chat-connection"><span className={`status-dot ${settled || connection.includes("connected") ? "connected" : ""} ${bloc.status === "NEGOTIATING" && connection.includes("connected") ? "is-live" : ""}`} /><span>{settled ? "Saved conversation" : connection}</span><button onClick={reconnect} aria-label="Refresh negotiation"><RefreshCw size={13} /></button></div>
    <div id={`${id}-conversation`} role="tabpanel" aria-labelledby={`${id}-conversation-tab`} hidden={tab !== "conversation"} className="chat-panel">
      <div className="chat-scroll" ref={feed} tabIndex={0} aria-label="Conversation history" onScroll={event => {
        // Content growth can briefly leave the view short of the bottom, so only an upward scroll stops following.
        const node = event.currentTarget;
        if (node.scrollHeight - node.scrollTop - node.clientHeight < 48) { followLatest.current = true; setUnread(0); }
        else if (node.scrollTop < lastScrollTop.current) followLatest.current = false;
        lastScrollTop.current = node.scrollTop;
      }}>
        {you && !query && <div className="chat-user-context"><span>Your commitment</span><p>One unit, up to <strong>{usd(you.max_price)}</strong>.</p></div>}
        {groups.length === 0 && <div className="chat-empty"><MessageSquare size={25} /><h3>The conversation starts here.</h3><p>When you close this Bloc, Maxx will ask seller agents for offers. You can follow their responses here.</p></div>}
        {visible.map(group => {
          const fresh = !initialIds.has(group.id);
          const index = groups.indexOf(group);
          return <div key={group.id} className={`chat-entry ${fresh ? "is-fresh" : ""}`}><ConversationEntry group={group} events={bloc.events} stream={fresh && index >= streamFrom && !query} onStream={() => { if (followLatest.current) pin(); }} /></div>;
        })}
        {query && visible.length === 0 && <p className="chat-no-results">No messages match “{query}”.</p>}
        {settled && !query && <div className={`chat-reply chat-final ${initialIds.size === groups.length ? "" : "is-fresh"}`}><div className="chat-reply-meta"><Check size={14} /><strong>Outcome</strong><span>{bloc.status === "FAILED" ? "No deal" : "Negotiation complete"}</span></div><p>{bloc.status === "FAILED" ? bloc.failure_reason ?? "No qualifying offer. All demo commitments were released." : you?.status === "WIN" ? `Your unit was allocated from seller ${you.seller_id} for ${usd(you.final_price)}, within your ${usd(you.max_price)} maximum.` : `${bloc.outcome?.allocations.length ?? 0} buyers received allocations; ${bloc.outcome?.unserved.length ?? 0} remained unserved.`}</p><span className="chat-recipients">{money?.enabled ? "Allocation settled through PayPal; see the settlement panel." : "Simulated allocation. No payment was taken."}</span></div>}
        {bloc.status === "NEGOTIATING" && !query && <div className="chat-pending" aria-hidden="true"><span className="typing-dots"><i /><i /><i /></span><ShimmerText>Waiting for the next response</ShimmerText></div>}
      </div>
      <AnimatePresence>{unread > 0 && <motion.button type="button" className="chat-jump" initial={{ opacity: 0, y: reduced ? 0 : 10, scale: .96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: reduced ? 0 : 10 }} transition={{ duration: reduced ? 0 : .2 }} onClick={() => { followLatest.current = true; setUnread(0); pin("smooth"); }}><ArrowDown size={13} aria-hidden="true" /> {unread} new</motion.button>}</AnimatePresence>
      <div className="chat-bottom"><span>Agent conversation · read only</span><button onClick={() => { followLatest.current = true; setUnread(0); pin("smooth"); }}>Latest <ArrowDown size={13} /></button></div>
    </div>
    <div id={`${id}-offers`} role="tabpanel" aria-labelledby={`${id}-offers-tab`} hidden={tab !== "offers"} className="chat-panel chat-offers-panel">
      <div className="chat-offers-intro"><div><h3>Latest available offers</h3><p>Withdrawn or unavailable sellers are excluded.</p></div>{best && <div className="chat-best"><span>Best offer · Seller {best.seller}</span><strong><AnimatedNumber value={Number(best.price)} currency /></strong></div>}</div>
      {offers.length ? <><NegotiationMap offers={offers} negotiating={bloc.status === "NEGOTIATING"} pulse={lastEvent ? { id: lastEvent.id, type: lastEvent.type, seller: lastEvent.data.seller } : null} bestSeller={best?.seller} /><div className="chat-offer-table"><table><thead><tr><th>Seller</th><th>Unit price</th><th>Change</th><th>Capacity</th><th>Round</th></tr></thead><tbody>{offers.map(offer => <tr key={offer.seller} className={offer.seller === best?.seller ? "is-best" : ""}><td>Seller {offer.seller}</td><td><AnimatedNumber value={Number(offer.price)} currency /></td><td><OfferChange events={bloc.events} seller={offer.seller} price={Number(offer.price)} /></td><td>{offer.qty} units</td><td>{offer.round}</td></tr>)}</tbody></table></div></> : <div className="chat-empty"><p>No seller offers have arrived yet.</p></div>}
    </div>
    <span className="sr-only" role="status">{copyState || (bloc.status === "NEGOTIATING" ? `Round ${bloc.round}. ${offers.length} available seller offers.` : "")}</span>
  </section>;
}

/** Change against the seller's quote before its latest one. */
function OfferChange({ events, seller, price }: { events: BlocEvent[]; seller: string; price: number }) {
  const latest = [...events].reverse().find(event => event.type === "seller_offer" && event.data.seller === seller);
  const before = latest ? previousOfferPrice(events, seller, latest.id) : null;
  if (before === null) return <span className="muted">—</span>;
  const change = Math.round((price - before) * 100) / 100;
  if (change === 0) return <span className="muted">No change</span>;
  return <span className={change < 0 ? "delta drop" : "delta rise"}>{change < 0 ? "−" : "+"}{usd(Math.abs(change))}</span>;
}
