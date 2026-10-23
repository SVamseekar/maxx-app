"use client";

import { useMemo, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { motion } from "motion/react";
import { Users } from "lucide-react";
import { type Bloc, type Member, usd } from "../blocs/types";
import { activeBuyers, buyersAtOrAbove, chartDomain, demandSteps, median, percentBelow } from "../blocs/group";
import { latestOffers } from "../presentation";
import { AnimatedNumber, useMotionPreferences } from "./motion-system";

const MAX_DOTS = 1500;

/**
 * The group, made visible. Everything here is derived from the buyers' recorded maximums and the
 * sellers' recorded offers: the demand curve is "how many buyers would pay at least this much".
 * It is not a forecast, and it does not say how many buyers a seller can actually serve.
 */
export default function GroupDemand({ bloc, you, order }: { bloc: Bloc; you?: Member; order: number }) {
  const { reduced } = useMotionPreferences();
  const [hover, setHover] = useState<number | null>(null);
  const buyers = useMemo(() => activeBuyers(bloc.members), [bloc.members]);
  const limits = useMemo(() => buyers.map(buyer => buyer.limit).sort((a, b) => a - b), [buyers]);
  const offers = useMemo(() => latestOffers(bloc.events), [bloc.events]);
  const settled = ["SETTLED", "FAILED"].includes(bloc.status);
  const best = offers.length ? Math.min(...offers.map(offer => Number(offer.price))) : null;
  const yourLimit = you ? Number(you.max_price) : null;
  const paid = you?.status === "WIN" && you.final_price !== null ? Number(you.final_price) : null;
  const failed = bloc.status === "FAILED";
  const marker = paid ?? (settled && !failed ? null : best);
  const [low, high] = useMemo(() => chartDomain(limits, [marker ?? NaN, yourLimit ?? NaN]), [limits, marker, yourLimit]);
  const total = limits.length;
  if (total === 0) return <motion.section layout="position" style={{ order }} className="group-panel" aria-label="Your group"><div className="group-head"><div><h2>Your group</h2><p>No buyers have joined yet. Join to start the group.</p></div></div></motion.section>;

  const x = (price: number) => ((price - low) / (high - low)) * 100;
  const y = (count: number) => 100 - (count / total) * 100;
  const steps = demandSteps(limits, low, high);
  const line = steps.map(([price, count], index) => `${index ? "L" : "M"}${x(price).toFixed(2)} ${y(count).toFixed(2)}`).join(" ");
  const area = `${line} L100 100 L0 100 Z`;
  const at = (price: number) => buyersAtOrAbove(limits, price);
  const markerCount = marker === null ? null : at(marker);
  const allocated = new Set(bloc.outcome?.allocations.map(allocation => allocation.member_id));
  const dots = [...buyers].sort((a, b) => b.limit - a.limit).slice(0, MAX_DOTS);
  const dotClass = (buyer: (typeof dots)[number]) => [
    buyer.id === you?.id ? "you" : "",
    settled ? (allocated.has(buyer.id) ? "served" : "unserved") : best !== null && buyer.limit >= best ? "covered" : "",
  ].join(" ").trim();
  const shown = hover ?? null;
  const chipShift = (percent: number) => ({ translate: percent < 16 ? "0 0" : percent > 84 ? "-100% 0" : "-50% 0" });
  const clampLeft = (percent: number) => `clamp(64px, ${percent}%, calc(100% - 64px))`;
  const step = (high - low) / 100;
  const move = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setHover(low + Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)) * (high - low));
  };
  const keys = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = hover ?? yourLimit ?? (low + high) / 2;
    const next = event.key === "ArrowRight" || event.key === "ArrowUp" ? current + step : event.key === "ArrowLeft" || event.key === "ArrowDown" ? current - step : event.key === "Home" ? low : event.key === "End" ? high : null;
    if (next === null) return;
    event.preventDefault();
    setHover(Math.min(high, Math.max(low, next)));
  };
  const summary = `${total} buyers. Median limit ${usd(median(limits))}.${yourLimit !== null ? ` Your limit of ${usd(yourLimit)} is higher than ${percentBelow(limits, yourLimit)}% of the group.` : ""}${best !== null ? ` ${at(best)} buyers have limits that cover the best seller offer of ${usd(best)}.` : ""}`;

  return <motion.section layout="position" style={{ order }} className="group-panel" aria-label="Your group">
    <div className="group-head"><div><h2>Your group</h2><p>Every buyer sets a private maximum. This is how those limits stack up: the higher the price, the fewer buyers are still in.</p></div><span className="group-note"><Users size={13} aria-hidden="true" /> Aggregated · demo buyers are simulated</span></div>
    <p className="sr-only">{summary}</p>
    <div className="group-body">
      <div className="demand">
        <div className="demand-y" aria-hidden="true"><span>{total} buyers</span><span>0</span></div>
        <div className="demand-plot" role="slider" tabIndex={0} aria-label="Explore how many buyers would pay each price" aria-valuemin={Math.floor(low)} aria-valuemax={Math.ceil(high)} aria-valuenow={Math.round(shown ?? yourLimit ?? (low + high) / 2)} aria-valuetext={`At ${usd(shown ?? yourLimit ?? (low + high) / 2)}, ${at(shown ?? yourLimit ?? (low + high) / 2)} buyers would pay`} onPointerMove={move} onPointerDown={move} onPointerLeave={() => setHover(null)} onKeyDown={keys} onBlur={() => setHover(null)}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <defs><linearGradient id={`${bloc.id}-area`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--accent)" stopOpacity=".34" /><stop offset="1" stopColor="var(--accent)" stopOpacity="0" /></linearGradient></defs>
            {[25, 50, 75].map(row => <line key={row} x1="0" x2="100" y1={row} y2={row} className="demand-grid" />)}
            <motion.path d={area} fill={`url(#${bloc.id}-area)`} initial={{ opacity: reduced ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ duration: reduced ? 0 : .9, delay: reduced ? 0 : .35 }} />
            <motion.path d={line} className="demand-line" initial={{ pathLength: reduced ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: reduced ? 0 : 1.1, ease: [.2, .8, .2, 1] }} />
          </svg>
          {marker !== null && <motion.div className={`demand-marker ${paid !== null ? "paid" : failed ? "offer miss" : "offer"}`} initial={false} animate={{ left: `${x(marker)}%` }} transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 160, damping: 22 }}><span className="chip" style={chipShift(x(marker))}>{paid !== null ? "You paid" : "Best offer"} <strong>{usd(marker)}</strong> · <AnimatedNumber value={markerCount ?? 0} /> buyers</span></motion.div>}
          {yourLimit !== null && <div className="demand-marker you" style={{ left: `${x(yourLimit)}%` }}><span className="dot" style={{ top: `${y(at(yourLimit))}%` }} /><span className="chip" style={chipShift(x(yourLimit))}>Your limit <strong>{usd(yourLimit)}</strong></span></div>}
          {shown !== null && <div className="demand-hover" style={{ left: `${x(shown)}%` }}><span style={{ top: `${y(at(shown))}%` }} /></div>}
          {shown !== null && <div className="demand-readout" style={{ left: clampLeft(x(shown)) }}>At <strong>{usd(shown)}</strong> · {at(shown)} buyers</div>}
        </div>
        <div className="demand-x" aria-hidden="true"><span>{usd(low)}</span><span>{usd((low + high) / 2)}</span><span>{usd(high)}</span></div>
      </div>
      <div className="group-stats">
        <div><span className="stat-label">In the group</span><strong className="stat-value"><AnimatedNumber value={total} /></strong><small>buyers with a maximum</small></div>
        {yourLimit !== null && <div><span className="stat-label">Your limit</span><strong className="stat-value">{usd(yourLimit)}</strong><small>higher than <AnimatedNumber value={percentBelow(limits, yourLimit)} />% of the group</small></div>}
        <div><span className="stat-label">Median limit</span><strong className="stat-value">{usd(median(limits))}</strong><small>half the group would pay more</small></div>
        {best !== null && markerCount !== null && <div className={`stat-offer ${failed ? "miss" : ""}`}><span className="stat-label">{paid !== null ? "Your price" : failed ? "Best offer, no deal" : "Best offer"}</span><strong className="stat-value">{usd(marker)}</strong><small><AnimatedNumber value={markerCount} /> buyers ({Math.round((markerCount / total) * 100)}%) have limits that cover it</small></div>}
      </div>
    </div>
    <div className="cohort" aria-hidden="true">{dots.map((buyer, index) => <i key={buyer.id} className={dotClass(buyer)} style={{ "--i": Math.min(index, 600) } as CSSProperties} />)}</div>
    <div className="cohort-legend" aria-hidden="true"><span><i /> Buyer</span>{you && <span><i className="you" /> You</span>}{!settled && best !== null && <span><i className="covered" /> Limit covers best offer</span>}{settled && (allocated.size > 0 ? <><span><i className="served" /> Allocated</span><span><i className="unserved" /> Not allocated</span></> : <span><i className="unserved" /> No allocation · commitments released</span>)}<small>One dot per buyer, highest limit first{total > MAX_DOTS ? ` · first ${MAX_DOTS} shown` : ""}</small></div>
  </motion.section>;
}
