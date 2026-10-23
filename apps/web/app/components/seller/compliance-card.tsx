"use client";
import { useState } from "react";
import { FileCheck2, Fingerprint } from "lucide-react";
import { request } from "../../lib/client";
import { useAction } from "../../lib/use-action";
import { usd } from "../../blocs/types";
import { Badge } from "../ui";
import { Field, FormMessage, SubmitButton } from "../auth-ui";
import { useSecure } from "../reauth";
import type { Profile } from "./types";

const IDENTITY: Record<string, [string, "good" | "warn" | "neutral"]> = { verified: ["Verified", "good"], pending: ["Being checked", "neutral"], requires_input: ["Needs another try", "warn"], none: ["Not started", "warn"] };

function date(seconds: number | null) {
  return seconds ? new Date(seconds * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—";
}

/** Identity, the INFORM Act tax id for high-volume sellers, and the yearly re-certification. */
export default function ComplianceCard({ profile, reload }: { profile: Profile; reload: () => Promise<void> }) {
  const c = profile.compliance;
  const secure = useSecure();
  const [tax, setTax] = useState("");
  const [sure, setSure] = useState(false);
  const action = useAction();
  const [label, tone] = IDENTITY[c.identity_status] ?? IDENTITY.none;
  const needsTax = c.high_volume && !c.tax_id_on_file;
  return <section className="seller-card" aria-labelledby="comp-h">
    <h3 id="comp-h"><FileCheck2 size={17} aria-hidden="true" /> Verification and yearly details</h3>
    <dl className="trader-info">
      {c.identity_required && <div><dt><Fingerprint size={13} aria-hidden="true" /> Identity</dt><dd><Badge tone={tone}>{label}</Badge></dd></div>}
      <div><dt>Sales in the last 12 months</dt><dd>{c.sales_last_year} orders · {usd(c.revenue_last_year)}</dd></div>
      <div><dt>Tax id</dt><dd>{c.tax_id_on_file ? `On file, ending ${c.tax_id_last4}` : c.high_volume ? "Required" : "Not needed yet"}</dd></div>
      <div><dt>Details confirmed until</dt><dd>{date(c.recertify_by)}</dd></div>
    </dl>
    {!c.can_sell && profile.status === "ACTIVE" && <FormMessage tone="error">Your offers are paused from new Blocs until you confirm your details{needsTax ? " and add your tax id" : ""}. Orders you already have are not affected.</FormMessage>}
    {needsTax && <p className="small">Under US law (the INFORM Consumers Act), a seller with {c.thresholds.sales} or more sales and {usd(c.thresholds.revenue)} or more in a year must give a tax id within {c.thresholds.days} days.{c.info_due_by && <> Yours is due by <strong>{date(c.info_due_by)}</strong>.</>}</p>}
    {(needsTax || c.recertify_due || !c.can_sell) && <>
      {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
      <form onSubmit={event => { event.preventDefault(); void action.run(async () => { await secure(() => request("/api/seller/compliance", { body: { certify: sure, tax_id: tax } })); setTax(""); await reload(); return "Thank you. Your details are confirmed for another year."; }); }}>
        {needsTax && <Field label="Tax id (for example an EIN, VAT or GST number)" value={tax} onChange={event => setTax(event.target.value)} required maxLength={30} autoComplete="off" hint="Stored encrypted; only the last four characters are shown." />}
        <label className="check-row"><input type="checkbox" checked={sure} onChange={event => setSure(event.target.checked)} /> My business details, contact information and payout email are accurate and complete.</label>
        <SubmitButton busy={action.busy} disabled={!sure || (needsTax && tax.trim().length < 4)}>Confirm my details</SubmitButton>
      </form></>}
  </section>;
}
