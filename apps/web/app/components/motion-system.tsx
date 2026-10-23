"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { animate, motion, MotionConfig, useMotionValue, useSpring, useTransform } from "motion/react";

const MotionPreferences = createContext({ reduced: false, paused: false, systemReduced: false, toggle: () => {} });

function subscribeToMotionPreference(notify: () => void) {
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  media.addEventListener("change", notify);
  return () => media.removeEventListener("change", notify);
}
const readMotionPreference = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const serverMotionPreference = () => false;

export function MotionProvider({ children }: { children: ReactNode }) {
  const systemReduced = useSyncExternalStore(subscribeToMotionPreference, readMotionPreference, serverMotionPreference);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    try { setPaused(localStorage.getItem("maxx-motion") === "paused"); } catch { /* Storage is optional. */ }
  }, []);
  const reduced = systemReduced || paused;
  useEffect(() => { document.documentElement.dataset.motion = reduced ? "reduced" : "full"; }, [reduced]);
  function toggle() {
    setPaused(value => {
      try { localStorage.setItem("maxx-motion", value ? "full" : "paused"); } catch { /* Storage is optional. */ }
      return !value;
    });
  }
  return <MotionPreferences.Provider value={{ reduced, paused, systemReduced, toggle }}><MotionConfig reducedMotion={reduced ? "always" : "user"} transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 330, damping: 32 }}>{children}</MotionConfig></MotionPreferences.Provider>;
}

export const useMotionPreferences = () => useContext(MotionPreferences);

/** Visual interpolation only: the accessible value always exposes the actual data. */
export function AnimatedNumber({ value, currency = false, className }: { value: number; currency?: boolean; className?: string }) {
  const { reduced } = useMotionPreferences();
  const number = useMotionValue(value);
  const format = (n: number) => currency ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n) : Math.round(n).toLocaleString("en-US");
  const display = useTransform(number, format);
  useEffect(() => {
    if (reduced) { number.jump(value); return; }
    const playback = animate(number, value, { type: "spring", stiffness: 170, damping: 26 });
    return () => playback.stop();
  }, [number, value, reduced]);
  return <span className={className}><span className="sr-only">{format(value)}</span><motion.span aria-hidden="true">{display}</motion.span></span>;
}

/** A bounded, pointer-driven depth effect. Controls remain in their original positions. */
export function DepthSurface({ children, active = true }: { children: ReactNode; active?: boolean }) {
  const { reduced } = useMotionPreferences();
  const x = useSpring(0, { stiffness: 140, damping: 24 });
  const y = useSpring(0, { stiffness: 140, damping: 24 });
  const lightX = useTransform(x, [-5, 5], ["20%", "80%"]);
  return <motion.div className="depth-surface" onPointerMove={event => {
    if (reduced || !active || event.pointerType !== "mouse") return;
    const rect = event.currentTarget.getBoundingClientRect();
    x.set(((event.clientX - rect.left) / rect.width - .5) * 10);
    y.set(((event.clientY - rect.top) / rect.height - .5) * -8);
  }} onPointerLeave={() => { x.set(0); y.set(0); }}>
    <motion.div className="depth-content" style={reduced || !active ? undefined : { rotateY: x, rotateX: y, transformPerspective: 1100 }}>{children}</motion.div>
    <motion.div className="depth-light" aria-hidden="true" style={{ left: reduced ? "50%" : lightX }} />
  </motion.div>;
}

/** Original product illustration, never a fabricated score, source, or progress report. */
export function ScanLens({ working = false }: { working?: boolean }) {
  const { reduced } = useMotionPreferences();
  const duration = reduced ? 0 : .8;
  return <div className={`scan-lens ${working ? "is-working" : ""}`} aria-hidden="true">
    <svg viewBox="0 0 400 210" fill="none">
      <defs><linearGradient id="lens-glass" x1="124" y1="24" x2="278" y2="198" gradientUnits="userSpaceOnUse"><stop stopColor="var(--accent)" stopOpacity=".18" /><stop offset="1" stopColor="var(--accent)" stopOpacity=".02" /></linearGradient><linearGradient id="lens-route"><stop stopColor="var(--accent)" stopOpacity=".1" /><stop offset=".5" stopColor="var(--accent)" /><stop offset="1" stopColor="var(--mint)" stopOpacity=".3" /></linearGradient></defs>
      <path d="M24 158H83Q97 158 97 144V101H300Q314 101 314 87V50H378" stroke="var(--line-strong)" strokeDasharray="3 5" />
      <motion.path d="M24 158H83Q97 158 97 144V101H300Q314 101 314 87V50H378" stroke="url(#lens-route)" strokeWidth="2" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration, delay: reduced ? 0 : .2 }} />
      <motion.g initial={{ opacity: 0, x: -12, rotate: -14 }} animate={{ opacity: 1, x: 0, rotate: -8 }} transition={{ duration }} style={{ transformOrigin: "115px 110px" }}>
        <rect x="50" y="40" width="127" height="145" rx="14" fill="var(--panel-raised)" stroke="var(--line-strong)" />
        <rect x="61" y="51" width="105" height="77" rx="8" fill="var(--base)" />
        <path d="M91 94V88a23 23 0 0146 0v6M90 91h7v21h-7a5 5 0 01-5-5v-11a5 5 0 015-5Zm46 0h-7v21h7a5 5 0 005-5v-11a5 5 0 00-5-5Z" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
        <path d="M64 143h69M64 155h46M64 167h82" stroke="var(--subtle)" strokeOpacity=".5" strokeWidth="4" strokeLinecap="round" />
      </motion.g>
      <motion.g initial={{ opacity: 0, x: 12, y: 10 }} animate={{ opacity: 1, x: 0, y: 0 }} transition={{ duration, delay: reduced ? 0 : .12 }}>
        <rect x="256" y="65" width="109" height="88" rx="13" fill="var(--panel-raised)" stroke="var(--line-strong)" />
        {[0, 1, 2].map(i => <g key={i}><rect x="269" y={80 + i * 23} width="12" height="12" rx="4" fill="var(--mint)" fillOpacity=".13" /><path d={`M272 ${86 + i * 23}l2 2 4-4`} stroke="var(--mint)" strokeWidth="1.3" strokeLinecap="round" /><path d={`M291 ${86 + i * 23}h${i === 1 ? 42 : 55}`} stroke="var(--subtle)" strokeOpacity=".5" strokeWidth="4" strokeLinecap="round" /></g>)}
      </motion.g>
      <motion.g initial={{ scale: .88, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration }} style={{ transformOrigin: "209px 103px" }}>
        <circle cx="209" cy="103" r="66" fill="var(--panel)" fillOpacity=".87" stroke="var(--line-strong)" />
        <circle cx="209" cy="103" r="60" fill="url(#lens-glass)" stroke="var(--accent)" strokeOpacity=".35" />
        <circle cx="209" cy="103" r="49" stroke="var(--accent)" strokeOpacity=".2" strokeDasharray="1 6" />
        <path d="M190 92v-7h8M220 85h8v7M228 113v8h-8M198 121h-8v-8" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" />
        <motion.path d="M193 103h32" stroke="var(--mint)" strokeWidth="2" strokeLinecap="round" animate={reduced ? {} : { y: [-10, 10, -10], opacity: [.5, 1, .5] }} transition={{ duration: 2.4, repeat: working ? Infinity : 1, ease: "easeInOut" }} />
        <path d="M256 151l23 23" stroke="var(--line-strong)" strokeWidth="13" strokeLinecap="round" /><path d="M256 151l23 23" stroke="var(--accent)" strokeOpacity=".35" strokeWidth="6" strokeLinecap="round" />
      </motion.g>
      <circle cx="24" cy="158" r="3" fill="var(--accent)" /><circle cx="378" cy="50" r="3" fill="var(--mint)" />
    </svg>
  </div>;
}
