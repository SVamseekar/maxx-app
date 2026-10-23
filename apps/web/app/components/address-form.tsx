"use client";
import { useState } from "react";
import { request } from "../lib/client";
import { useAction } from "../lib/use-action";
import { COUNTRIES } from "../lib/countries";
import type { AddressSummary } from "../lib/orders";
import { Field, FormMessage, SubmitButton } from "./auth-ui";

/** A delivery address. It is encrypted on the server and shown only to the seller of an order you have won. */
export default function AddressForm({ onSaved, defaultCountry = "" }: { onSaved: (address: AddressSummary) => void; defaultCountry?: string }) {
  const [form, setForm] = useState({ label: "", name: "", line1: "", line2: "", city: "", region: "", postal: "", country: defaultCountry, phone: "" });
  const action = useAction();
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) => setForm(current => ({ ...current, [key]: event.target.value }));
  return <form className="address-form" onSubmit={event => { event.preventDefault(); void action.run(async () => { onSaved(await request<AddressSummary>("/api/addresses", { body: form })); }); }}>
    {action.message && <FormMessage tone={action.message.tone}>{action.message.text}</FormMessage>}
    <Field label="Full name" value={form.name} onChange={set("name")} required autoComplete="name" maxLength={100} />
    <Field label="Address line 1" value={form.line1} onChange={set("line1")} required autoComplete="address-line1" maxLength={200} />
    <Field label="Address line 2 (optional)" value={form.line2} onChange={set("line2")} autoComplete="address-line2" maxLength={200} />
    <div className="two-up"><Field label="City" value={form.city} onChange={set("city")} required autoComplete="address-level2" maxLength={100} /><Field label="State or region" value={form.region} onChange={set("region")} autoComplete="address-level1" maxLength={100} /></div>
    <div className="two-up"><Field label="Postal code" value={form.postal} onChange={set("postal")} required autoComplete="postal-code" maxLength={20} />
      <label className="select-field">Country<select value={form.country} onChange={set("country")} required autoComplete="country"><option value="" disabled>Choose…</option>{Object.entries(COUNTRIES).map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label></div>
    <Field label="Phone for the courier (optional)" type="tel" value={form.phone} onChange={set("phone")} autoComplete="tel" maxLength={30} hint="Shared with the seller only to deliver this order." />
    <Field label="Name this address (optional)" value={form.label} onChange={set("label")} maxLength={60} placeholder="Home, Work…" />
    <SubmitButton busy={action.busy}>Save address</SubmitButton>
  </form>;
}
