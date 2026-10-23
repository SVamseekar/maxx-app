"use client";

import { useEffect, useId, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronDown, CircleHelp, FlaskConical, Moon, Sun, X, ScanLine, Users, Store, Menu } from "lucide-react";

export { MotionProvider } from "./motion-system";
import { useMotionPreferences } from "./motion-system";
import AccountMenu from "./account-menu";
import { moneyLabel, useMoneyConfig } from "../lib/money";
import { useAuth } from "./auth";
import { loginPath } from "../lib/auth-helpers";

export function AppHeader() {
  const pathname = usePathname();
  const money = useMoneyConfig();
  const { user, status } = useAuth();
  const [light, setLight] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => { setMenuOpen(false); }, [pathname]);
  useEffect(() => {
    try {
      const saved = localStorage.getItem("maxx-theme");
      if (saved === "light") { setLight(true); document.documentElement.dataset.theme = "light"; }
    } catch { /* Theme still works when storage is unavailable. */ }
  }, []);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") { setMenuOpen(false); document.querySelector<HTMLButtonElement>(".mobile-menu-toggle")?.focus(); } };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [menuOpen]);
  function toggleTheme() {
    const next = !light; setLight(next);
    document.documentElement.dataset.theme = next ? "light" : "dark";
    try { localStorage.setItem("maxx-theme", next ? "light" : "dark"); } catch { /* Storage is optional. */ }
  }
  const links = [{ href: "/blocs", label: "Blocs", icon: Users, match: ["/blocs"] }, { href: "/scan", label: "Scan", icon: ScanLine, match: ["/scan"] }, { href: "/for-sellers", label: "Sell", icon: Store, match: ["/for-sellers", "/sell"] }, { href: "/how-it-works", label: "How it works", icon: CircleHelp, match: ["/how-it-works", "/trust", "/pricing", "/faq"] }, { href: "/judge", label: "Demo lab", icon: FlaskConical, match: ["/judge"] }];
  return <header className="app-header"><div className="nav-inner">
    <Link href="/" className="wordmark" aria-label="Maxx home">maxx<span className="brand-dot" /></Link>
    <nav id="main-navigation" className={menuOpen ? "navigation is-open" : "navigation"} aria-label="Main navigation">{links.map(link => {
      const selected = link.match.some(prefix => pathname === prefix || pathname.startsWith(prefix + "/"));
      return <Link key={link.href} href={link.href} className={selected ? "nav-link active" : "nav-link"} aria-current={selected ? "page" : undefined}>{link.label}{selected && <motion.span className="nav-indicator" layoutId="active-navigation" />}</Link>;
    })}{status === "ready" && !user && pathname !== "/login" && pathname !== "/signup" && <div className="nav-account"><Link className="button" href={loginPath(pathname)}>Sign in</Link><Link className="button primary" href={`/signup?next=${encodeURIComponent(pathname)}`}>Create account</Link></div>}</nav>
    <div className="nav-tools"><span className="demo-chip"><FlaskConical size={13} aria-hidden="true" /> {moneyLabel(money)}</span><button className="icon-button" onClick={toggleTheme} aria-label={light ? "Use dark theme" : "Use light theme"}>{light ? <Moon size={18} /> : <Sun size={18} />}</button><AccountMenu /><button type="button" className="icon-button mobile-menu-toggle" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button></div>
  </div></header>;
}

export function PageIntro({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return <div className="page-intro"><div><h1>{title.replace(/\.$/, "")}</h1><p>{description}</p></div>{children}</div>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "accent" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

/** Grid timing adapted from Beautiful UI LoadingState (MIT; see THIRD_PARTY_NOTICES.md). */
export function Working({ label, seconds }: { label: string; seconds?: number }) {
  const { reduced: reduce } = useMotionPreferences();
  return <div className="working" role="status"><span className="pixel-loader" aria-hidden="true">{Array.from({ length: 9 }, (_, i) => <span key={i} style={{ animationDelay: `${(i % 3 + Math.abs(Math.floor(i / 3) - 1)) * 90}ms`, animationPlayState: reduce ? "paused" : "running" }} />)}</span><span>{label}</span>{seconds !== undefined && <span className="elapsed">{seconds}s</span>}</div>;
}

export function Disclosure({ title, children, defaultOpen = false, className = "" }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean; className?: string }) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();
  const { reduced: reduce } = useMotionPreferences();
  return <div className={`disclosure ${className}`}><button type="button" className="disclosure-trigger" aria-expanded={open} aria-controls={contentId} onClick={() => setOpen(!open)}><span>{title}</span><motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: reduce ? 0 : .2 }}><ChevronDown size={16} aria-hidden="true" /></motion.span></button><AnimatePresence initial={false}>{open && <motion.div id={contentId} className="disclosure-body" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: reduce ? 0 : .22 }}><div>{children}</div></motion.div>}</AnimatePresence></div>;
}

export function ErrorNotice({ message, retry, dismiss }: { message: string; retry?: () => void; dismiss?: () => void }) {
  return <div className="error-notice" role="alert"><CircleHelp size={18} aria-hidden="true" /><p>{message}</p>{retry && <button className="quiet-button" onClick={retry}>Retry</button>}{dismiss && <button className="icon-button" onClick={dismiss} aria-label="Dismiss error"><X size={16} /></button>}</div>;
}

export function SellerWhy({ compact = false }: { compact?: boolean }) {
  return <Disclosure title={<><CircleHelp size={16} aria-hidden="true" /> Why would a seller offer less?</>} className="seller-why">
    <p>Sellers gain a group of interested buyers. Lower acquisition effort or clearing spare inventory can make a lower price worthwhile. Each seller still chooses its own profitable offer.</p>
    {!compact && <div className="seller-principles"><div><Check size={17} /><strong>Demand in one place</strong><p>A batch of buyers with a stated maximum.</p></div><div><Check size={17} /><strong>Profit stays protected</strong><p>Sellers can decline. A deal is never guaranteed.</p></div><div><Check size={17} /><strong>Real costs still count</strong><p>Shipping, returns and fees must fit the price.</p></div></div>}
    <p className="small muted">This is Maxx’s proposed merchant model. Sellers, stock and commitments in this demo are simulated; merchant adoption and payment guarantees are unverified.</p>
  </Disclosure>;
}

/** Kept so pages that render it need no change: the real footer lives in the layout, once. */
export function AppFooter() {
  return null;
}
