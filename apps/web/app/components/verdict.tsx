"use client";
import Link from "next/link";
import { motion } from "motion/react";
import { ArrowDown, ArrowUpRight, Check, FileText, Pencil, ShieldCheck } from "lucide-react";
import type { ScanResult } from "../scan-types";
import { usd } from "../blocs/types";
import { hostOf, safeHref } from "../lib/safe-url";
import { priceComparison } from "../presentation";
import { useMotionPreferences } from "./motion-system";
import ScoreDial from "./score-dial";
import AgentCheckout from "./agent-checkout";
import { Badge, Disclosure } from "./ui";
import type { ReactNode } from "react";

export default function Verdict({ result, editForm }: { result: ScanResult; editForm: ReactNode }) {
  const { reduced } = useMotionPreferences();
  const comparison = priceComparison(result.item.price, result.item.currency, result.rows);
  const eligible = result.rows.filter(row => row.same_item && row.in_stock && row.shipping !== null);
  const values = eligible.map(row => Number(row.price) + Number(row.shipping));
  const observed = result.item.currency === "USD" && result.item.price ? Number(result.item.price) : null;
  const low = Math.min(...values, observed ?? Infinity), high = Math.max(...values, observed ?? -Infinity);
  const position = (value: number) => 4 + ((value - low) / (high - low || 1)) * 92;
  const deductions = [{ label: "Price difference", value: Number(result.score.price_gap) * 70 }, { label: "Already own similar", value: result.score.ownership_penalty }, { label: "Group opportunity", value: result.score.bloc_bonus }];
  return <motion.article className="verdict" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : .35 }}>
    <div className="section-heading"><span>Your verdict</span><Badge tone={result.mode === "fixture" ? "warn" : "accent"}>{result.mode === "fixture" ? "Demo prices" : "Live results"}</Badge></div>
    <h2 className="verdict-headline">{result.recommendation.headline}</h2><p className="verdict-explanation">{result.recommendation.explanation}</p>
    <div className="verdict-instrument"><ScoreDial value={result.score.value} /><div className="price-receipt"><div><span>Your screenshot price</span><strong>{result.item.currency === "USD" ? usd(result.item.price) : `${result.item.currency ?? "Unknown"} ${result.item.price ?? "—"}`}</strong></div><div><span>Best comparable delivered</span><strong>{usd(result.score.best)}</strong></div>{comparison ? <div className={`price-difference ${comparison.difference > 0 ? "positive" : ""}`}><ArrowDown size={21} aria-hidden="true" /><strong>{usd(Math.abs(comparison.difference))}</strong><span>{comparison.difference > 0 ? "lower elsewhere" : comparison.difference < 0 ? "below alternatives" : "matches the best"}</span></div> : <p className="small muted">A comparison needs a USD price, matching item, confirmed stock and known shipping.</p>}</div></div>
    <div className="evidence-quality"><ShieldCheck size={15} aria-hidden="true" /><span>{result.score.value === null ? "Not enough evidence to score" : result.score.low_confidence ? "Limited comparable evidence" : `${comparison?.trustedCount ?? eligible.length} comparable sources`}</span><span className="subtle-divider" /><span>Price competitiveness, not a probability</span></div>
    {comparison && observed !== null && high > low && <div className="price-scale" aria-label={`Best comparable delivered ${usd(comparison.best)}; your screenshot price ${usd(observed)}`}><div className="scale-labels"><span>{usd(low)}</span><span>{usd(high)}</span></div><div className="scale-line"><span className="scale-ticks" /><motion.span className="scale-marker best" initial={{ left: "4%" }} animate={{ left: `${position(comparison.best)}%` }} title={`Best comparable ${usd(comparison.best)}`} /><span className="scale-marker observed" style={{ left: `${position(observed)}%` }} title={`Your price ${usd(observed)}`} /></div><div className="scale-labels muted"><span>Comparable range</span><span>Your price in context</span></div></div>}
    <div className="detected-item"><div className="item-glyph"><FileText size={19} /></div><div><strong>{result.item.title ?? "Product not identified"}</strong><p>{result.item.variant ?? "Variant needs confirmation"} <span>from {result.item.merchant ?? "unknown merchant"}</span></p></div></div>
    <Disclosure title={<><Pencil size={15} /> Edit extracted details</>}>{editForm}</Disclosure>
    <div className="evidence-section"><div className="section-heading"><h3>Price evidence</h3><span className="small muted">{result.mode === "fixture" ? "Synthetic sources" : "Check at the source"}</span></div>{result.rows.length === 0 ? <p className="empty-copy">No trustworthy comparable price was found. Correct the details or try another screenshot.</p> : <ul className="source-list">{result.rows.map((row, index) => {
      const valid = row.same_item && row.in_stock && row.shipping !== null, total = row.shipping === null ? null : Number(row.price) + Number(row.shipping);
      return <li key={`${row.url}-${index}`} className={!valid ? "excluded-source" : ""}><div className="source-main"><span className="source-index">{index + 1}</span><div>{safeHref(row.url) ? <a href={safeHref(row.url)!} target="_blank" rel="noopener noreferrer nofollow">{result.mode === "fixture" ? `Demo store ${index + 1}` : hostOf(row.url)}<ArrowUpRight size={13} /></a> : <span>{hostOf(row.url)}</span>}<p>{row.title}</p></div><strong>{usd(total ?? row.price)}<small>{total === null ? "before shipping" : "delivered"}</small></strong></div><div className="source-flags"><span>{row.same_item ? <><Check size={11} /> Exact item</> : "Different variant · excluded"}</span><span>{row.in_stock ? "In stock" : "Stock unconfirmed · excluded"}</span><span>{row.shipping === null ? "Shipping unknown · excluded" : Number(row.shipping) === 0 ? "Free shipping" : `${usd(row.shipping)} shipping`}</span></div></li>;
    })}</ul>}</div>
    <Disclosure title="What shaped your score"><div className="score-breakdown">{deductions.map(deduction => <div key={deduction.label}><span>{deduction.label}</span><span className="deduction-track"><motion.span initial={{ width: 0 }} animate={{ width: `${deduction.value}%` }} transition={{ duration: reduced ? 0 : .55 }} /></span><strong>−{deduction.value.toFixed(deduction.value % 1 ? 1 : 0)}</strong></div>)}<div className="score-total"><span>Final Money Score</span><strong>{result.score.value ?? "Unscored"}</strong></div></div><p className="small muted">Higher means a more competitive price. A qualifying open Bloc with a lower target lowers this score to flag a group opportunity; it doesn’t guarantee a deal.</p></Disclosure>
    <AgentCheckout result={result} />
    {result.open_bloc_id && <Link className="button primary" href={`/blocs/${result.open_bloc_id}/room`}>Join the matching open Bloc <ArrowUpRight size={17} /></Link>}
    <Link className={`button ${result.open_bloc_id ? "secondary" : "primary"}`} href={`/blocs?title=${encodeURIComponent(result.item.title ?? "")}&price=${encodeURIComponent(result.item.price ?? "")}`}>Confirm product & create a Bloc <ArrowUpRight size={17} /></Link>
    {result.warnings.map((warning, index) => <p className="warning" key={index}>{warning}</p>)}
    <Disclosure title={`Provider activity · ${result.latency_ms} ms`}><p className="small muted">Request {result.request_id}</p>{result.calls.length === 0 ? <p className="small">Fixture replay. No provider calls. Live performance and cost are unmeasured.</p> : result.calls.map((call, index) => <div className="tool-row" key={index}><span>{call.provider} / {call.purpose}</span><Badge>{call.status}</Badge><span>{call.latency_ms} ms</span><small>{call.model ?? "search"} · cost {call.cost_usd == null ? "unmeasured" : `$${call.cost_usd} estimate`}</small></div>)}</Disclosure>
  </motion.article>;
}
