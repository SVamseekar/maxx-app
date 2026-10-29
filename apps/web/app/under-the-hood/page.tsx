"use client";
import { RefreshCw } from "lucide-react";
import { Badge, ErrorNotice, PageIntro, Working } from "../components/ui";
import FilterToolbar from "../components/filter-toolbar";
import { matchesQuery } from "../lib/collection";
import { useCallback, useEffect, useState } from "react";
import { api } from "../blocs/types";
type Call = { request_id: string | null; provider: string; purpose: string; model: string | null; status: string; tokens: Record<string, number> | null; latency_ms: number; cost_usd: string | null; cost_status: string; rate_date: string | null };
type Report = { modes: Record<string, string>; configured_models: Record<string, string>; inference_host?: string; calls: Call[]; cost_status: string };
export default function UnderTheHood() {
  const [data, setData] = useState<Report | null>(null), [error, setError] = useState("");
  const [query, setQuery] = useState(""), [provider, setProvider] = useState("all"), [busy, setBusy] = useState(false);
  const load = useCallback(async () => { setError(""); setBusy(true); try { setData(await api<Report>("/api/transparency")); } catch (e) { setError(e instanceof Error ? e.message : "Cannot load metadata."); } finally { setBusy(false); } }, []);
  useEffect(() => { void load(); }, [load]);
  const visible = (data?.calls ?? []).filter(call => matchesQuery(`${call.provider} ${call.purpose} ${call.model ?? ""} ${call.request_id ?? ""} ${call.status}`, query) && (provider === "all" || call.provider === provider));
  const providers = [...new Set(data?.calls.map(call => call.provider) ?? [])];
  return <main id="main-content"><PageIntro title="The evidence behind Maxx" description="Actual provider activity, configured models and recorded costs. Inspect what happened, down to the request."><button disabled={busy} onClick={() => void load()}><RefreshCw size={14} className={busy ? "spin" : ""} /> {busy ? "Refreshing…" : "Refresh activity"}</button></PageIntro>
    <div className="notice-strip">Prompts, images, API keys and private seller state are never included in this activity view.</div>
    {error && <ErrorNotice message={error} retry={() => void load()} />}{!data && !error && <div className="loading-surface"><Working label="Loading provider activity" /></div>}
    {data && <><section className="provider-modes" aria-label="Configured modes">{Object.entries(data.modes).map(([role, mode]) => <article key={role}><h2>{role}</h2><Badge tone={mode === "fixture" ? "warn" : "neutral"}>{mode}</Badge><p>{mode === "fixture" ? "Replay data. No live provider calls." : "Check the recorded calls to verify availability."}</p></article>)}</section>
      <section className="technical-section"><h2>Configured models</h2><p>Configuration is not proof of availability. The records below show the model used and its response status.{data.inference_host && <> Every model call goes to Nebius Token Factory at <strong>{data.inference_host}</strong>.</>}</p><ul className="model-list">{Object.entries(data.configured_models).map(([role, model]) => <li key={role}><strong>{role}</strong><span>{model}</span></li>)}</ul></section>
      <section className="technical-section"><h2>Latest 200 calls</h2><p>Records can include injected test transports. Fixture flows make zero provider calls. Cost is an estimate from recorded tokens and configured rates, not a measured invoice. Missing usage remains unmeasured.</p>
        <FilterToolbar query={query} onQuery={setQuery} filter={provider} onFilter={setProvider} options={[{value:"all",label:"All providers"},...providers.map(value=>({value,label:value}))]} count={visible.length} label="Search provider activity" placeholder="Model, request, status or step…" />
        {visible.length === 0 ? <div className="empty-state"><h3>{data.calls.length ? "No matching calls" : "No provider calls yet"}</h3><p>{data.calls.length ? "Try another query or reset the filters." : "Live scans and negotiations record provider activity here. Fixture flows do not generate usage."}</p></div> : <div className="table-wrap call-table"><table><thead><tr><th scope="col">Provider / step</th><th scope="col">Model / request</th><th scope="col">Status</th><th scope="col">Tokens</th><th scope="col">Latency</th><th scope="col">Cost</th></tr></thead><tbody>{visible.map((call, i) => <tr key={`${call.request_id}-${i}`}><td>{call.provider}<br /><span className="muted">{call.purpose}</span></td><td>{call.model ?? "—"}<br /><span className="small muted">{call.request_id ?? "—"}</span></td><td><Badge>{call.status}</Badge></td><td>{call.tokens ? Object.entries(call.tokens).map(([key,value])=><div key={key}>{key}: {value.toLocaleString()}</div>) : "Unavailable"}</td><td>{call.latency_ms.toLocaleString()} ms</td><td>{call.cost_usd === null ? "Unmeasured" : `$${call.cost_usd} estimate`}<br /><span className="small muted">{call.rate_date ?? "No rate date"}</span></td></tr>)}</tbody></table></div>}
      </section></>}
  </main>;
}
