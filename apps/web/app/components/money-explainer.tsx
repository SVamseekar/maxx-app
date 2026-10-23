"use client";

import { useId, useState } from "react";
import { motion } from "motion/react";
import { ArrowDown, ArrowRight, Check, LockKeyhole, Undo2 } from "lucide-react";
import { AnimatedNumber, useMotionPreferences } from "./motion-system";

export default function MoneyExplainer() {
  const [outcome, setOutcome] = useState<"win" | "no-deal" | "leave">("win");
  const id = useId();
  const { reduced } = useMotionPreferences();
  const won = outcome === "win";
  return <div className="money-explainer">
    <div className="money-explainer-intro"><p className="section-label">Follow the money</p><h2>A hold is a reservation.</h2><p>Explore what happens to an example $180 hold. Your actual amounts are always shown before you confirm.</p><div className="money-outcomes" role="group" aria-label="Example payment outcome">{([{ value: "win", label: "You win" }, { value: "no-deal", label: "No deal" }, { value: "leave", label: "You leave early" }] as const).map(item => <button key={item.value} aria-pressed={outcome === item.value} onClick={() => setOutcome(item.value)}>{outcome === item.value && <Check size={14} />}{item.label}</button>)}</div></div>
    <div className="money-path" aria-live="polite"><div className="money-node"><LockKeyhole size={22} strokeWidth={1.4} /><span>Reserved at joining</span><strong>$180.00</strong><small>Not charged</small></div><div className="money-connector" aria-hidden="true"><ArrowRight size={22} /><ArrowDown size={22} /></div><motion.div layout={!reduced} className="money-node money-result" key={outcome} initial={{ y: reduced ? 0 : 10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: reduced ? 0 : .25 }}>{won ? <Check size={22} /> : <Undo2 size={22} />}<span>{won ? "Allocated price charged" : "Charged to you"}</span><strong><AnimatedNumber value={won ? 160 : 0} currency /></strong><small>{won ? "$20 of the hold released" : "$180 hold released"}</small></motion.div><p id={`${id}-note`} className="money-path-note">{won ? "The seller is paid after shipment, minus the platform fee." : outcome === "leave" ? "Leaving is available before the negotiation starts." : "No qualifying allocation means no charge."}<span>Illustrative example · payments depend on the app’s displayed mode.</span></p></div>
  </div>;
}
