"use client";

import AuthShowcase from "./auth-showcase";
import { useQuery } from "../lib/use-query";
import Link from "next/link";
import { useEffect, useId, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { useAuthConfig } from "./auth-config";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "motion/react";
import { Check, Eye, EyeOff, Loader2, ShieldCheck, X } from "lucide-react";
import { passwordChecks, passwordStrength, STRENGTH_LABELS, safeNext } from "../lib/auth-helpers";
import { useAuth } from "./auth";
import { useMotionPreferences } from "./motion-system";

/** Shared account shell; credentials and provider flows remain in their route components. */
export function AuthShell({ title, description, children, footer }: { title: string; description?: string; children: ReactNode; footer?: ReactNode }) {
  const { reduced } = useMotionPreferences();
  const pathname = usePathname();
  const query = useQuery();
  const signup = pathname === "/signup";
  const entry = signup || pathname === "/login";
  const next = encodeURIComponent(safeNext(query?.get("next")));
  return <main id="main-content" className={`auth-page auth-editorial ${signup ? "is-signup" : "is-login"}`}>
    {entry ? <AuthShowcase key={pathname} signup={signup} /> : <aside className="auth-recovery-art"><ShieldCheck size={80} strokeWidth={.8} /><h2>A secure way<br />back to your account.</h2><p>Follow the steps here to verify it’s you. Your buying groups will be there when you return.</p><Link className="text-action" href="/login">Back to sign in</Link></aside>}
    <motion.section className="auth-card" aria-labelledby="auth-title" initial={reduced ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : .4 }}>
      {entry && <nav className="auth-entry-nav" aria-label="Account access"><Link href={`/login?next=${next}`} aria-current={!signup ? "page" : undefined}>Sign in</Link><Link href={`/signup?next=${next}`} aria-current={signup ? "page" : undefined}>Create account</Link></nav>}
      <span className="auth-welcome-mark" aria-hidden="true"><ShieldCheck size={22} strokeWidth={1.4} /></span>
      <h1 id="auth-title">{title.replace(/\.$/, "")}</h1>
      {description && <p className="auth-lede">{description}</p>}
      {children}
      {footer && <div className="auth-footer">{footer}</div>}
      <p className="auth-mode-note">Prototype · simulated commitments · no live payments</p>
    </motion.section>
  </main>;
}

export function Field({ label, hint, error, trailing, ...input }: { label: ReactNode; hint?: string; error?: string | null; trailing?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return <div className={`field ${error ? "has-error" : ""}`}>
    <label htmlFor={id}>{label}</label>
    <div className="field-control"><input id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-e` : hint ? `${id}-h` : undefined} {...input} />{trailing}</div>
    {error ? <p id={`${id}-e`} className="field-error" role="alert">{error}</p> : hint ? <p id={`${id}-h`} className="field-hint">{hint}</p> : null}
  </div>;
}

export function PasswordField({ label = "Password", value, onChange, email, meter = false, autoComplete = "current-password", error }: { label?: string; value: string; onChange: (value: string) => void; email?: string; meter?: boolean; autoComplete?: string; error?: string | null }) {
  const [shown, setShown] = useState(false);
  const strength = passwordStrength(value);
  return <div>
    <Field label={label} type={shown ? "text" : "password"} value={value} onChange={event => onChange(event.target.value)} autoComplete={autoComplete} required maxLength={128} error={error}
      trailing={<button type="button" className="field-toggle" onClick={() => setShown(!shown)} aria-label={shown ? "Hide password" : "Show password"} aria-pressed={shown}>{shown ? <EyeOff size={16} /> : <Eye size={16} />}</button>} />
    {meter && value.length > 0 && <div className="pw-meter">
      <div className="pw-bars" role="img" aria-label={`Password strength: ${STRENGTH_LABELS[strength]}`}>{[1, 2, 3, 4].map(n => <span key={n} className={n <= strength ? `on s${strength}` : ""} />)}</div>
      <span className="pw-label">{STRENGTH_LABELS[strength]}</span>
      <ul className="pw-checks">{passwordChecks(value, email).map(check => <li key={check.id} className={check.ok ? "ok" : ""}>{check.ok ? <Check size={12} aria-hidden="true" /> : <X size={12} aria-hidden="true" />}{check.label}</li>)}</ul>
    </div>}
  </div>;
}

export function SubmitButton({ busy, disabled = false, children }: { busy: boolean; disabled?: boolean; children: ReactNode }) {
  return <button className="button primary auth-submit" type="submit" disabled={busy || disabled} aria-busy={busy}>
    <span className="submit-content">{children}</span>
    <span className="submit-progress" aria-hidden="true"><Loader2 className={busy ? "spin" : undefined} size={18} /></span>
    {busy && <span className="sr-only"> — in progress</span>}
  </button>;
}

export function FormMessage({ tone = "error", children }: { tone?: "error" | "success" | "info"; children: ReactNode }) {
  return <div className={`form-message ${tone}`} role={tone === "error" ? "alert" : "status"}>{tone === "success" && <Check className="feedback-check" size={17} aria-hidden="true" />}<div>{children}</div></div>;
}

const GoogleMark = () => <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.7v3h3.9c2.3-2.1 3.5-5.2 3.5-8.9Z" /><path fill="#34A853" d="M12 24c3.2 0 6-1.1 7.9-2.9l-3.9-3c-1.1.7-2.5 1.2-4 1.2-3.1 0-5.7-2.1-6.6-4.9H1.4v3.1A12 12 0 0 0 12 24Z" /><path fill="#FBBC05" d="M5.4 14.4a7.2 7.2 0 0 1 0-4.8V6.5H1.4a12 12 0 0 0 0 11l4-3.1Z" /><path fill="#EA4335" d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.4 6.5l4 3.1C6.3 6.9 8.9 4.8 12 4.8Z" /></svg>;
const GitHubMark = () => <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M12 .5a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.2c0 .3.2.7.8.6A11.5 11.5 0 0 0 12 .5Z" /></svg>;
const MicrosoftMark = () => <svg width="18" height="18" viewBox="0 0 23 23" aria-hidden="true"><path fill="#f25022" d="M1 1h10v10H1z" /><path fill="#7fba00" d="M12 1h10v10H12z" /><path fill="#00a4ef" d="M1 12h10v10H1z" /><path fill="#ffb900" d="M12 12h10v10H12z" /></svg>;
const AppleMark = () => <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M16.4 12.6c0-2.6 2.1-3.8 2.2-3.9-1.2-1.7-3-2-3.7-2-1.6-.2-3.1.9-3.9.9-.8 0-2-.9-3.4-.9-1.7 0-3.3 1-4.2 2.6-1.8 3.1-.5 7.7 1.3 10.2.9 1.2 1.9 2.6 3.2 2.5 1.3-.1 1.8-.8 3.3-.8s2 .8 3.4.8c1.4 0 2.3-1.2 3.1-2.5 1-1.4 1.4-2.8 1.4-2.9-.1 0-2.7-1-2.7-4zM13.9 5c.7-.9 1.2-2.1 1-3.3-1 0-2.3.7-3 1.6-.7.8-1.2 2-1.1 3.2 1.2.1 2.4-.6 3.1-1.5z" /></svg>;
const MARKS: Record<string, () => ReactNode> = { google: GoogleMark, github: GitHubMark, microsoft: MicrosoftMark, apple: AppleMark };

/** Provider buttons are plain links: OAuth needs a full-page redirect, never a fetch. */
export function OAuthButtons({ next, verb = "Continue", link = false, linked = [], guard }: { next: string; verb?: string; link?: boolean; linked?: string[]; guard?: () => Promise<void> }) {
  const config = useAuthConfig();
  // Only providers this server is set up for are offered; the rest would be dead buttons.
  const offered = config?.oauth.filter(provider => provider.enabled) ?? [];
  if (offered.length === 0) return null;
  return <div className="oauth-buttons">
    {offered.map(provider => {
      const Mark = MARKS[provider.id];
      const isLinked = linked.includes(provider.id);
      const href = `/api/auth/oauth/${provider.id}/start?next=${encodeURIComponent(safeNext(next))}${link ? "&link=true" : ""}`;
      if (isLinked) return <span key={provider.id} className="button oauth-button is-disabled" aria-disabled="true">{Mark && <Mark />}{provider.name} linked</span>;
      return <a key={provider.id} className={`button oauth-button oauth-${provider.id}`} href={href} onClick={guard ? event => { event.preventDefault(); void guard().then(() => window.location.assign(href)).catch(() => {}); } : undefined}>{Mark && <Mark />}{verb} with {provider.name}</a>;
    })}
  </div>;
}

/** The divider only makes sense when provider buttons are shown above it. */
export function OrDivider({ text = "or use your email" }: { text?: string }) {
  const config = useAuthConfig();
  return config?.oauth.some(provider => provider.enabled) ? <div className="or-divider"><span>{text}</span></div> : null;
}

/** Signed-in people have no business on the sign-in screens. */
export function useLeaveIfSignedIn(next: string) {
  const { user, status } = useAuth();
  const router = useRouter();
  useEffect(() => { if (status === "ready" && user) router.replace(safeNext(next)); }, [status, user, next, router]);
  return status === "loading" || !!user;
}

export function AuthLink({ href, children }: { href: string; children: ReactNode }) {
  return <Link className="auth-link" href={href}>{children}</Link>;
}
