"use client";
import { useState } from "react";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import Link from "next/link";
import { request } from "../../lib/client";
import { useAction } from "../../lib/use-action";
import { countryName } from "../../lib/countries";
import { Field, FormMessage, SubmitButton } from "../auth-ui";
import type { Overview } from "./types";

const STEPS = ["Who you are", "Contact", "Shipping and returns", "Agreement"];
const blank = {
  business_name: "", legal_name: "", business_type: "company", country: "", trade_register_no: "", address_line1: "", address_city: "", address_region: "", address_postal: "", phone: "", support_email: "", website: "",
  ship_within_days: 3, ships_to: [] as string[], return_days: 30, return_policy: "", payout_email: "", accept_terms: false, certify_accurate: false, certify_lawful: false, certify_authorised: false,
};

/** Four short steps. We ask for what marketplace law asks for, and say why. */
export default function ApplyForm({ overview, onDone }: { overview: Overview; onDone: () => Promise<void> }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(blank);
  const [problem, setProblem] = useState("");
  const action = useAction();
  const set = <K extends keyof typeof blank>(key: K, value: (typeof blank)[K]) => setForm(current => ({ ...current, [key]: value }));
  const text = (key: keyof typeof blank) => ({ value: String(form[key]), onChange: (event: { target: { value: string } }) => set(key, event.target.value as never) });
  const euCompany = overview.eu_countries.includes(form.country) && form.business_type === "company";

  function check(): string {
    if (step === 0) {
      if (form.business_name.trim().length < 2 || form.legal_name.trim().length < 2) return "Enter your trading name and your legal name.";
      if (!form.country) return "Choose the country you sell from.";
      if (euCompany && !form.trade_register_no.trim()) return "EU companies must give their trade register number.";
    }
    if (step === 1) {
      if (!form.address_line1.trim() || !form.address_city.trim() || !form.address_postal.trim()) return "Enter your full business address.";
      if (!/^[+()\d\s.-]{6,30}$/.test(form.phone)) return "Enter a phone number with digits, spaces, + ( ) - only.";
      if (!/^\S+@\S+\.\S+$/.test(form.support_email)) return "Enter a support email address buyers can reach.";
      if (form.website && !/^https:\/\//.test(form.website)) return "The website must start with https://";
    }
    if (step === 2) {
      if (form.ships_to.length === 0) return "Choose at least one country you ship to.";
      if (form.return_policy.trim().length < 20) return "Describe your return policy in a sentence or two (at least 20 characters).";
    }
    return "";
  }
  function next() { const issue = check(); setProblem(issue); if (!issue) setStep(step + 1); }
  const ready = form.accept_terms && form.certify_accurate && form.certify_lawful && form.certify_authorised && /^\S+@\S+\.\S+$/.test(form.payout_email);

  return <section className="seller-card wizard" aria-labelledby="apply-h">
    <h2 id="apply-h">Apply to sell</h2>
    <p className="muted">You are the seller of record. Maxx runs the group, the negotiation and the payment; <strong>you ship and support the goods</strong>. Maxx keeps {overview.fee_percent}% of each sale, taken from your payout, so buyers never pay more than their winning price.</p>
    {!overview.email_verified && <FormMessage tone="info">Confirm your account email first. Check your inbox for the verification link.</FormMessage>}
    <ol className="wizard-steps" aria-label="Application steps">{STEPS.map((label, index) => <li key={label} className={index === step ? "current" : index < step ? "done" : ""} aria-current={index === step ? "step" : undefined}><span>{index < step ? <Check size={13} aria-hidden="true" /> : index + 1}</span>{label}</li>)}</ol>
    {(problem || action.message) && <FormMessage tone={problem ? "error" : action.message!.tone}>{problem || action.message!.text}</FormMessage>}

    <form onSubmit={event => { event.preventDefault(); if (step < 3) { next(); return; } void action.run(async () => { setProblem(""); await request("/api/seller/apply", { body: form }); await onDone(); }); }}>
      {step === 0 && <>
        <Field label="Trading name (shown to buyers)" {...text("business_name")} maxLength={120} required autoComplete="organization" />
        <Field label="Legal name" {...text("legal_name")} maxLength={160} required hint="Your full legal name, or your company’s registered name." />
        <fieldset className="pay-method"><legend>You are selling as</legend>{(["company", "individual"] as const).map(kind => <label key={kind} className={form.business_type === kind ? "is-selected" : ""}><input type="radio" name="type" checked={form.business_type === kind} onChange={() => set("business_type", kind)} /> {kind === "company" ? "A company" : "An individual"}</label>)}</fieldset>
        <label className="select-field">Country you sell from<select value={form.country} onChange={event => set("country", event.target.value)} required><option value="" disabled>Choose…</option>{overview.countries.map(code => <option key={code} value={code}>{countryName(code)}</option>)}</select></label>
        <Field label={euCompany ? "Trade register number (required)" : "Trade register number (if you have one)"} {...text("trade_register_no")} maxLength={60} hint="EU marketplace rules require this for companies." />
      </>}
      {step === 1 && <>
        <Field label="Business address" {...text("address_line1")} maxLength={200} required autoComplete="address-line1" hint="Shown to buyers after they buy, as marketplace law requires." />
        <div className="two-up"><Field label="City" {...text("address_city")} maxLength={100} required autoComplete="address-level2" /><Field label="State or region" {...text("address_region")} maxLength={100} autoComplete="address-level1" /></div>
        <Field label="Postal code" {...text("address_postal")} maxLength={20} required autoComplete="postal-code" />
        <Field label="Phone" type="tel" {...text("phone")} maxLength={40} required autoComplete="tel" />
        <Field label="Support email for buyers" type="email" {...text("support_email")} maxLength={320} required hint="Buyers and Maxx will write here about orders." />
        <Field label="Website (optional)" type="url" {...text("website")} maxLength={300} placeholder="https://" />
      </>}
      {step === 2 && <>
        <label className="select-field">I will ship within<select value={form.ship_within_days} onChange={event => set("ship_within_days", Number(event.target.value))}>{Array.from({ length: 14 }, (_, i) => i + 1).map(days => <option key={days} value={days}>{days} {days === 1 ? "day" : "days"} of getting the buyer’s address</option>)}</select></label>
        <p className="small muted">If you do not ship in time (plus a 2-day grace period) the buyer is refunded and you receive a strike.</p>
        <fieldset className="country-grid"><legend>Countries I ship to</legend>{overview.countries.map(code => <label key={code}><input type="checkbox" checked={form.ships_to.includes(code)} onChange={event => set("ships_to", event.target.checked ? [...form.ships_to, code] : form.ships_to.filter(item => item !== code))} /> {countryName(code)}</label>)}</fieldset>
        <label className="select-field">Return window<select value={form.return_days} onChange={event => set("return_days", Number(event.target.value))}>{[14, 21, 30, 45, 60, 90].map(days => <option key={days} value={days}>{days} days</option>)}</select></label>
        <label className="select-field">Return policy buyers will see<textarea value={form.return_policy} onChange={event => set("return_policy", event.target.value)} rows={4} minLength={20} maxLength={1000} required placeholder="Unused items in original packaging can be returned within 30 days for a full refund. We pay return postage for faulty items." /></label>
        <p className="small muted">Returns must be allowed for at least {overview.min_return_days} days, and consumer law where your buyers live may give them more.</p>
      </>}
      {step === 3 && <>
        <Field label="PayPal email for payouts" type="email" {...text("payout_email")} maxLength={320} required autoComplete="email" hint="We send a code here next. You are paid only at an address you have confirmed." />
        <h3>What you agree to</h3>
        <ul className="terms-list">{overview.terms.map(term => <li key={term}>{term}</li>)}</ul>
        <details className="prohibited"><summary>Items you may not sell</summary><ul>{overview.prohibited.map(item => <li key={item}>{item}</li>)}</ul></details>
        <p className="small muted">Full text: <Link href="/legal/seller-terms" target="_blank">Seller Agreement</Link> · <Link href="/legal/prohibited" target="_blank">Prohibited items</Link> · <Link href="/legal/privacy" target="_blank">Privacy</Link></p>
        <div className="checks">
          <label className="check"><input type="checkbox" checked={form.accept_terms} onChange={event => set("accept_terms", event.target.checked)} /> I have read and accept the Seller Agreement.</label>
          <label className="check"><input type="checkbox" checked={form.certify_accurate} onChange={event => set("certify_accurate", event.target.checked)} /> Everything I entered is accurate, and I will keep it up to date.</label>
          <label className="check"><input type="checkbox" checked={form.certify_lawful} onChange={event => set("certify_lawful", event.target.checked)} /> I sell only new, genuine, lawful goods, none of them prohibited.</label>
          <label className="check"><input type="checkbox" checked={form.certify_authorised} onChange={event => set("certify_authorised", event.target.checked)} /> I am authorised to sell these goods and to receive money at the payout email.</label>
        </div>
      </>}
      <div className="wizard-nav">
        {step > 0 && <button type="button" className="quiet-button" onClick={() => { setProblem(""); setStep(step - 1); }}><ArrowLeft size={14} aria-hidden="true" /> Back</button>}
        {step < 3 ? <button type="submit" className="button primary">Next <ArrowRight size={15} aria-hidden="true" /></button> : <SubmitButton busy={action.busy} disabled={!ready || !overview.email_verified}>Send my confirmation code</SubmitButton>}
      </div>
    </form>
    <p className="small muted">Maxx does not independently verify businesses in this prototype. {overview.review === "manual" ? "A person reviews every application before it goes live." : "Sellers go live once the payout email is confirmed."} A launch would need identity and business verification through PayPal’s partner onboarding.</p>
  </section>;
}
