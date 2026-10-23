"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Fingerprint, KeyRound, MailWarning, X } from "lucide-react";
import { useAuth } from "./auth";
import { request } from "../lib/client";
import { passkeysSupported } from "../lib/webauthn";

type Kind = "verify" | "credential" | "passkey";
const KEYS: Record<Kind, string> = { verify: "maxx-verify-dismissed", credential: "maxx-credential-dismissed", passkey: "maxx-passkey-dismissed" };
const HIDDEN_ON = ["/verify-email", "/complete-signup", "/signin-link", "/login", "/signup", "/account"];

/** One gentle, dismissible reminder at a time, most important first. */
export default function VerifyBanner() {
  const { user } = useAuth();
  const pathname = usePathname();
  const [dismissed, setDismissed] = useState<Record<string, boolean>>({});
  const [supported, setSupported] = useState(false);
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  useEffect(() => {
    setSupported(passkeysSupported());
    const found: Record<string, boolean> = {};
    for (const kind of Object.keys(KEYS) as Kind[]) {
      try { found[kind] = (kind === "passkey" ? localStorage : sessionStorage).getItem(KEYS[kind]) === "1"; } catch { found[kind] = false; }
    }
    setDismissed(found);
  }, []);
  if (!user || HIDDEN_ON.includes(pathname)) return null;
  const kind: Kind | null = !user.email_verified ? "verify" : user.needs_credential ? "credential" : supported && user.passkeys === 0 ? "passkey" : null;
  if (!kind || dismissed[kind]) return null;
  function dismiss() {
    setDismissed(value => ({ ...value, [kind!]: true }));
    try { (kind === "passkey" ? localStorage : sessionStorage).setItem(KEYS[kind!], "1"); } catch { /* optional */ }
  }
  async function resend() {
    setState("sending");
    try { await request("/api/auth/email/resend", { body: {} }); setState("sent"); } catch { setState("error"); }
  }
  return <div className={`verify-banner ${kind === "passkey" ? "is-calm" : ""}`} role="status">
    {kind === "verify" && <><MailWarning size={16} aria-hidden="true" /><span>Confirm your email <strong>{user.email}</strong> to secure your account.</span><button type="button" className="quiet-button" onClick={() => void resend()} disabled={state === "sending" || state === "sent"}>{state === "sent" ? "Link sent" : state === "error" ? "Try again" : "Resend link"}</button></>}
    {kind === "credential" && <><KeyRound size={16} aria-hidden="true" /><span>Add a passkey or password so you can always sign back in.</span><Link className="quiet-button button" href="/account#passkeys-h">Set it up</Link></>}
    {kind === "passkey" && <><Fingerprint size={16} aria-hidden="true" /><span>Sign in faster and safer with a <strong>passkey</strong>: your fingerprint, face or screen lock.</span><Link className="quiet-button button" href="/account#passkeys-h">Add a passkey</Link></>}
    <button type="button" className="icon-button" aria-label="Dismiss reminder" onClick={dismiss}><X size={15} /></button>
  </div>;
}
