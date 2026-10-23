"use client";

import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Fingerprint, KeyRound, Mail, ShieldCheck, Smartphone, X } from "lucide-react";
import { ApiError, request } from "../lib/client";
import { getPasskey, passkeyErrorMessage, passkeysSupported, type RequestJSON } from "../lib/webauthn";
import { Field, FormMessage, PasswordField, SubmitButton } from "./auth-ui";
import { useMotionPreferences } from "./motion-system";

type Methods = { password: boolean; totp: boolean; passkey: boolean; email_code: boolean };
type Method = keyof Methods;
type Secure = <T>(task: () => Promise<T>) => Promise<T>;

const ReauthContext = createContext<{ secure: Secure }>({ secure: task => task() });

/**
 * Wrap an action that needs a recent identity check. If the server says "confirm it's you", a
 * dialog asks (passkey, authenticator code, password or emailed code), then the action is retried.
 */
export const useSecure = (): Secure => useContext(ReauthContext).secure;

export function ReauthProvider({ children }: { children: ReactNode }) {
  const [waiting, setWaiting] = useState<((ok: boolean) => void) | null>(null);
  const ask = useCallback(() => new Promise<boolean>(resolve => setWaiting(() => resolve)), []);
  const secure = useCallback<Secure>(async task => {
    try { return await task(); }
    catch (cause) {
      if (!(cause instanceof ApiError) || cause.code !== "reauth_required") throw cause;
      if (!(await ask())) throw new ApiError("Cancelled.", 0, "reauth_cancelled");
      return task();
    }
  }, [ask]);
  const value = useMemo(() => ({ secure }), [secure]);
  return <ReauthContext.Provider value={value}>{children}<AnimatePresence>{waiting && <ReauthDialog key="reauth" onDone={ok => { waiting(ok); setWaiting(null); }} />}</AnimatePresence></ReauthContext.Provider>;
}

const LABELS: Record<Method, { label: string; icon: typeof KeyRound }> = {
  passkey: { label: "Passkey", icon: Fingerprint },
  totp: { label: "Authenticator", icon: Smartphone },
  password: { label: "Password", icon: KeyRound },
  email_code: { label: "Email code", icon: Mail },
};
const ORDER: Method[] = ["passkey", "totp", "password", "email_code"];

function ReauthDialog({ onDone }: { onDone: (ok: boolean) => void }) {
  const { reduced } = useMotionPreferences();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const [methods, setMethods] = useState<Methods | null>(null);
  const [method, setMethod] = useState<Method | null>(null);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    void request<Methods>("/api/auth/reauth/methods").then(found => {
      const usable = { ...found, passkey: found.passkey && passkeysSupported() };
      setMethods(usable);
      setMethod(ORDER.find(m => usable[m]) ?? "email_code");
    }).catch(() => { setMethods({ password: false, totp: false, passkey: false, email_code: true }); setMethod("email_code"); });
    return () => { document.body.style.overflow = ""; opener?.focus?.(); };
  }, []);
  useEffect(() => { panel.current?.querySelector<HTMLElement>("input,button[data-primary]")?.focus(); }, [method, methods]);

  function keys(event: React.KeyboardEvent) {
    if (event.key === "Escape") { event.stopPropagation(); onDone(false); return; }
    if (event.key !== "Tab" || !panel.current) return;
    const items = [...panel.current.querySelectorAll<HTMLElement>("button:not([disabled]),input,a[href]")].filter(el => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0], last = items.at(-1)!;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  async function confirm(body: Record<string, unknown>) {
    setBusy(true); setError("");
    try { await request("/api/auth/reauth", { body }); onDone(true); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not confirm."); setBusy(false); }
  }
  async function viaPasskey() {
    setBusy(true); setError("");
    try {
      const started = await request<{ options: RequestJSON; challenge_id: string }>("/api/auth/reauth/passkey/options", { body: {} });
      const credential = await getPasskey(started.options);
      await request("/api/auth/reauth", { body: { method: "passkey", challenge_id: started.challenge_id, credential } });
      onDone(true);
    } catch (cause) {
      const text = cause instanceof ApiError ? cause.message : passkeyErrorMessage(cause);
      if (text) setError(text);
      setBusy(false);
    }
  }
  async function sendCode() {
    setBusy(true); setError("");
    try { await request("/api/auth/reauth/email/send", { body: {} }); setSent(true); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not send the code."); }
    finally { setBusy(false); }
  }

  const available = methods ? ORDER.filter(m => methods[m]) : [];
  return <motion.div className="dialog-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: reduced ? 0 : .15 }} onPointerDown={event => { if (event.target === event.currentTarget) onDone(false); }}>
    <motion.div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} className="dialog" onKeyDown={keys} initial={{ opacity: 0, y: reduced ? 0 : 14, scale: reduced ? 1 : .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: reduced ? 0 : 10 }} transition={{ duration: reduced ? 0 : .2, ease: [.2, .8, .2, 1] }}>
      <button type="button" className="icon-button dialog-close" aria-label="Cancel" onClick={() => onDone(false)}><X size={16} /></button>
      <div className="dialog-head"><ShieldCheck size={22} aria-hidden="true" /><div><h2 id={titleId}>Confirm it’s you</h2><p>This change affects how you sign in, so we check again first.</p></div></div>
      {!methods && <p className="muted small">Checking your options…</p>}
      {methods && available.length > 1 && <div className="dialog-tabs" role="tablist" aria-label="How to confirm">{available.map(item => { const { label, icon: Icon } = LABELS[item]; return <button key={item} role="tab" type="button" aria-selected={method === item} className={method === item ? "is-selected" : ""} onClick={() => { setMethod(item); setError(""); setValue(""); }}><Icon size={14} aria-hidden="true" />{label}</button>; })}</div>}
      {error && <FormMessage>{error}</FormMessage>}
      {method === "passkey" && <div className="dialog-body"><p>Use the passkey on this device. You may be asked for your fingerprint, face or screen lock.</p><button type="button" data-primary className="button primary auth-submit" disabled={busy} onClick={() => void viaPasskey()}><Fingerprint size={16} aria-hidden="true" /> Use passkey</button></div>}
      {method === "password" && <form className="dialog-body" onSubmit={event => { event.preventDefault(); void confirm({ method: "password", password: value }); }}><PasswordField label="Your password" value={value} onChange={setValue} /><SubmitButton busy={busy}>Confirm</SubmitButton></form>}
      {method === "totp" && <form className="dialog-body" onSubmit={event => { event.preventDefault(); void confirm({ method: "totp", code: value }); }}><Field label="Code from your authenticator app" inputMode="numeric" autoComplete="one-time-code" value={value} onChange={event => setValue(event.target.value)} maxLength={14} required hint="Or enter one of your recovery codes." /><SubmitButton busy={busy}>Confirm</SubmitButton></form>}
      {method === "email_code" && <div className="dialog-body">{!sent ? <><p>We will email a six-digit code to your address on file.</p><button type="button" data-primary className="button primary auth-submit" disabled={busy} onClick={() => void sendCode()}>Email me a code</button></> : <form className="dialog-body" onSubmit={event => { event.preventDefault(); void confirm({ method: "email_code", code: value }); }}><Field label="Six-digit code" inputMode="numeric" autoComplete="one-time-code" value={value} onChange={event => setValue(event.target.value)} maxLength={6} required hint="It expires in 10 minutes." /><SubmitButton busy={busy}>Confirm</SubmitButton></form>}</div>}
    </motion.div>
  </motion.div>;
}

