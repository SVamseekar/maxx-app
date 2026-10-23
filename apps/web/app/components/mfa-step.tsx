"use client";

import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { request } from "../lib/client";
import type { AccountUser } from "../lib/auth-helpers";
import { Field, FormMessage, SubmitButton } from "./auth-ui";

/** The second step after a password or email link: a code from the authenticator, or a recovery code. */
export default function MfaStep({ token, onDone, onCancel }: { token: string; onDone: (user: AccountUser) => void; onCancel: () => void }) {
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const { user } = await request<{ user: AccountUser }>("/api/auth/login/mfa", { body: { mfa_token: token, code, remember: remember && !recovery } });
      onDone(user);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not verify the code.");
      setBusy(false);
      if (cause instanceof Error && /start the sign-in again|expired/i.test(cause.message)) setTimeout(onCancel, 1800);
    }
  }
  return <form onSubmit={submit} aria-busy={busy} className="mfa-step">
    <div className="mfa-lede"><ShieldCheck size={22} aria-hidden="true" /><p>{recovery ? "Enter one of your recovery codes. Each works once." : "Open your authenticator app and enter the 6-digit code for Maxx."}</p></div>
    {error && <FormMessage>{error}</FormMessage>}
    <Field key={recovery ? "recovery" : "code"} label={recovery ? "Recovery code" : "6-digit code"} value={code} onChange={event => setCode(event.target.value)} inputMode={recovery ? "text" : "numeric"} autoComplete="one-time-code" autoCapitalize="off" spellCheck={false} maxLength={recovery ? 14 : 7} required autoFocus placeholder={recovery ? "xxxxx-xxxxx" : "123456"} />
    {!recovery && <label className="checkbox remember"><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)} />Trust this browser for 30 days</label>}
    <SubmitButton busy={busy}>Verify and sign in</SubmitButton>
    <div className="auth-row"><button type="button" className="quiet-button" onClick={() => { setRecovery(!recovery); setCode(""); setError(""); }}>{recovery ? "Use my authenticator app" : "Use a recovery code"}</button><button type="button" className="quiet-button" onClick={onCancel}>Back</button></div>
  </form>;
}
