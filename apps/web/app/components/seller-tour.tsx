"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, Bot, PackageCheck, Store, Truck, Wallet } from "lucide-react";
import { request } from "../lib/client";
import { useAction } from "../lib/use-action";
import { loginPath } from "../lib/auth-helpers";
import { useAuth } from "./auth";
import { FormMessage } from "./auth-ui";
import { Badge } from "./ui";
import { useServerReady } from "./server-wake";

const STEPS = [
  { icon: Store, text: "You get a demo seller account with onboarding already passed (identity, sanctions screening and review are shown as done)." },
  { icon: Bot, text: "Your AI agent offers 3 units of a demo product against two simulated competitors, within hard limits." },
  { icon: PackageCheck, text: "Three demo buyers hold money with PayPal (simulated), the negotiation runs, and you win orders. They give addresses automatically." },
  { icon: Truck, text: "Ship from the seller console with a test tracking number and watch the carrier updates arrive." },
  { icon: Wallet, text: "As a new seller you are paid once the parcel is delivered. See the payout, the fee and your notifications." },
];

/** The judge's way into the seller side, in a few minutes. Only offered in the simulator setup. */
export default function SellerTour() {
  const { user, status } = useAuth();
  const [available, setAvailable] = useState(false);
  const [started, setStarted] = useState<string | null>(null);
  const action = useAction();
  const ready = useServerReady();
  // Asked once the API answers, so a sleeping server does not hide the tour.
  useEffect(() => { if (ready) void request<{ available: boolean }>("/api/demo/seller-tour").then(r => setAvailable(r.available)).catch(() => setAvailable(false)); }, [ready]);
  if (!available) return null;
  return <section className="seller-card seller-tour" aria-labelledby="tour-h">
    <div className="section-heading"><h2 id="tour-h">See the seller side.</h2><Badge>About 4 minutes</Badge></div>
    <ol className="tour-steps">{STEPS.map(step => <li key={step.text}><step.icon size={16} aria-hidden="true" /><span>{step.text}</span></li>)}</ol>
    {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
    {status === "ready" && !user ? <Link className="button primary" href={loginPath("/judge")}>Sign in to start the tour <ArrowUpRight size={15} /></Link>
      : started ? <div className="inline-actions"><Link className="button primary" href="/sell">Open your seller console <ArrowUpRight size={15} /></Link><Link className="button" href={`/blocs/${started}/room`}>Watch the negotiation</Link></div>
      : <button type="button" className="button primary" disabled={action.busy || status === "loading"} onClick={() => void action.run(async () => { const result = await request<{ bloc_id: string }>("/api/demo/seller-tour", { body: {} }); setStarted(result.bloc_id); return "Your demo shop is open and the negotiation has started."; })}>Start the seller tour</button>}
    <p className="small muted">Demo buyers are not accounts and never receive email. Money moves only in the PayPal simulator, to the sandbox receiver.</p>
  </section>;
}
