"use client";
import { useEffect, useState } from "react";
import { BadgeCheck, Check, Clock, Fingerprint, Mail, ScanFace, ShieldCheck } from "lucide-react";
import { request } from "../../lib/client";
import { useAction } from "../../lib/use-action";
import { useQuery } from "../../lib/use-query";
import { FormMessage } from "../auth-ui";
import type { Profile } from "./types";

const STEPS = [
  { id: "apply", label: "Application", icon: BadgeCheck },
  { id: "payout_email", label: "Payout email", icon: Mail },
  { id: "identity", label: "Identity check", icon: Fingerprint },
  { id: "review", label: "Checks and review", icon: ShieldCheck },
  { id: "live", label: "Selling", icon: Check },
] as const;

/** Where the seller is between applying and selling. */
export function OnboardingSteps({ profile }: { profile: Profile }) {
  const next = profile.compliance.next_step;
  const current = next === "payout_email" ? 1 : next === "identity" ? 2 : next === "screening" || next === "review" ? 3 : 4;
  const steps = STEPS.filter(step => step.id !== "identity" || profile.compliance.identity_required);
  const index = (id: string) => STEPS.findIndex(step => step.id === id);
  return <ol className="onboarding-steps" aria-label="Seller setup">{steps.map(step => {
    const position = index(step.id);
    const state = position < current ? "done" : position === current ? "current" : "todo";
    return <li key={step.id} className={state} aria-current={state === "current" ? "step" : undefined}><step.icon size={15} aria-hidden="true" /><span>{step.label}</span></li>;
  })}</ol>;
}

/** Start (or re-check) the identity check with the verification provider. */
export function IdentityStep({ profile, onDone }: { profile: Profile; onDone: () => Promise<void> }) {
  const action = useAction();
  const query = useQuery();
  const [checked, setChecked] = useState(false);
  const status = profile.compliance.identity_status;
  useEffect(() => {
    // Back from the provider's page: ask the provider for the result instead of trusting the return.
    if (!checked && query?.get("identity") === "returned" && status === "pending") { setChecked(true); void action.run(async () => { await request("/api/seller/identity/refresh", { body: {} }); await onDone(); }); }
  }, [query, status, checked, action, onDone]);
  async function start() {
    const { url } = await request<{ url: string; simulated: boolean }>("/api/seller/identity/start", { body: {} });
    // Only Maxx's own simulated page or Stripe's hosted page are followed.
    if (url.startsWith("/sell/verify-identity?") || url.startsWith("https://verify.stripe.com/")) window.location.assign(url);
    else throw new Error("The identity provider returned an unexpected address.");
  }
  return <section className="seller-card" aria-labelledby="idv-h">
    <h2 id="idv-h"><ScanFace size={18} aria-hidden="true" /> Verify your identity</h2>
    <p className="muted">Marketplaces must know who their sellers are (EU Digital Services Act article 30, US INFORM Consumers Act). You take a photo of a government ID and a live selfie on {profile.compliance.identity_mode === "stripe" ? "Stripe's secure page" : "the identity provider's page"}; Maxx never sees or stores the document, only the result and your verified name.</p>
    {status === "pending" && <p className="order-note" role="status"><Clock size={15} aria-hidden="true" /> Your check is being processed. This page updates when the provider has a result.</p>}
    {status === "requires_input" && <FormMessage tone="error">The provider could not verify your ID. Try again with a clear photo of a valid, unexpired document.</FormMessage>}
    {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
    <div className="inline-actions">
      <button type="button" className="button primary" disabled={action.busy} onClick={() => void action.run(start)}><Fingerprint size={15} aria-hidden="true" /> {status === "none" ? "Start identity check" : "Start again"}</button>
      {status === "pending" && <button type="button" className="quiet-button" disabled={action.busy} onClick={() => void action.run(async () => { await request("/api/seller/identity/refresh", { body: {} }); await onDone(); return "Checked with the provider."; })}>Check the result</button>}
    </div>
  </section>;
}
