"use client";
import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { request } from "../../lib/client";
import { useAction } from "../../lib/use-action";
import { countryName } from "../../lib/countries";
import { usd } from "../../blocs/types";
import { Field, FormMessage, SubmitButton } from "../auth-ui";
import { useSecure } from "../reauth";
import ComplianceCard from "./compliance-card";
import type { Overview, Profile } from "./types";

export default function ProfileTab({ overview, profile, reload }: { overview: Overview; profile: Profile; reload: () => Promise<void> }) {
  const secure = useSecure();
  const [form, setForm] = useState({ ship_within_days: profile.ship_within_days, ships_to: profile.ships_to, return_days: profile.return_days, return_policy: profile.return_policy, support_email: profile.support_email, phone: profile.phone, website: profile.website });
  const [newEmail, setNewEmail] = useState("");
  const commit = useAction(), email = useAction();
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm(current => ({ ...current, [key]: value }));
  return <div className="seller-orders">
    <section className="seller-card" aria-labelledby="acct-h">
      <h3 id="acct-h">Your account</h3>
      <dl className="trader-info"><div><dt>Seller code</dt><dd>{profile.code}</dd></div><div><dt>Legal name</dt><dd>{profile.legal_name} ({profile.business_type})</dd></div><div><dt>Country</dt><dd>{countryName(profile.country)}</dd></div><div><dt>Payout email</dt><dd>{profile.payout_email}</dd></div><div><dt>Strikes</dt><dd>{profile.strikes} of 3{profile.strikes > 0 && " (missed commitments; three suspend your account)"}</dd></div><div><dt>Delivered orders</dt><dd>{profile.deliveries}{profile.trusted ? " · paid at the first carrier scan" : " · paid on delivery"}</dd></div></dl>
      {Number(profile.owed) > 0 && <FormMessage tone="info"><AlertTriangle size={14} aria-hidden="true" /> You owe Maxx {usd(profile.owed)} for refunded orders. It is taken from your next payouts.</FormMessage>}
      <p className="small muted">To change your legal name, country or business type, write to support. Buyers see your trader details after they buy.</p>
    </section>
    <ComplianceCard profile={profile} reload={reload} />
    <section className="seller-card" aria-labelledby="commit-h">
      <h3 id="commit-h">Shipping, returns and contact</h3>
      {commit.message && <FormMessage tone={commit.message.tone}>{commit.message.text}</FormMessage>}
      <form onSubmit={event => { event.preventDefault(); void commit.run(async () => { await request("/api/seller/commitments", { body: form }); await reload(); return "Saved. Buyers see the new commitments on future orders."; }); }}>
        <label className="select-field">Ship within<select value={form.ship_within_days} onChange={event => set("ship_within_days", Number(event.target.value))}>{Array.from({ length: 14 }, (_, i) => i + 1).map(days => <option key={days} value={days}>{days} {days === 1 ? "day" : "days"}</option>)}</select></label>
        <fieldset className="country-grid"><legend>Countries I ship to</legend>{overview.countries.map(code => <label key={code}><input type="checkbox" checked={form.ships_to.includes(code)} onChange={event => set("ships_to", event.target.checked ? [...form.ships_to, code] : form.ships_to.filter(item => item !== code))} /> {countryName(code)}</label>)}</fieldset>
        <label className="select-field">Return window<select value={form.return_days} onChange={event => set("return_days", Number(event.target.value))}>{[14, 21, 30, 45, 60, 90].map(days => <option key={days} value={days}>{days} days</option>)}</select></label>
        <label className="select-field">Return policy<textarea value={form.return_policy} onChange={event => set("return_policy", event.target.value)} rows={3} minLength={20} maxLength={1000} required /></label>
        <Field label="Support email" type="email" value={form.support_email} onChange={event => set("support_email", event.target.value)} required />
        <Field label="Phone" type="tel" value={form.phone} onChange={event => set("phone", event.target.value)} required />
        <Field label="Website" type="url" value={form.website} onChange={event => set("website", event.target.value)} />
        <SubmitButton busy={commit.busy}>Save changes</SubmitButton>
      </form>
    </section>
    <section className="seller-card" aria-labelledby="pe-h">
      <h3 id="pe-h">Payout email</h3>
      <p className="muted small">Changing it pauses your offers and payouts until the new address is confirmed, and a newly confirmed address may wait before it is paid.</p>
      {email.message && <FormMessage tone={email.message.tone}>{email.message.text}</FormMessage>}
      <form className="inline-form" onSubmit={event => { event.preventDefault(); void email.run(async () => { await secure(() => request("/api/seller/payout-email", { body: { payout_email: newEmail } })); await reload(); }); }}>
        <Field label="New PayPal email" type="email" value={newEmail} onChange={event => setNewEmail(event.target.value)} required autoComplete="off" />
        <SubmitButton busy={email.busy} disabled={!newEmail || profile.demo}>Change and re-verify</SubmitButton>
      </form>
    </section>
  </div>;
}
