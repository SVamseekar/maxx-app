"use client";
import Link from "next/link";
import { useState } from "react";
import { FlaskConical, ScanFace, ShieldCheck, XCircle } from "lucide-react";
import { AppFooter, ErrorNotice, PageIntro } from "../../components/ui";
import { FormMessage } from "../../components/auth-ui";
import { request } from "../../lib/client";
import { useAction } from "../../lib/use-action";
import { useQuery } from "../../lib/use-query";

/** The simulated identity provider (VERIFY_MODE=simulator). With Stripe the seller goes to
 * Stripe's own page instead, and this page refuses to do anything (the API returns 404). */
export default function SimulatedIdentityCheck() {
  const query = useQuery();
  const session = query?.get("session") ?? "";
  const action = useAction();
  const [done, setDone] = useState<"verified" | "failed" | null>(null);
  const valid = /^SIM-IDV-[0-9A-F]{16}$/.test(session);
  async function finish(outcome: "verified" | "failed") {
    await request("/api/seller/identity/simulate", { body: { session, outcome } });
    setDone(outcome);
  }
  return <main id="main-content" className="idv-page">
    <PageIntro title="Identity check." description="A stand-in for the verification provider's page, so the whole seller journey can be tried without a real ID." />
    <div className="notice-strip"><FlaskConical size={18} aria-hidden="true" /><p><strong>Simulated provider.</strong> No document or photo is taken. With VERIFY_MODE=stripe, sellers go to Stripe Identity instead, where a government ID and a matching live selfie are checked.</p></div>
    {query && !valid && <ErrorNotice message="This link is not a valid identity check. Start again from your seller console." />}
    {valid && !done && <section className="seller-card idv-card" aria-labelledby="sim-h">
      <h2 id="sim-h"><ScanFace size={18} aria-hidden="true" /> Choose the provider's result</h2>
      <p className="muted">A real provider decides this from your ID and selfie. Pick an outcome to see how Maxx handles each one.</p>
      {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
      <div className="inline-actions"><button type="button" className="button primary" disabled={action.busy} onClick={() => void action.run(() => finish("verified"))}><ShieldCheck size={15} aria-hidden="true" /> Pass the check</button><button type="button" className="button" disabled={action.busy} onClick={() => void action.run(() => finish("failed"))}><XCircle size={15} aria-hidden="true" /> Fail the check</button></div>
    </section>}
    {done && <section className="seller-card" role="status"><h2>{done === "verified" ? "Identity verified." : "The check did not pass."}</h2><p className="muted">{done === "verified" ? "Your seller console shows the next step." : "You can try again from your seller console."}</p><Link className="button primary" href="/sell">Back to the seller console</Link></section>}
    <AppFooter />
  </main>;
}
