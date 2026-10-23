"use client";

import { AnimatePresence, motion } from "motion/react";
import { Bot, Store } from "lucide-react";
import { AnimatedNumber, useMotionPreferences } from "./motion-system";

type Offer = { seller: string; price: string; qty: number; round: number };
type Pulse = { id: number; type: string; seller?: string } | null;
const positions = [
  { x: 50, y: 30 }, { x: 150, y: 30 }, { x: 250, y: 30 }, { x: 350, y: 30 },
  { x: 50, y: 190 }, { x: 150, y: 190 }, { x: 250, y: 190 }, { x: 350, y: 190 },
];

/**
 * Lines connect real received offers to Maxx; there are no invented agent states.
 * A traveling spark marks a real event: an outbound request, or one seller's reply.
 */
export default function NegotiationMap({ offers, negotiating, pulse, bestSeller }: { offers: Offer[]; negotiating: boolean; pulse: Pulse; bestSeller?: string }) {
  const { reduced } = useMotionPreferences();
  return <div className="negotiation-map" aria-label="Available seller offers">
    <svg className="offer-connections" viewBox="0 0 400 220" preserveAspectRatio="none" aria-hidden="true">
      {offers.slice(0, 8).map((offer, index) => {
        const { x, y } = positions[index];
        const toSeller = `M200 110 C200 ${y < 110 ? 65 : 155},${x} 110,${x} ${y}`;
        const toMaxx = `M${x} ${y} C${x} 110,200 ${y < 110 ? 65 : 155},200 110`;
        const outbound = pulse?.type === "negotiator_message";
        const inbound = pulse?.type === "seller_offer" && pulse.seller === offer.seller;
        return <g key={offer.seller}>
          <path d={toSeller} stroke={offer.seller === bestSeller ? "var(--mint)" : "var(--line-strong)"} strokeOpacity={offer.seller === bestSeller ? .55 : 1} />
          <motion.path key={`${offer.price}-${offer.round}`} d={toSeller} stroke="var(--accent)" strokeOpacity=".6" initial={{ pathLength: 0, opacity: .3 }} animate={{ pathLength: 1, opacity: .65 }} transition={{ duration: reduced ? 0 : .7, ease: [.2, .8, .2, 1] }} />
          {!reduced && (outbound || inbound) && <motion.path key={`spark-${pulse?.id}`} className="offer-spark" d={outbound ? toSeller : toMaxx} pathLength={1} stroke={outbound ? "var(--accent)" : "var(--mint)"} initial={{ strokeDasharray: "0.16 1", strokeDashoffset: 0.16, opacity: 1 }} animate={{ strokeDashoffset: -1, opacity: [1, 1, 0] }} transition={{ duration: .9, ease: "easeInOut", delay: outbound ? index * .05 : 0 }} />}
        </g>;
      })}
    </svg>
    <div className={`negotiation-core ${negotiating ? "active" : ""}`} aria-hidden="true"><Bot size={25} /><span>Maxx</span></div>
    <AnimatePresence initial={false}>{offers.slice(0, 8).map((offer, index) => <motion.div layout={!reduced} key={offer.seller} className={`offer-chip offer-node ${offer.seller === bestSeller ? "is-best" : ""}`} style={{ left: `${positions[index].x / 4}%`, top: `${positions[index].y / 2.2}%` }} initial={{ opacity: 0, scale: reduced ? 1 : .85 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: reduced ? 1 : .85 }} transition={{ duration: reduced ? 0 : .25 }}><span><Store size={12} /> Seller {offer.seller}</span><strong><AnimatedNumber value={Number(offer.price)} currency /></strong><span className="sr-only">Up to {offer.qty} units, round {offer.round}{offer.seller === bestSeller ? ", best offer" : ""}</span></motion.div>)}</AnimatePresence>
  </div>;
}
