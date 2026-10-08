"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import type { ScanResult } from "./scan-types";

const money = (value: string | number | null) => value === null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value));

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [owns, setOwns] = useState(false);
  const [loading, setLoading] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ScanResult | null>(null);
  const [title, setTitle] = useState("");
  const [price, setPrice] = useState("");
  const [merchant, setMerchant] = useState("");

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => {
    if (!loading) return;
    const timer = setInterval(() => setSeconds(s => s + 1), 1000);
    return () => clearInterval(timer);
  }, [loading]);

  function choose(next: File | null) {
    setResult(null); setError(""); setFile(null); setPreview("");
    if (!next) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(next.type)) { setError("Use a PNG, JPG or WebP screenshot."); return; }
    if (next.size > 8 * 1024 * 1024 || !next.size) { setError("Choose a non-empty image up to 8 MB."); return; }
    setFile(next);
  }
  async function sample() {
    try {
      const response = await fetch("/samples/headphones.png");
      if (!response.ok) throw new Error("Sample unavailable.");
      choose(new File([await response.blob()], "headphones.png", { type: "image/png" }));
    } catch { setError("Cannot load the sample. Try uploading a screenshot."); }
  }
  async function scan(edit = false) {
    if (!file) return;
    setError(""); setLoading(true); setSeconds(0); setResult(null);
    const query = new URLSearchParams({ owns_similar: String(owns) });
    if (edit) { query.set("title", title); query.set("price", price); query.set("merchant", merchant); }
    try {
      const response = await fetch(`/api/scan?${query}`, { method: "POST", headers: { "Content-Type": file.type }, body: file, signal: AbortSignal.timeout(110000) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message ?? "Scan failed. Try again.");
      const verdict = data as ScanResult;
      setResult(verdict); setTitle(verdict.item.title ?? ""); setPrice(verdict.item.price ?? ""); setMerchant(verdict.item.merchant ?? "");
    } catch (e) { setError(e instanceof Error ? e.message : "Scan failed. Try again."); }
    finally { setLoading(false); }
  }

  return <main>
    <header><a href="/" className="wordmark" aria-label="Maxx home">maxx<span>✳</span></a><Link href="/blocs">Explore demo Blocs</Link><Link href="/judge">Judge mode</Link><Link href="/under-the-hood">Under the hood</Link></header>
    <div className="workspace">
      <section className="upload-panel" aria-label="Upload a screenshot">
        <h1>Before you buy,<br/>run it by Maxx.</h1>
        <p className="intro">A screenshot. A price check. One smarter move.</p>
        <label className="upload"><span className="upload-icon">+</span><strong>{file ? file.name : "Choose your shopping screenshot"}</strong><span>PNG, JPG or WebP · up to 8 MB</span><input type="file" accept="image/png,image/jpeg,image/webp" disabled={loading} onChange={e => choose(e.target.files?.[0] ?? null)}/></label>
        {preview && <div className="preview"><img src={preview} alt="Your selected shopping screenshot"/></div>}
        <label className="checkbox"><input type="checkbox" checked={owns} disabled={loading} onChange={e => { setOwns(e.target.checked); setResult(null); }}/><span>I already own something similar</span></label>
        <button className="primary" disabled={!file || loading} onClick={() => void scan()}>{loading ? "Checking your screenshot…" : "Get my verdict"}</button>
        <button className="sample" disabled={loading} onClick={() => void sample()}>Try a sample screenshot</button>
        <p className="privacy">Screenshots are processed in memory. Live scans send the image to Nebius and product details to Tavily. USD comparisons only.</p>
      </section>
      <section className="verdict-panel" aria-label="Your verdict" aria-busy={loading}>
        {loading && <div className="pending" role="status"><div className="spinner"/><h2>Looking for your smartest move.</h2><p>Reading the product and price, checking comparable listings, then calculating your score.</p><p>{seconds}s elapsed. Provider calls can take a while.</p></div>}
        {error && <div className="error" role="alert"><h2>Let’s try that again.</h2><p>{error}</p><button onClick={() => void scan()} disabled={!file || loading}>Retry scan</button></div>}
        {!result && !loading && !error && <div className="empty"><span className="receipt">$?</span><h2>A good deal should<br/>stand up to a second look.</h2><p>Your Money Score, recommendation and price sources will appear here.</p><ol><li>Read the product and visible price</li><li>Find comparable prices with source links</li><li>Calculate the score and your next move</li></ol></div>}
        {result && <article>
          <div className={`mode ${result.mode}`}>{result.mode === "fixture" ? "Fixture replay · no live prices or model calls" : "Live provider results"}</div>
          <div className="verdict-top"><div><p className="muted">Your Money Score</p><div className="score">{result.score.value ?? "—"}<small>/100</small></div><p className="confidence">{result.score.value === null ? "Not enough evidence to score" : result.score.low_confidence ? "Low confidence" : "Based on comparable listings"}</p></div><span className="move">{result.recommendation.primary}</span></div>
          <h2>{result.recommendation.headline}</h2><p>{result.recommendation.explanation}</p>
          <div className="item"><strong>{result.item.title ?? "Unreadable product"}</strong><p>{result.item.currency === "USD" ? money(result.item.price) : `${result.item.currency ?? "Unknown currency"} ${result.item.price ?? "—"}`} <span>at {result.item.merchant ?? "—"}</span></p><p className="muted">{result.item.variant ?? "Variant not identified"}</p></div>
          <details><summary>Edit extracted details</summary><form onSubmit={e => { e.preventDefault(); void scan(true); }}><label>Product title<input value={title} onChange={e => setTitle(e.target.value)} required maxLength={300}/></label><label>Unit price in USD<input type="number" min="0.01" step="0.01" value={price} onChange={e => setPrice(e.target.value)} required/></label><label>Merchant<input value={merchant} onChange={e => setMerchant(e.target.value)}/></label><button type="submit">Recheck these details</button></form></details>
          <Link className="bloc-link" href={`/blocs?title=${encodeURIComponent(result.item.title ?? "")}&price=${encodeURIComponent(result.item.price ?? "")}`}>Confirm this product & create a Bloc</Link>
          {result.open_bloc_id && <Link className="bloc-link" href={`/blocs/${result.open_bloc_id}/room`}>Join the matching open Bloc</Link>}
          <h3>Price evidence</h3>
          {result.rows.length === 0 ? <p>No trustworthy comparable price was found.</p> : <ul className="sources">{result.rows.map((row, i) => <li key={i}><a href={row.url} target="_blank" rel="noopener noreferrer">{row.title}<span>View source ↗</span></a><strong>{money(row.price)}</strong><p>{row.shipping === null ? "Shipping unknown" : `${money(row.shipping)} shipping`} · {row.in_stock ? "In stock" : "Stock unconfirmed"} · {row.same_item ? "Same item" : "Excluded variant"}</p></li>)}</ul>}
          {result.warnings.map((warning, i) => <p className="warning" key={i}>{warning}</p>)}
          <details><summary>How the score works</summary><p>A higher score means a more competitive price. Price gap subtracts up to 70 points; owning a similar item subtracts 15. A lower target in a matching open Bloc subtracts 15.</p><p>Price gap: {(Number(result.score.price_gap) * 70).toFixed(2)} points · Ownership: {result.score.ownership_penalty} points · Group deal: {result.score.bloc_bonus} points</p><p>Best comparable total: {money(result.score.best)}. Unknown shipping, different variants and unconfirmed stock are excluded.</p></details>
          <details><summary>Under the hood · {result.latency_ms} ms</summary><p>Request {result.request_id}</p>{result.calls.length === 0 ? <p>Fixture replay. No provider calls. Cost and live latency unmeasured.</p> : result.calls.map((call, i) => <p key={i}>{call.provider} / {call.purpose}: {call.model ?? "search"} · {call.status} · {call.latency_ms} ms · tokens {call.tokens ? JSON.stringify(call.tokens) : "unavailable"} · cost {call.cost_usd === null || call.cost_usd === undefined ? "unmeasured" : `$${call.cost_usd} estimate`}</p>)}</details>
        </article>}
      </section>
    </div>
    <footer>Scan, join a Bloc, watch the negotiation. Demo commitments only; payments deferred.</footer>
  </main>;
}
