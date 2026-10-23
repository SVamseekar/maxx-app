"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Download, MapPin, Trash2 } from "lucide-react";
import { ApiError, request } from "../lib/client";
import { useAction } from "../lib/use-action";
import { countryName } from "../lib/countries";
import type { AddressSummary } from "../lib/orders";
import AddressForm from "./address-form";
import { FormMessage } from "./auth-ui";
import { useSecure } from "./reauth";

/** Saved delivery addresses and the person's right to take their data with them. */
export default function AccountData() {
  const secure = useSecure();
  const [addresses, setAddresses] = useState<AddressSummary[] | null>(null);
  const [adding, setAdding] = useState(false);
  const addressAction = useAction(), exportAction = useAction();
  const load = useCallback(async () => { try { setAddresses(await request<AddressSummary[]>("/api/addresses")); } catch { setAddresses([]); } }, []);
  useEffect(() => { void load(); }, [load]);

  async function download() {
    await exportAction.run(async () => {
      await secure(async () => {
        const response = await fetch("/api/me/export", { credentials: "same-origin", cache: "no-store" });
        if (!response.ok) { const body = await response.json().catch(() => ({})) as { detail?: string; message?: string; code?: string }; throw new ApiError(body.message ?? body.detail ?? "Could not export your data.", response.status, body.code); }
        const url = URL.createObjectURL(await response.blob());
        const link = Object.assign(document.createElement("a"), { href: url, download: "maxx-my-data.json" });
        document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
      });
      return "Your data was downloaded.";
    });
  }

  return <>
    <section className="account-section" aria-labelledby="addr-h">
      <h2 id="addr-h"><MapPin size={16} aria-hidden="true" /> Delivery addresses</h2>
      <p className="muted">Used only when you win an order, so the seller can ship it. Encrypted on our servers and wiped from an order 90 days after it finishes. Never shown to other buyers.</p>
      {addressAction.message && <FormMessage tone={addressAction.message.tone}>{addressAction.message.text}</FormMessage>}
      {addresses && addresses.length > 0 && <ul className="address-list">{addresses.map(a => <li key={a.id}><div><strong>{a.label || a.name}</strong><span>{a.name}, {a.line1}, {a.city} {a.postal}, {countryName(a.country)}</span></div><button type="button" className="icon-button" aria-label={`Delete address ${a.label || a.line1}`} disabled={addressAction.busy} onClick={() => void addressAction.run(async () => { await request(`/api/addresses/${a.id}/delete`, { body: {} }); await load(); })}><Trash2 size={15} /></button></li>)}</ul>}
      {adding ? <div><AddressForm onSaved={async () => { setAdding(false); await load(); }} /><button type="button" className="quiet-button" onClick={() => setAdding(false)}>Cancel</button></div> : <button type="button" className="button" onClick={() => setAdding(true)}>Add an address</button>}
      <p className="small muted"><Link href="/orders">Your orders</Link></p>
    </section>
    <section className="account-section" aria-labelledby="data-h">
      <h2 id="data-h"><Download size={16} aria-hidden="true" /> Your data</h2>
      <p className="muted">Download everything Maxx holds about your account: profile, sign-in activity, addresses, payments, orders and problem reports. We may ask you to confirm it is you first. <Link href="/legal/privacy">Privacy Policy</Link></p>
      {exportAction.message && <FormMessage tone={exportAction.message.tone}>{exportAction.message.text}</FormMessage>}
      <button type="button" className="button" disabled={exportAction.busy} onClick={() => void download()}><Download size={15} aria-hidden="true" /> Download my data</button>
    </section>
  </>;
}
