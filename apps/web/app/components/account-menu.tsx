"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, LayoutList, LogOut, Package, Receipt, Store, Settings, ShieldCheck, ShieldAlert } from "lucide-react";
import { useAuth } from "./auth";
import { useMotionPreferences } from "./motion-system";
import { initials, loginPath } from "../lib/auth-helpers";

export function Avatar({ name, url, size = 30 }: { name: string; url?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const style = { width: size, height: size, fontSize: Math.round(size * .4) };
  if (url && !failed) return <img className="avatar" src={url} alt="" referrerPolicy="no-referrer" style={style} onError={() => setFailed(true)} />;
  return <span className="avatar avatar-initials" aria-hidden="true" style={style}>{initials(name)}</span>;
}

export default function AccountMenu() {
  const { user, status, signOut } = useAuth();
  const { reduced } = useMotionPreferences();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const menu = useId();

  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => {
    if (!open) return;
    const away = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); root.current?.querySelector<HTMLElement>("button")?.focus(); }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        const items = [...root.current!.querySelectorAll<HTMLElement>("[role=menuitem]")];
        const index = items.indexOf(document.activeElement as HTMLElement);
        event.preventDefault();
        items[(index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
      }
    };
    document.addEventListener("pointerdown", away); document.addEventListener("keydown", keys);
    root.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", keys); };
  }, [open]);

  if (status === "loading") return <span className="account-skeleton" aria-hidden="true" />;
  if (!user) {
    if (pathname === "/login" || pathname === "/signup") return null;
    const here = pathname === "/login" || pathname === "/signup" ? "/" : pathname;
    return <div className="account-actions"><Link className="button quiet-link" href={loginPath(here)}>Sign in</Link><Link className="button primary account-cta" href={`/signup?next=${encodeURIComponent(here)}`}>Create account</Link></div>;
  }
  return <div className="account-menu" ref={root}>
    <button type="button" className="account-trigger" aria-haspopup="menu" aria-expanded={open} aria-controls={menu} aria-label={`Account menu for ${user.display_name}`} onClick={() => setOpen(!open)}>
      <Avatar name={user.display_name} url={user.avatar_url} /><span className="account-name">{user.display_name}</span><ChevronDown size={14} aria-hidden="true" />
    </button>
    <AnimatePresence>{open && <motion.div id={menu} role="menu" aria-label="Account" className="account-popover" initial={{ opacity: 0, y: reduced ? 0 : -6, scale: reduced ? 1 : .97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: reduced ? 0 : -6 }} transition={{ duration: reduced ? 0 : .16 }}>
      <div className="account-who"><Avatar name={user.display_name} url={user.avatar_url} size={38} /><div><strong>{user.display_name}</strong><span>{user.email}</span></div></div>
      <span className={`account-verify ${user.email_verified ? "ok" : ""}`}>{user.email_verified ? <><ShieldCheck size={13} aria-hidden="true" /> Email verified</> : <><ShieldAlert size={13} aria-hidden="true" /> Email not verified</>}</span>
      <Link role="menuitem" href="/my-blocs"><LayoutList size={15} aria-hidden="true" /> My Blocs</Link>
      <Link role="menuitem" href="/orders"><Package size={15} aria-hidden="true" /> Your orders</Link>
      <Link role="menuitem" href="/sell"><Store size={15} aria-hidden="true" /> Seller console</Link>
      <Link role="menuitem" href="/receipts"><Receipt size={15} aria-hidden="true" /> Receipts</Link>
      <Link role="menuitem" href="/account"><Settings size={15} aria-hidden="true" /> Account settings</Link>
      <button role="menuitem" type="button" onClick={async () => { setOpen(false); await signOut(); router.push("/"); router.refresh(); }}><LogOut size={15} aria-hidden="true" /> Sign out</button>
    </motion.div>}</AnimatePresence>
  </div>;
}
