"use client";
import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, Check, Headphones, ImagePlus, ScanLine, Smartphone, Upload, X } from "lucide-react";
import { ScanLens, useMotionPreferences } from "../components/motion-system";
import { RevealText } from "../components/ambient";
import type { ScanResult } from "../scan-types";
import Verdict from "../components/verdict";
import { AppFooter, Badge, ErrorNotice, SellerWhy, Working } from "../components/ui";

export default function Home() {
  const { reduced } = useMotionPreferences();
  const verdictPanel = useRef<HTMLElement>(null);
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
  const [dragging, setDragging] = useState(false);
  const [scanMode, setScanMode] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { void fetch("/api/transparency").then(response => response.ok ? response.json() : null).then(data => { if (data) setScanMode(data.modes?.scan ?? null); }).catch(() => {}); }, []);
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file); setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => {
    if (!loading) return;
    const timer = setInterval(() => setSeconds(value => value + 1), 1000);
    return () => clearInterval(timer);
  }, [loading]);
  function choose(next: File | null) {
    setResult(null); setError(""); setFile(null); setPreview("");
    if (input.current) input.current.value = "";
    if (!next) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(next.type)) { setError("Use a PNG, JPG or WebP screenshot."); return; }
    if (next.size > 8 * 1024 * 1024 || !next.size) { setError("Choose a non-empty image up to 8 MB."); return; }
    setFile(next);
  }
  async function sample(name = "headphones") {
    try {
      const response = await fetch(`/samples/${name}.png`);
      if (!response.ok) throw new Error("Sample unavailable.");
      choose(new File([await response.blob()], `${name}.png`, { type: "image/png" }));
    } catch { setError("Cannot load the sample. Try uploading a screenshot."); }
  }
  async function scan(edit = false) {
    if (!file || loading) return;
    setError(""); setLoading(true); setSeconds(0); setResult(null);
    if (window.matchMedia("(max-width: 800px)").matches) verdictPanel.current?.scrollIntoView({ behavior: reduced ? "instant" : "smooth", block: "start" });
    const query = new URLSearchParams({ owns_similar: String(owns) });
    if (edit) { query.set("title", title); query.set("price", price); query.set("merchant", merchant); }
    try {
      const response = await fetch(`/api/scan?${query}`, { method: "POST", headers: { "Content-Type": file.type }, body: file, signal: AbortSignal.timeout(110000) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message ?? "Scan failed. Try again.");
      const verdict = data as ScanResult;
      setResult(verdict); verdictPanel.current?.focus({ preventScroll: true }); setTitle(verdict.item.title ?? ""); setPrice(verdict.item.price ?? ""); setMerchant(verdict.item.merchant ?? "");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Scan failed. Try again."); }
    finally { setLoading(false); }
  }
  return <main id="main-content" className="scan-page">
    <div className="scan-intro"><div><h1><RevealText lines={["Is this the best price?", "Or wait for the group."]} /></h1><p>Screenshot a product page. Maxx finds what it costs elsewhere, then tells you to buy now,<br className="desktop-break" /> wait, skip it, or join a Bloc of people who want the same thing.</p></div><Badge tone={scanMode === "fixture" ? "warn" : "neutral"}>{scanMode === "fixture" ? "Fixture demo · no live prices" : scanMode === "live" ? "Live scan configured" : "Scan a product"}</Badge></div>
    <ol className="scan-steps" aria-label="Scan workflow"><li className={file ? "complete" : "current"}><span>{file ? <Check size={14} /> : <ImagePlus size={14} />}</span><span>{file ? "Screenshot ready" : "Add a screenshot"}</span></li><li className={result ? "complete" : loading ? "current" : ""}><span>{result ? <Check size={14} /> : <ScanLine size={14} />}</span><span>{result ? "Evidence ready" : loading ? "Checking the evidence" : "Check the evidence"}</span></li><li className={result ? "current" : ""}><span><ArrowUpRight size={14} /></span><span>Buy, wait or join a group</span></li></ol>
    <div className="scan-workspace">
      <section className="upload-workspace" aria-label="Upload a screenshot">
        <div className={`product-stage ${preview ? "has-preview" : ""} ${dragging ? "dragging" : ""}`} onDragOver={event => { event.preventDefault(); if (!loading) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); if (!loading) choose(event.dataTransfer.files[0] ?? null); }}>
          <AnimatePresence mode="wait">{preview ? <motion.div className="screenshot-preview" key={preview} initial={{ opacity: 0, scale: .98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}><img src={preview} alt="Your selected shopping screenshot" /><span className="stage-file-chip"><Check size={13} /> Ready to scan</span><span className="stage-caption"><ImagePlus size={13} /> Your screenshot</span><button className="preview-remove icon-button" onClick={() => { choose(null); input.current?.focus(); }} disabled={loading} aria-label="Remove selected screenshot"><X size={17} /></button></motion.div> : <motion.div className="stage-art" key="art" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><Image src="/artwork/camera-editorial-v2.png" alt="Illustrative silver camera on limestone" fill sizes="(max-width: 900px) 100vw, 52vw" preload /><span className="stage-caption">Illustrative artwork · start with any shopping screenshot</span></motion.div>}</AnimatePresence>
          {dragging && <div className="drop-overlay"><Upload size={30} /><strong>Drop your screenshot here</strong></div>}
          {loading && <div className="scan-sweep" aria-hidden="true" />}<span className="scan-corner top-left" aria-hidden="true" /><span className="scan-corner bottom-right" aria-hidden="true" />
        </div>
        <div className="upload-controls"><label className="upload-chooser"><Upload size={22} aria-hidden="true" /><span><strong>{file?.name ?? "Choose your shopping screenshot"}</strong><small>PNG, JPG or WebP · up to 8 MB</small></span><input ref={input} type="file" accept="image/png,image/jpeg,image/webp" disabled={loading} onChange={event => choose(event.target.files?.[0] ?? null)} /></label><motion.button whileTap={reduced ? undefined : { scale: .97 }} className="button primary scan-button" disabled={!file || loading} onClick={() => void scan()}><AnimatePresence mode="wait" initial={false}><motion.span key={loading ? "checking" : "ready"} initial={{ opacity: 0, y: reduced ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduced ? 0 : -8 }} transition={{ duration: reduced ? 0 : .14 }}>{loading ? "Checking screenshot…" : "Get my verdict"}</motion.span></AnimatePresence><ScanLine size={18} /></motion.button></div>
        <div className="sample-selector"><span>Try a sample</span><button aria-pressed={file?.name === "headphones.png"} disabled={loading} onClick={() => void sample()}><Headphones size={15} /> Headphones</button><button aria-pressed={file?.name === "phone.png"} disabled={loading} onClick={() => void sample("phone")}><Smartphone size={15} /> Phone</button><button aria-pressed={file?.name === "vacuum.png"} disabled={loading} onClick={() => void sample("vacuum")}><ScanLine size={15} /> Vacuum</button><small className="muted">Samples show made-up products, so a live scan finds nothing to compare. For real prices and links, upload a screenshot of your own cart.</small></div>
        <label className="ownership-checkbox"><input type="checkbox" checked={owns} disabled={loading} onChange={event => { setOwns(event.target.checked); setResult(null); }} /><span>I already own something similar</span></label>
        <p className="privacy small muted">Processed in memory. Live scans send the image to Nebius and product details to Tavily. Comparisons currently support USD.</p><SellerWhy />
      </section>
      <section ref={verdictPanel} tabIndex={-1} className="verdict-panel" aria-label="Your verdict" aria-busy={loading}>
        <AnimatePresence mode="wait">{loading ? <motion.div key="working" className="verdict-waiting" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><Working label="Checking your screenshot" seconds={seconds} /><ScanLens working /><h2>A closer look<br />before you commit.</h2><p>Reading the product and price, checking comparable listings, and calculating your Money Score.</p><p className="small muted">{scanMode === "fixture" ? "Replaying the selected synthetic sample." : "Provider calls may take a while. We’ll show the evidence when it returns."}</p></motion.div> : result ? <Verdict key={result.request_id} result={result} editForm={<form onSubmit={event => { event.preventDefault(); void scan(true); }}><label>Product title<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={300} /></label><label>Unit price in USD<input type="number" min="0.01" step="0.01" value={price} onChange={event => setPrice(event.target.value)} required /></label><label>Merchant<input value={merchant} onChange={event => setMerchant(event.target.value)} /></label><button className="button secondary" type="submit">Recheck these details</button></form>} /> : <motion.div key="empty" className="verdict-empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><div className="section-heading"><span>Your verdict</span><Badge>Ready when you are</Badge></div><ScanLens /><h2>The whole picture.<br />Before the purchase.</h2><p>See how your price compares, what the sources say, and whether buying together could be your next move.</p><ol className="journey-list"><li><span><ScanLine size={17} /></span><div><strong>Read your screenshot</strong><p>Product, exact variant and visible price.</p></div></li><li><span><Check size={17} /></span><div><strong>Look at the evidence</strong><p>Comparable listings, shipping and stock.</p></div></li><li><span><ArrowUpRight size={17} /></span><div><strong>Choose your next move</strong><p>Compare, wait or bring demand into a Bloc.</p></div></li></ol><p className="small muted">Choose a sample or upload a screenshot to get started.</p></motion.div>}</AnimatePresence>
        {error && <ErrorNotice message={error} retry={file ? () => void scan() : undefined} dismiss={() => setError("")} />}
      </section>
    </div><div className="sr-only" role="status" aria-live="polite">{result ? `Scan complete. ${result.recommendation.headline}` : file ? `${file.name} selected.` : ""}</div><AppFooter />
  </main>;
}
