"use client";
import { useState } from "react";
import { MailCheck } from "lucide-react";
import { AuthLink, AuthShell, Field, FormMessage, SubmitButton } from "../components/auth-ui";
import { request } from "../lib/client";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await request("/api/auth/password/forgot", { body: { email } }); setSent(true); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not send the email."); }
    finally { setBusy(false); }
  }
  return <AuthShell title="Reset your password." description="Enter the email you signed up with and we will send a link to choose a new password." footer={<AuthLink href="/login">Back to sign in</AuthLink>}>
    {sent ? <div className="auth-success"><MailCheck size={26} aria-hidden="true" /><h2>Check your inbox.</h2><p>If an account exists for <strong>{email}</strong>, a reset link is on its way. It works once and expires in an hour.</p><button className="button" type="button" onClick={() => setSent(false)}>Use a different email</button></div>
      : <form onSubmit={submit} aria-busy={busy}>{error && <FormMessage>{error}</FormMessage>}<Field label="Email" type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" required maxLength={254} /><SubmitButton busy={busy}>Send reset link</SubmitButton></form>}
  </AuthShell>;
}
