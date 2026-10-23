"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { useMotionPreferences } from "./motion-system";

/** Cursor-follow light for glass surfaces. One passive listener; CSS does the painting. */
const SPOTLIGHT_SELECTOR = ".bloc-card,.verdict-panel,.commit-panel,.negotiation-chat,.create-bloc,.room-metrics,.upload-controls,.group-panel";

export function AmbientEffects() {
  useEffect(() => {
    let frame = 0;
    function move(event: PointerEvent) {
      if (event.pointerType !== "mouse" || document.documentElement.dataset.motion === "reduced") return;
      const { clientX, clientY, target } = event;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const surface = (target as Element | null)?.closest?.<HTMLElement>(SPOTLIGHT_SELECTOR);
        if (!surface) return;
        const rect = surface.getBoundingClientRect();
        surface.style.setProperty("--mx", `${clientX - rect.left}px`);
        surface.style.setProperty("--my", `${clientY - rect.top}px`);
      });
    }
    document.addEventListener("pointermove", move, { passive: true });
    return () => { document.removeEventListener("pointermove", move); cancelAnimationFrame(frame); };
  }, []);
  return <div className="aurora" aria-hidden="true"><span className="aurora-blob a" /><span className="aurora-blob b" /><span className="aurora-grid" /></div>;
}

/** Headline that resolves word by word out of a soft blur. The text stays plain for assistive tech. */
export function RevealText({ lines }: { lines: string[] }) {
  let index = 0;
  return <>{lines.map((line, lineIndex) => <Fragment key={line}>
    {lineIndex > 0 && <br />}
    {line.split(" ").map((word, wordIndex) => <Fragment key={`${word}-${wordIndex}`}>
      {wordIndex > 0 && " "}<span className="reveal-word" style={{ animationDelay: `${index++ * 70}ms` }}>{word}</span>
    </Fragment>)}
  </Fragment>)}</>;
}

export function ShimmerText({ children }: { children: string }) {
  return <span className="shimmer-text">{children}</span>;
}

/**
 * Streaming reveal adapted from Beautiful UI StreamText (MIT; see THIRD_PARTY_NOTICES.md).
 * Visible characters are decorative; the full string is always exposed to assistive tech.
 */
export function StreamText({ text, charsPerTick = 2, tickMs = 12, blurTail = 6, onProgress, className }: { text: string; charsPerTick?: number; tickMs?: number; blurTail?: number; onProgress?: () => void; className?: string }) {
  const { reduced } = useMotionPreferences();
  const [count, setCount] = useState(reduced ? text.length : 0);
  const progress = useRef(onProgress);
  useEffect(() => { progress.current = onProgress; });
  useEffect(() => {
    if (reduced) { setCount(text.length); return; }
    let shown = 0;
    setCount(0);
    const timer = setInterval(() => {
      shown = Math.min(shown + charsPerTick, text.length);
      setCount(shown);
      progress.current?.();
      if (shown >= text.length) clearInterval(timer);
    }, tickMs);
    return () => clearInterval(timer);
  }, [text, charsPerTick, tickMs, reduced]);
  const streaming = count < text.length;
  const split = streaming ? Math.max(0, count - blurTail) : count;
  return <span className={className}>
    <span className="sr-only">{text}</span>
    <span aria-hidden="true">{text.slice(0, split)}{split < count && <span className="stream-tail">{text.slice(split, count)}</span>}{streaming && <span className="stream-caret" />}</span>
  </span>;
}
