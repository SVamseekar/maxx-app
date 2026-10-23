"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { animate } from "motion/react";
import { useMotionPreferences } from "./motion-system";

/** Marketing blocks that rise into view. Scoped to `.info-page` so app screens never hide content. */
const REVEAL = ".info-page :is(.band-head,.feature-grid>article,.steps-grid>li,.table-wrap,.callout,.faq-list>details,.cta-row,.seller-editorial,.scan-editorial,.editorial-image,.fee-calculator,[data-reveal])";

/** The provider briefly reports "full" while hydrating, so read the device and stored settings directly. */
function motionIsReduced() {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches || localStorage.getItem("maxx-motion") === "paused" || document.documentElement.dataset.motion === "reduced";
  } catch { return document.documentElement.dataset.motion === "reduced"; }
}

/**
 * Scroll reveal for explanatory pages.
 * Content below the fold is hidden only after hydration, so it stays readable without script,
 * and nothing is hidden at all when motion is reduced or paused.
 */
export default function PageEffects() {
  const pathname = usePathname();

  useEffect(() => {
    const nodes = [...document.querySelectorAll<HTMLElement>(REVEAL)].filter(node => !node.parentElement?.closest(REVEAL));
    if (!nodes.length) return;
    if (motionIsReduced() || !("IntersectionObserver" in window)) {
      nodes.forEach(node => node.classList.add("rv-in"));
      return;
    }
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("rv-in");
        observer.unobserve(entry.target);
      }
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
    const viewport = window.innerHeight;
    for (const node of nodes) {
      const { top, bottom } = node.getBoundingClientRect();
      if (bottom <= 0 || top < viewport * 0.92) { node.classList.add("rv-in"); continue; }
      const siblings = node.parentElement ? [...node.parentElement.children].filter(child => child.matches(REVEAL)) : [node];
      node.style.setProperty("--rv-delay", `${Math.min(siblings.indexOf(node), 5) * 70}ms`);
      node.classList.add("rv");
      observer.observe(node);
    }
    return () => observer.disconnect();
  }, [pathname]);

  return null;
}

/** Counts up once when scrolled into view. The final value is always in the markup and read aloud. */
export function CountUp({ value, prefix = "", suffix = "" }: { value: number; prefix?: string; suffix?: string }) {
  const { reduced } = useMotionPreferences();
  const [node, setNode] = useState<HTMLSpanElement | null>(null);
  const [shown, setShown] = useState(value);
  useEffect(() => {
    if (reduced || !node || !("IntersectionObserver" in window)) return;
    let playback: ReturnType<typeof animate> | undefined;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry?.isIntersecting) return;
      observer.disconnect();
      playback = animate(0, value, { duration: 1.4, ease: [0.2, 0.8, 0.2, 1], onUpdate: latest => setShown(Math.round(latest)) });
    }, { threshold: 0.6 });
    observer.observe(node);
    return () => { observer.disconnect(); playback?.stop(); };
  }, [node, reduced, value]);
  return <><span className="sr-only">{prefix}{value}{suffix}</span><span ref={setNode} aria-hidden="true">{prefix}{shown.toLocaleString("en-US")}{suffix}</span></>;
}
