"use client";
import { useCallback, useEffect, useState } from "react";
import { FlaskConical, Sparkles } from "lucide-react";
import { request } from "../lib/client";
import { useAction } from "../lib/use-action";
import { FormMessage } from "./auth-ui";
import { Badge } from "./ui";

type Status = {
  enabled: boolean; simulated: boolean; premium: boolean; checkout_limit: string; benefits: string[];
  plans: { id: "weekly" | "yearly"; label: string; price: string; interval: string }[];
  subscription: { id: string; plan: string; status: string } | null;
};

/** Maxx Plus, billed by PayPal Subscriptions. The page only reflects what PayPal's webhook told the server. */
export default function PlusSection() {
  const [status, setStatus] = useState<Status | null>(null);
  const action = useAction();
  const load = useCallback(async () => { try { setStatus(await request<Status>("/api/money/subscription")); } catch { setStatus(null); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (!status?.enabled) return null;
  const pending = status.subscription?.status === "APPROVAL_PENDING";
  async function subscribe(plan: string) {
    await action.run(async () => {
      const started = await request<{ approve_url: string; simulated: boolean }>("/api/money/subscription", { body: { plan } });
      if (started.approve_url) { window.location.assign(started.approve_url); return; }
      await load();
    });
  }
  return <section className="account-section" aria-labelledby="plus-h">
    <div className="section-heading"><h2 id="plus-h"><Sparkles size={16} aria-hidden="true" /> Maxx Plus</h2>{status.premium ? <Badge tone="good">Active</Badge> : status.simulated ? <Badge tone="warn"><FlaskConical size={11} /> Simulated PayPal</Badge> : <Badge>PayPal sandbox</Badge>}</div>
    <p className="muted">{status.benefits.join(" · ")}. Your agent checkout limit today: ${status.checkout_limit}.</p>
    {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
    {status.premium ? <div className="inline-actions"><button type="button" className="button" disabled={action.busy} onClick={() => void action.run(async () => { await request("/api/money/subscription/cancel", { body: {} }); await load(); return "Cancelled. Plus ends now in this demo; PayPal would keep it to the end of the period."; })}>Cancel Plus</button></div>
      : pending ? <div className="inline-actions"><p className="muted small">Waiting for PayPal to confirm the subscription.</p>{status.simulated && <button type="button" className="button primary" disabled={action.busy} onClick={() => void action.run(async () => { await request("/api/money/subscription/simulate-approve", { body: {} }); await load(); return "PayPal confirmed. Plus is active."; })}>Approve in simulated PayPal</button>}</div>
      : <div className="plan-grid">{status.plans.map(plan => <button type="button" key={plan.id} className="plan-card" disabled={action.busy} onClick={() => void subscribe(plan.id)}><strong>{plan.label}</strong><span>${plan.price} <small>/ {plan.interval}</small></span></button>)}</div>}
  </section>;
}
