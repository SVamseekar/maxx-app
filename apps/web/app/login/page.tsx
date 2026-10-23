"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Fingerprint, Mail, MailCheck } from "lucide-react";
import { AuthLink, AuthShell, Field, FormMessage, OAuthButtons, OrDivider, PasswordField, SubmitButton, useLeaveIfSignedIn } from "../components/auth-ui";
import { useAuth } from "../components/auth";
import { useAuthConfig } from "../components/auth-config";
import MfaStep from "../components/mfa-step";
import Turnstile from "../components/turnstile";
import { ApiError, request } from "../lib/client";
import { oauthErrorMessage, safeNext, type AccountUser } from "../lib/auth-helpers";
import { conditionalSupported, getPasskey, passkeyErrorMessage, passkeysSupported, type RequestJSON } from "../lib/webauthn";
import { useQuery } from "../lib/use-query";

type Step = "start" | "mfa" | "link-sent";
type PasskeyStart = { options: RequestJSON; challenge_id: string };

export default function Login() {
  const query = useQuery();
  const next = safeNext(query?.get("next"));
  const router = useRouter();
  const { setUser } = useAuth();
  const config = useAuthConfig();
  const [step, setStep] = useState<Step>("start");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [captchaNeeded, setCaptchaNeeded] = useState(false);
  const [captchaReset, setCaptchaReset] = useState(0);
  const [passkeys, setPasskeys] = useState(false);
  const autofill = useRef<AbortController | null>(null);
  const leaving = useLeaveIfSignedIn(next);
  // After a provider sign-in on an account with two-step verification, the API sends the person here
  // with a short-lived token; it is removed from the address bar straight away.
  useEffect(() => {
    const token = query?.get("mfa");
    if (!token) return;
    setMfaToken(token); setStep("mfa");
    const clean = new URL(window.location.href); clean.searchParams.delete("mfa");
    window.history.replaceState(null, "", clean.pathname + clean.search);
  }, [query]);
  const notice = query?.get("reset") ? "Your password was updated. Sign in with the new one." : null;
  const oauthError = oauthErrorMessage(query?.get("error"));

  const done = useCallback((user: AccountUser) => { setUser(user); router.replace(next); router.refresh(); }, [setUser, router, next]);
  const finishPasskey = useCallback(async (started: PasskeyStart, credential: unknown) => {
    const { user } = await request<{ user: AccountUser }>("/api/auth/passkeys/login/verify", { body: { challenge_id: started.challenge_id, credential } });
    done(user);
  }, [done]);

  // Offer saved passkeys inside the email field's autofill list, so one tap signs in.
  useEffect(() => {
    if (!passkeysSupported() || step !== "start") return;
    setPasskeys(true);
    let live = true;
    void (async () => {
      if (!(await conditionalSupported())) return;
      try {
        const started = await request<PasskeyStart>("/api/auth/passkeys/login/options", { body: {} });
        const controller = new AbortController(); autofill.current = controller;
        const credential = await getPasskey(started.options, { conditional: true, signal: controller.signal });
        if (live) await finishPasskey(started, credential);
      } catch { /* cancelled, unsupported or dismissed: the normal form is still there */ }
    })();
    return () => { live = false; autofill.current?.abort(); };
  }, [step, finishPasskey]);

  async function withPasskey() {
    autofill.current?.abort(); setBusy(true); setError("");
    try {
      const started = await request<PasskeyStart>("/api/auth/passkeys/login/options", { body: {} });
      await finishPasskey(started, await getPasskey(started.options));
    } catch (cause) {
      const text = cause instanceof ApiError ? cause.message : passkeyErrorMessage(cause);
      if (text) setError(text);
      setBusy(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await request<{ user?: AccountUser; mfa_required?: boolean; mfa_token?: string }>("/api/auth/login", { body: { email, password, captcha } });
      if (result.mfa_required && result.mfa_token) { setMfaToken(result.mfa_token); setStep("mfa"); setBusy(false); return; }
      done(result.user!);
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "captcha_required") setCaptchaNeeded(true);
      setError(cause instanceof Error ? cause.message : "Could not sign in.");
      setCaptcha(null); setCaptchaReset(value => value + 1); setBusy(false);
    }
  }

  async function emailLink() {
    if (!email) { setError("Enter your email above first, and we will send a sign-in link."); return; }
    setBusy(true); setError("");
    try { await request("/api/auth/login/link", { body: { email, captcha } }); setStep("link-sent"); }
    catch (cause) {
      if (cause instanceof ApiError && cause.code === "captcha_required") setCaptchaNeeded(true);
      setError(cause instanceof Error ? cause.message : "Could not send the link.");
      setCaptcha(null); setCaptchaReset(value => value + 1);
    } finally { setBusy(false); }
  }

  if (step === "mfa") return <AuthShell title="Check it’s you." description="Your account uses two-step verification."><MfaStep token={mfaToken} onDone={done} onCancel={() => { setStep("start"); setPassword(""); setError(""); }} /></AuthShell>;
  if (step === "link-sent") return <AuthShell title="Check your inbox." footer={<AuthLink href="/login">Back to sign in</AuthLink>}><div className="auth-success"><MailCheck size={26} aria-hidden="true" /><p>If <strong>{email}</strong> has a Maxx account, a sign-in link is on its way. It works once and expires in 15 minutes.</p>{config?.email_mode === "log" && <p className="dev-hint">Development mode: the link is printed in the API log.</p>}<button className="button" type="button" onClick={() => setStep("start")}>Use a different way</button></div></AuthShell>;

  return <AuthShell title="Welcome back." description="Sign in to join Blocs, set your maximum and follow your negotiations." footer={<>New to Maxx? <AuthLink href={`/signup?next=${encodeURIComponent(next)}`}>Create an account</AuthLink></>}>
    {notice && <FormMessage tone="success">{notice}</FormMessage>}
    {(oauthError || error) && <FormMessage>{oauthError ?? error}</FormMessage>}
    {passkeys && <button type="button" className="button primary passkey-button" disabled={busy || leaving} onClick={() => void withPasskey()}><Fingerprint size={18} aria-hidden="true" /> Sign in with a passkey</button>}
    <OAuthButtons next={next} />
    <OrDivider text={passkeys ? "or with your email" : "or use your email"} />
    <form onSubmit={submit} aria-busy={busy || leaving}>
      <Field label="Email" type="email" name="username" value={email} onChange={event => setEmail(event.target.value)} autoComplete="username webauthn" required maxLength={254} />
      <PasswordField value={password} onChange={setPassword} />
      {captchaNeeded && config?.captcha && <Turnstile siteKey={config.captcha.site_key} onToken={setCaptcha} resetSignal={captchaReset} />}
      <div className="auth-row"><AuthLink href="/forgot-password">Forgot your password?</AuthLink></div>
      <SubmitButton busy={busy}>Sign in</SubmitButton>
      <button type="button" className="button link-button" disabled={busy} onClick={() => void emailLink()}><Mail size={15} aria-hidden="true" /> Email me a sign-in link instead</button>
    </form>
  </AuthShell>;
}
