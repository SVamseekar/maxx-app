"use client";
import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { useEffect } from "react";

import { useMotionPreferences } from "./motion-system";

export default function ScoreDial({ value }: { value: number | null }) {
  const { reduced: reduce } = useMotionPreferences();
  const safe = value === null ? 0 : Math.max(0, Math.min(100, value));
  const arc = "M 28 128 A 80 80 0 1 1 172 128";
  const count = useMotionValue(reduce ? safe : 0);
  const shown = useTransform(count, latest => Math.round(latest));
  useEffect(() => {
    if (reduce) { count.jump(safe); return; }
    const playback = animate(count, safe, { duration: .9, ease: [.2, .8, .2, 1] });
    return () => playback.stop();
  }, [count, safe, reduce]);
  return <div className="score-dial" role="img" aria-label={value === null ? "Money Score unavailable: insufficient evidence" : `Money Score ${value} out of 100. Price competitiveness, not a probability.`}>
    <svg viewBox="0 0 200 160" aria-hidden="true"><path d={arc} className="dial-track" pathLength="100" /><motion.path key={value ?? "unknown"} d={arc} className="dial-fill" pathLength="100" strokeDasharray={`${safe} 100`} initial={{ strokeDashoffset: safe }} animate={{ strokeDashoffset: 0 }} transition={{ duration: reduce ? 0 : .9, ease: [.2,.8,.2,1] }} /><motion.text x="100" y="89" className="dial-number" textAnchor="middle">{value === null ? "—" : shown}</motion.text><text x="100" y="111" className="dial-denominator" textAnchor="middle">/ 100</text><text x="24" y="149" className="dial-label">0</text><text x="155" y="149" className="dial-label">100</text></svg>
    <span>Money Score</span><small>Price competitiveness</small>
  </div>;
}
