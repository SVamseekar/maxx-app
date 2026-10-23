"use client";
import { useConfirm } from "./confirm-provider";

import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import { AlertTriangle, Check, Copy, Download, Fingerprint, History, Pencil, ShieldCheck, Smartphone, Trash2, X } from "lucide-react";
import { Badge, ErrorNotice, Working } from "./ui";
import { Field, FormMessage, SubmitButton } from "./auth-ui";
import { useSecure } from "./reauth";
import { useMotionPreferences } from "./motion-system";
import { ApiError, request } from "../lib/client";
import { describeAgent, relativeTime, type AccountUser } from "../lib/auth-helpers";
import { createPasskey, passkeyErrorMessage, passkeysSupported, type CreationJSON } from "../lib/webauthn";
import { useAction } from "../lib/use-action";

export type Overview = {
  totp_enabled: boolean; recovery_codes_left: number; trusted_devices: number;
  passkeys: { id: string; name: string; created_at: number; last_used_at: number | null; synced: boolean }[];
  checkup: { score: number; items: { id: string; label: string; done: boolean; weight: number }[] };
};

export function useOverview(user: AccountUser | null) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try { setOverview(await request<Overview>("/api/auth/security")); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Cannot load your security settings."); }
  }, []);
  useEffect(() => { if (user) void refresh(); }, [user?.id, refresh]); // eslint-disable-line react-hooks/exhaustive-deps
  return { overview, error, refresh };
}

// ---- checkup --------------------------------------------------------------------------------

const ADVICE: Record<string, { cta: string; anchor: string }> = {
  email: { cta: "Confirm email", anchor: "#email-h" },
  signin: { cta: "Add a sign-in method", anchor: "#methods-h" },
  passkey: { cta: "Add a passkey", anchor: "#passkeys-h" },
  mfa: { cta: "Turn on two-step", anchor: "#twostep-h" },
};

export function SecurityCheckup({ overview }: { overview: Overview | null }) {
  const { reduced } = useMotionPreferences();
  const score = overview?.checkup.score ?? 0;
  const radius = 34, circumference = 2 * Math.PI * radius;
  const tone = score >= 100 ? "var(--mint)" : score >= 60 ? "var(--accent)" : "var(--warn)";
  return <section className="checkup" aria-labelledby="checkup-h">
    <div className="checkup-ring" role="img" aria-label={`Security score ${score} out of 100`}>
      <svg viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="40" r={radius} className="ring-track" /><motion.circle cx="40" cy="40" r={radius} className="ring-fill" stroke={tone} strokeDasharray={circumference} initial={{ strokeDashoffset: reduced ? circumference * (1 - score / 100) : circumference }} animate={{ strokeDashoffset: circumference * (1 - score / 100) }} transition={{ duration: reduced ? 0 : .9, ease: [.2, .8, .2, 1] }} /></svg>
      <strong>{score}</strong>
    </div>
    <div className="checkup-body">
      <h2 id="checkup-h">Security checkup</h2>
      <p>{score >= 100 ? "Your account is well protected." : "A few steps make your account much harder to take over."}</p>
      <ul>{overview?.checkup.items.map(item => <li key={item.id} className={item.done ? "done" : ""}>{item.done ? <Check size={14} aria-hidden="true" /> : <X size={14} aria-hidden="true" />}<span>{item.label}</span>{!item.done && ADVICE[item.id] && <a href={ADVICE[item.id].anchor}>{ADVICE[item.id].cta}</a>}</li>)}</ul>
    </div>
  </section>;
}

// ---- passkeys -------------------------------------------------------------------------------

export function PasskeysSection({ overview, refresh }: { overview: Overview | null; refresh: () => Promise<void> }) {
  const confirmAction = useConfirm();
  const secure = useSecure();
  const add = useAction(), manage = useAction();
  const [renaming, setRenaming] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [supported, setSupported] = useState(true);
  useEffect(() => { setSupported(passkeysSupported()); }, []);
  async function addPasskey() {
    await add.run(async () => {
      try {
        await secure(async () => {
          const started = await request<{ options: CreationJSON; challenge_id: string }>("/api/auth/passkeys/register/options", { body: {} });
          const credential = await createPasskey(started.options);
          await request("/api/auth/passkeys/register/verify", { body: { challenge_id: started.challenge_id, credential, name: describeAgent(navigator.userAgent) } });
        });
      } catch (cause) {
        if (cause instanceof ApiError) throw cause;
        const text = passkeyErrorMessage(cause);
        if (text) throw new Error(text, { cause });
        return;
      }
      await refresh();
      return "Passkey added. You can now sign in with it.";
    });
  }
  return <section className="account-section" aria-labelledby="passkeys-h">
    <div className="account-section-head"><Fingerprint size={18} aria-hidden="true" /><div><h2 id="passkeys-h">Passkeys <Badge tone="good">Recommended</Badge></h2><p>Sign in with your fingerprint, face or screen lock. Passkeys can’t be phished or guessed, and they replace both a password and a code.</p></div></div>
    <ul className="passkey-list">{overview?.passkeys.map(key => <li key={key.id}>
      {renaming === key.id ? <form onSubmit={event => { event.preventDefault(); void manage.run(async () => { await request(`/api/auth/passkeys/${key.id}`, { method: "PATCH", body: { name } }); setRenaming(null); await refresh(); return "Renamed."; }); }}><Field label="Name" value={name} onChange={event => setName(event.target.value)} maxLength={80} required autoFocus /><div className="auth-row"><SubmitButton busy={manage.busy}>Save</SubmitButton><button type="button" className="quiet-button" onClick={() => setRenaming(null)}>Cancel</button></div></form>
        : <><div><strong>{key.name}</strong><span>Added {relativeTime(key.created_at)} · {key.last_used_at ? `last used ${relativeTime(key.last_used_at)}` : "not used yet"}{key.synced ? " · synced across your devices" : ""}</span></div>
          <div className="row-actions"><button type="button" className="icon-button" aria-label={`Rename ${key.name}`} onClick={() => { setRenaming(key.id); setName(key.name); }}><Pencil size={15} /></button>
            <button type="button" className="icon-button" aria-label={`Remove ${key.name}`} onClick={async () => { if (!await confirmAction(`Remove “${key.name}”? You will no longer be able to sign in with it.`)) return; void manage.run(async () => { await secure(() => request(`/api/auth/passkeys/${key.id}`, { method: "DELETE" })); await refresh(); return "Passkey removed."; }); }}><Trash2 size={15} /></button></div></>}
    </li>)}</ul>
    {overview && overview.passkeys.length === 0 && <p className="muted small">No passkeys yet.</p>}
    {add.message && <FormMessage tone={add.message.tone}>{add.message.text}</FormMessage>}
    {manage.message && <FormMessage tone={manage.message.tone}>{manage.message.text}</FormMessage>}
    {supported ? <button type="button" className="button primary" disabled={add.busy} onClick={() => void addPasskey()}><Fingerprint size={16} aria-hidden="true" /> Add a passkey</button> : <p className="muted small">This browser can’t create passkeys. Open Maxx in a recent Chrome, Safari, Edge or Firefox to add one.</p>}
  </section>;
}

// ---- two-step verification ------------------------------------------------------------------

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = `Maxx recovery codes\nEach code works once.\n\n${codes.join("\n")}\n`;
  function download() {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const link = document.createElement("a"); link.href = url; link.download = "maxx-recovery-codes.txt"; link.click(); URL.revokeObjectURL(url);
  }
  return <div className="recovery" role="group" aria-label="Recovery codes">
    <h3><AlertTriangle size={16} aria-hidden="true" /> Save your recovery codes</h3>
    <p>If you lose your phone, these are the only way back in. Each works once. They are shown now and never again.</p>
    <ul>{codes.map(code => <li key={code}><code>{code}</code></li>)}</ul>
    <div className="auth-row"><button type="button" className="button" onClick={async () => { try { await navigator.clipboard.writeText(text); setCopied(true); } catch { setCopied(false); } }}><Copy size={14} aria-hidden="true" /> {copied ? "Copied" : "Copy"}</button><button type="button" className="button" onClick={download}><Download size={14} aria-hidden="true" /> Download</button></div>
    <label className="checkbox"><input type="checkbox" checked={saved} onChange={event => setSaved(event.target.checked)} />I have saved these codes somewhere safe</label>
    <button type="button" className="button primary" disabled={!saved} onClick={onDone}>Done</button>
  </div>;
}

export function TwoStepSection({ user, overview, refresh }: { user: AccountUser; overview: Overview | null; refresh: () => Promise<void> }) {
  const secure = useSecure();
  const setup = useAction(), confirm = useAction(), manage = useAction();
  const [seed, setSeed] = useState<{ secret: string; uri: string; qr: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [mode, setMode] = useState<null | "disable" | "regenerate">(null);
  const [manageCode, setManageCode] = useState("");
  async function begin() {
    await setup.run(async () => {
      const result = await secure(() => request<{ secret: string; otpauth_uri: string }>("/api/auth/mfa/totp/setup", { body: {} }));
      const QRCode = (await import("qrcode")).default;
      const qr = await QRCode.toDataURL(result.otpauth_uri, { margin: 1, width: 200, errorCorrectionLevel: "M", color: { dark: "#0b1020", light: "#ffffff" } });
      setSeed({ secret: result.secret, uri: result.otpauth_uri, qr });
    });
  }
  const spaced = (value: string) => value.replace(/(.{4})/g, "$1 ").trim();
  return <section className="account-section" aria-labelledby="twostep-h">
    <div className="account-section-head"><Smartphone size={18} aria-hidden="true" /><div><h2 id="twostep-h">Two-step verification</h2><p>{user.totp_enabled ? "On. Signing in with a password also needs a code from your authenticator app." : "Add a code from an authenticator app (1Password, Google Authenticator, Authy…) so a stolen password alone is not enough."}</p></div></div>
    {codes && <RecoveryCodes codes={codes} onDone={() => { setCodes(null); void refresh(); }} />}
    {!codes && !user.totp_enabled && !seed && <><button type="button" className="button" disabled={setup.busy} onClick={() => void begin()}>Set up authenticator app</button>{setup.message && <FormMessage tone={setup.message.tone}>{setup.message.text}</FormMessage>}</>}
    {!codes && !user.totp_enabled && seed && <form className="totp-setup" onSubmit={event => { event.preventDefault(); void confirm.run(async () => { const result = await secure(() => request<{ recovery_codes: string[] }>("/api/auth/mfa/totp/enable", { body: { code } })); setSeed(null); setCode(""); setCodes(result.recovery_codes); }); }}>
      <ol className="steps"><li>Scan this with your authenticator app, or enter the key by hand.</li></ol>
      <div className="qr-row"><img src={seed.qr} alt="QR code for your authenticator app" width={176} height={176} /><div><span className="small muted">Can’t scan? Enter this key</span><code className="seed">{spaced(seed.secret)}</code></div></div>
      <Field label="Then enter the 6-digit code it shows" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={event => setCode(event.target.value)} maxLength={7} required />
      {confirm.message && <FormMessage tone={confirm.message.tone}>{confirm.message.text}</FormMessage>}
      <div className="auth-row"><SubmitButton busy={confirm.busy}>Turn on</SubmitButton><button type="button" className="quiet-button" onClick={() => { setSeed(null); setCode(""); confirm.clear(); }}>Cancel</button></div>
    </form>}
    {!codes && user.totp_enabled && <div className="twostep-on">
      <p className="small"><ShieldCheck size={14} aria-hidden="true" /> {overview ? `${overview.recovery_codes_left} recovery code${overview.recovery_codes_left === 1 ? "" : "s"} left` : "…"}{overview && overview.recovery_codes_left <= 2 && <strong className="warn"> · running low, make new ones</strong>}{overview && overview.trusted_devices > 0 ? ` · ${overview.trusted_devices} trusted browser${overview.trusted_devices === 1 ? "" : "s"}` : ""}</p>
      {mode ? <form onSubmit={event => { event.preventDefault(); void manage.run(async () => { const path = mode === "disable" ? "/api/auth/mfa/totp/disable" : "/api/auth/mfa/recovery/regenerate"; const result = await secure(() => request<{ recovery_codes?: string[] }>(path, { body: { code: manageCode } })); setManageCode(""); setMode(null); if (result.recovery_codes) setCodes(result.recovery_codes); else { await refresh(); window.location.reload(); } }); }}>
        <Field label={mode === "disable" ? "Enter a current code to turn this off" : "Enter a current code to make new recovery codes"} inputMode="numeric" autoComplete="one-time-code" value={manageCode} onChange={event => setManageCode(event.target.value)} maxLength={14} required hint={mode === "disable" ? "A recovery code also works." : undefined} />
        {manage.message && <FormMessage tone={manage.message.tone}>{manage.message.text}</FormMessage>}
        <div className="auth-row"><SubmitButton busy={manage.busy}>{mode === "disable" ? "Turn off" : "Make new codes"}</SubmitButton><button type="button" className="quiet-button" onClick={() => { setMode(null); manage.clear(); }}>Cancel</button></div>
      </form> : <div className="auth-row"><button type="button" className="button" onClick={() => setMode("regenerate")}>New recovery codes</button><button type="button" className="button danger-button" onClick={() => setMode("disable")}>Turn off</button>{overview && overview.trusted_devices > 0 && <button type="button" className="button" onClick={() => void manage.run(async () => { await secure(() => request("/api/auth/trusted-devices", { method: "DELETE" })); await refresh(); return "Trusted browsers forgotten."; })}>Forget trusted browsers</button>}</div>}
      {!mode && manage.message && <FormMessage tone={manage.message.tone}>{manage.message.text}</FormMessage>}
    </div>}
  </section>;
}

// ---- activity -------------------------------------------------------------------------------

type ActivityEvent = { id: string; kind: string; label: string; created_at: number; network: string; user_agent: string; detail: string; alert: boolean };

export function ActivitySection() {
  const [events, setEvents] = useState<ActivityEvent[] | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setEvents((await request<{ events: ActivityEvent[] }>("/api/auth/activity")).events); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Cannot load activity."); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  return <section className="account-section" aria-labelledby="activity-h">
    <div className="account-section-head"><History size={18} aria-hidden="true" /><div><h2 id="activity-h">Security activity</h2><p>Recent sign-ins and changes. If something here isn’t you, change your password and sign out other devices.</p></div></div>
    {error && <ErrorNotice message={error} retry={() => void load()} />}
    {!events && !error && <Working label="Loading activity" />}
    <ul className="activity-list">{events?.slice(0, 20).map(item => <li key={item.id} className={item.alert ? "is-alert" : ""}>
      <span className="activity-dot" aria-hidden="true" />
      <div><strong>{item.label}{item.detail ? ` · ${item.detail}` : ""}</strong><span>{describeAgent(item.user_agent)}{item.network ? ` · network ${item.network}` : ""}</span></div>
      <time dateTime={new Date(item.created_at * 1000).toISOString()} title={new Date(item.created_at * 1000).toLocaleString()}>{relativeTime(item.created_at)}</time>
    </li>)}</ul>
    {events && events.length === 0 && <p className="muted small">Nothing recorded yet.</p>}
  </section>;
}
