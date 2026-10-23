"use client";
import { useState } from "react";
import { MailCheck } from "lucide-react";
import { AuthLink, AuthShell, Field, FormMessage, OAuthButtons, OrDivider, SubmitButton, useLeaveIfSignedIn } from "../components/auth-ui";
import { useAuthConfig } from "../components/auth-config";
import Turnstile from "../components/turnstile";
import { ApiError, request } from "../lib/client";
import { oauthErrorMessage, safeNext } from "../lib/auth-helpers";
import { useQuery } from "../lib/use-query";

export default function Signup() {
  const query = useQuery();
  const next = safeNext(query?.get("next"));
  const config = useAuthConfig();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [captchaReset, setCaptchaReset] = useState(0);
  const leaving = useLeaveIfSignedIn(next);
  const oauthError = oauthErrorMessage(query?.get("error"));
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await request("/api/auth/signup", { body: { email, display_name: name, captcha } });
      try { sessionStorage.setItem("maxx-next", next); } catch { /* optional */ }
      setSent(true);
    } catch (cause) {
      setError(cause instanceof ApiError || cause instanceof Error ? cause.message : "Could not start sign-up.");
      setCaptcha(null); setCaptchaReset(value => value + 1);
    } finally { setBusy(false); }
  }
  if (sent) return <AuthShell title="Check your inbox." footer={<AuthLink href="/login">Already confirmed? Sign in</AuthLink>}>
    <div className="auth-success" role="status">
      <MailCheck size={26} aria-hidden="true" />
      <p>We sent a link to <strong>{email}</strong>. Open it to confirm your address and choose how you sign in. It works once and expires in 24 hours.</p>
      {config?.email_mode === "log" && <p className="dev-hint">Development mode: the link is printed in the API log (or run <code>make dev-account</code>).</p>}
      <p className="small muted">Nothing is created until you open the link. Not there? Check spam, or try again with the same address.</p>
      <button className="button" type="button" onClick={() => { setSent(false); setCaptcha(null); setCaptchaReset(value => value + 1); }}>Use a different email</button>
    </div>
  </AuthShell>;
  return <AuthShell title="Create your account." description="Find your people. Set your price. Start with a free account." footer={<>Already have an account? <AuthLink href={`/login?next=${encodeURIComponent(next)}`}>Sign in</AuthLink></>}>
    {(oauthError || error) && <FormMessage>{oauthError ?? error}</FormMessage>}
    <OAuthButtons next={next} verb="Sign up" />
    <OrDivider />
    <form onSubmit={submit} aria-busy={busy || leaving}>
      <Field label="Name" hint="Optional. This is how you appear in your account." value={name} onChange={event => setName(event.target.value)} autoComplete="name" maxLength={80} />
      <Field label="Email" type="email" name="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" required maxLength={254} />
      {config?.captcha && <Turnstile siteKey={config.captcha.site_key} onToken={setCaptcha} resetSignal={captchaReset} />}
      <SubmitButton busy={busy}>Continue with email</SubmitButton>
      <p className="auth-fine">We’ll email a secure link. Confirm your address, then choose a passkey or password.</p>
    </form>
  </AuthShell>;
}
