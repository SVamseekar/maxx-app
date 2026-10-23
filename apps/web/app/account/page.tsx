"use client";
import SectionNav from "../components/section-nav";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, KeyRound, Laptop, Link2, Mail, ShieldAlert, ShieldCheck, Trash2, UserRound } from "lucide-react";
import { AppFooter, Badge, ErrorNotice, Working } from "../components/ui";
import { Avatar } from "../components/account-menu";
import { Field, FormMessage, OAuthButtons, PasswordField, SubmitButton } from "../components/auth-ui";
import PlusSection from "../components/plus-section";
import AccountData from "../components/account-data";
import { ActivitySection, PasskeysSection, SecurityCheckup, TwoStepSection, useOverview } from "../components/account-sections";
import { useAuth } from "../components/auth";
import { useSecure } from "../components/reauth";
import { request } from "../lib/client";
import { describeAgent, loginPath, oauthErrorMessage, relativeTime } from "../lib/auth-helpers";
import { useAction } from "../lib/use-action";
import { useQuery } from "../lib/use-query";

type SessionRow = { id: string; current: boolean; created_at: number; last_seen_at: number; user_agent: string };
const PROVIDER_NAMES: Record<string, string> = { google: "Google", apple: "Apple", microsoft: "Microsoft", github: "GitHub" };

export default function Account() {
  const { user, status, refresh, setUser } = useAuth();
  const secure = useSecure();
  const router = useRouter();
  const query = useQuery();
  const { overview, error: overviewError, refresh: refreshOverview } = useOverview(user);
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [trusted, setTrusted] = useState(0);
  const [sessionError, setSessionError] = useState("");
  const profile = useAction(), email = useAction(), password = useAction(), providers = useAction(), devices = useAction(), danger = useAction();
  const [name, setName] = useState("");
  const [editingPassword, setEditingPassword] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [phrase, setPhrase] = useState("");

  useEffect(() => { if (status === "ready" && !user) router.replace(loginPath("/account")); }, [status, user, router]);
  useEffect(() => { if (user) setName(user.display_name); }, [user]);
  const loadSessions = useCallback(async () => {
    try { const data = await request<{ sessions: SessionRow[]; trusted_devices: number }>("/api/auth/sessions"); setSessions(data.sessions); setTrusted(data.trusted_devices); setSessionError(""); }
    catch (cause) { setSessionError(cause instanceof Error ? cause.message : "Cannot load your devices."); }
  }, []);
  useEffect(() => { if (user) void loadSessions(); }, [user?.id, loadSessions]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!user) return <main id="main-content" className="account-page"><div className="loading-surface"><Working label="Loading your account" /></div></main>;
  const linkedNotice = query?.get("linked") ? `${PROVIDER_NAMES[query.get("linked")!] ?? "Provider"} is now linked to your account.` : null;
  const linkError = oauthErrorMessage(query?.get("error"));
  const methodCount = user.providers.length + (user.has_password ? 1 : 0) + user.passkeys;
  const refreshAll = async () => { await refresh(); await refreshOverview(); await loadSessions(); };

  return <main id="main-content" className="account-page">
    <header className="account-hero">
      <Avatar name={user.display_name} url={user.avatar_url} size={64} />
      <div><h1>{user.display_name}</h1><p>{user.email}</p></div>
      <Badge tone={user.email_verified ? "good" : "warn"}>{user.email_verified ? <><ShieldCheck size={13} /> Verified</> : <><ShieldAlert size={13} /> Unverified</>}</Badge>
      <span className="account-since">Member since {new Date(user.created_at * 1000).toLocaleDateString("en-US", { month: "long", year: "numeric" })}</span>
    </header>
    {linkedNotice && <FormMessage tone="success">{linkedNotice}</FormMessage>}
    {linkError && <FormMessage>{linkError}</FormMessage>}
    {overviewError && <ErrorNotice message={overviewError} retry={() => void refreshOverview()} />}

    <SectionNav label="Account sections" items={[{id:"profile-h",label:"Profile"},{id:"passkeys-h",label:"Passkeys"},{id:"twostep-h",label:"Two-step security"},{id:"methods-h",label:"Sign-in methods"},{id:"devices-h",label:"Devices"},{id:"addr-h",label:"Addresses"},{id:"data-h",label:"Your data"}]} />
    <SecurityCheckup overview={overview} />

    <section className="account-section" aria-labelledby="profile-h">
      <div className="account-section-head"><UserRound size={18} aria-hidden="true" /><div><h2 id="profile-h">Profile</h2><p>How you appear across Maxx.</p></div></div>
      <form onSubmit={event => { event.preventDefault(); void profile.run(async () => { const { user: updated } = await request<{ user: typeof user }>("/api/auth/me", { method: "PATCH", body: { display_name: name } }); setUser(updated); return "Name saved."; }); }}>
        <Field label="Display name" value={name} onChange={event => setName(event.target.value)} maxLength={80} required />
        {profile.message && <FormMessage tone={profile.message.tone}>{profile.message.text}</FormMessage>}
        <SubmitButton busy={profile.busy}>Save name</SubmitButton>
      </form>
    </section>

    <section className="account-section" aria-labelledby="email-h">
      <div className="account-section-head"><Mail size={18} aria-hidden="true" /><div><h2 id="email-h">Email</h2><p>We use it for sign-in and security alerts. It never appears next to your commitments.</p></div></div>
      <div className="account-row"><div><strong>{user.email}</strong><span>{user.email_verified ? "Verified" : "Not verified yet. Check your inbox for the confirmation link."}</span></div>
        {!user.email_verified && <button className="button" type="button" disabled={email.busy} onClick={() => void email.run(async () => { await request("/api/auth/email/resend", { body: {} }); return "Confirmation email sent."; })}>Resend email</button>}</div>
      {email.message && <FormMessage tone={email.message.tone}>{email.message.text}</FormMessage>}
    </section>

    <PasskeysSection overview={overview} refresh={refreshAll} />
    <TwoStepSection user={user} overview={overview} refresh={refreshAll} />

    <section className="account-section" aria-labelledby="methods-h">
      <div className="account-section-head"><KeyRound size={18} aria-hidden="true" /><div><h2 id="methods-h">Password and linked accounts</h2><p>Any method you keep here can reach this account.</p></div></div>
      <div className="account-row"><div><strong>Password</strong><span>{user.has_password ? "Set. Changing it signs out your other devices." : "Not set. You sign in with a passkey, a linked provider or an emailed link."}</span></div>
        <button className="button" type="button" aria-expanded={editingPassword} onClick={() => { setEditingPassword(!editingPassword); password.clear(); }}>{user.has_password ? "Change password" : "Set a password"}</button></div>
      {editingPassword && <form onSubmit={event => { event.preventDefault(); void password.run(async () => { const result = await secure(() => request<{ signed_out_elsewhere: number }>("/api/auth/password/change", { body: { current_password: user.has_password ? current : undefined, new_password: next } })); setCurrent(""); setNext(""); setEditingPassword(false); await refreshAll(); return result.signed_out_elsewhere ? `Password updated. Signed out of ${result.signed_out_elsewhere} other ${result.signed_out_elsewhere === 1 ? "device" : "devices"}.` : "Password updated."; }); }}>
        {user.has_password && <PasswordField label="Current password" value={current} onChange={setCurrent} />}
        <PasswordField label="New password" value={next} onChange={setNext} meter autoComplete="new-password" email={user.email} />
        <SubmitButton busy={password.busy}>Update password</SubmitButton>
      </form>}
      {password.message && <FormMessage tone={password.message.tone}>{password.message.text}</FormMessage>}
      <div className="linked-list">
        {Object.entries(PROVIDER_NAMES).map(([id, label]) => user.providers.includes(id) ? <div className="account-row" key={id}><div><strong>{label}</strong><span>Linked</span></div>
          <button className="button" type="button" disabled={providers.busy || methodCount <= 1} title={methodCount <= 1 ? "Add another way to sign in before unlinking your only one" : undefined} onClick={() => void providers.run(async () => { await secure(() => request(`/api/auth/oauth/${id}`, { method: "DELETE" })); await refreshAll(); return `${label} unlinked.`; })}><Link2 size={14} aria-hidden="true" /> Unlink</button></div> : null)}
      </div>
      <OAuthButtons next="/account" verb="Link" link linked={user.providers} guard={async () => { await secure(() => request("/api/auth/reauth/check", { body: {} })); }} />
      {providers.message && <FormMessage tone={providers.message.tone}>{providers.message.text}</FormMessage>}
    </section>

    <section className="account-section" aria-labelledby="devices-h">
      <div className="account-section-head"><Laptop size={18} aria-hidden="true" /><div><h2 id="devices-h">Devices</h2><p>Browsers currently signed in to your account{trusted ? `, and ${trusted} you chose to trust for two-step` : ""}.</p></div></div>
      {sessionError && <ErrorNotice message={sessionError} retry={() => void loadSessions()} />}
      {!sessions && !sessionError && <Working label="Loading devices" />}
      <ul className="session-list">{sessions?.map(session => <li key={session.id}><div><strong>{describeAgent(session.user_agent)}</strong>{session.current && <Badge tone="good"><Check size={12} /> This device</Badge>}<span>Active {relativeTime(session.last_seen_at)} · signed in {relativeTime(session.created_at)}</span></div>
        {!session.current && <button className="button" type="button" disabled={devices.busy} onClick={() => void devices.run(async () => { await secure(() => request(`/api/auth/sessions/${session.id}`, { method: "DELETE" })); await loadSessions(); return "Device signed out."; })}>Sign out</button>}</li>)}</ul>
      {sessions && sessions.length > 1 && <button className="button" type="button" disabled={devices.busy} onClick={() => void devices.run(async () => { const { revoked } = await secure(() => request<{ revoked: number }>("/api/auth/sessions/revoke-others", { body: {} })); await loadSessions(); return `Signed out of ${revoked} other ${revoked === 1 ? "device" : "devices"}.`; })}>Sign out everywhere else</button>}
      {devices.message && <FormMessage tone={devices.message.tone}>{devices.message.text}</FormMessage>}
    </section>

    <PlusSection />
    <AccountData />
    <ActivitySection />

    <section className="account-section danger" aria-labelledby="danger-h">
      <div className="account-section-head"><Trash2 size={18} aria-hidden="true" /><div><h2 id="danger-h">Delete account</h2><p>Releases your open commitments and removes your sign-in. Past negotiation results stay, anonymised. This cannot be undone.</p></div></div>
      {!confirming ? <button className="button danger-button" type="button" onClick={() => setConfirming(true)}>Delete my account…</button>
        : <form onSubmit={event => { event.preventDefault(); void danger.run(async () => { await secure(() => request("/api/auth/me/delete", { body: { confirm: phrase } })); window.location.assign("/"); }); }}>
          <Field label={<>Type <code>delete my account</code> to confirm</>} value={phrase} onChange={event => setPhrase(event.target.value)} autoComplete="off" required />
          {danger.message && <FormMessage tone={danger.message.tone}>{danger.message.text}</FormMessage>}
          <div className="auth-row"><button className="button" type="button" onClick={() => { setConfirming(false); danger.clear(); }}>Keep my account</button><button className="button danger-button" type="submit" disabled={danger.busy || phrase !== "delete my account"}>Permanently delete</button></div>
        </form>}
    </section>
    <AppFooter />
  </main>;
}
