import SectionNav from "./section-nav";
import Link from "next/link";
import { FileText } from "lucide-react";
import { SITE } from "../lib/site";
import type { Block, Doc } from "../legal/types";
import { DOCS } from "../legal/docs";

const SEE: [string, string][] = [
  ["Prohibited and restricted items", "prohibited"], ["Payments, PayPal and PYUSD", "payments"], ["AI agents and automated decisions", "ai"], ["Security and responsible disclosure", "security"],
  ["Report content and appeal a decision", "notice-and-action"], ["Cancellations, refunds and problem reports", "refunds"], ["Acceptable Use Policy", "acceptable-use"], ["Seller Agreement", "seller-terms"], ["Privacy Policy", "privacy"],
  ["Terms of Service", "terms"], ["Legal notice", "imprint"], ["Service providers", "subprocessors"],
];

/** Turn the names of other policies inside a paragraph into links, so the documents work together. */
function linkify(text: string) {
  const parts: (string | React.ReactElement)[] = [];
  let rest = text, key = 0;
  while (rest) {
    let best: { index: number; name: string; slug: string } | null = null;
    for (const [name, slug] of SEE) { const index = rest.indexOf(name); if (index >= 0 && (!best || index < best.index || (index === best.index && name.length > best.name.length))) best = { index, name, slug }; }
    if (!best) { parts.push(rest); break; }
    if (best.index > 0) parts.push(rest.slice(0, best.index));
    parts.push(<Link key={key++} href={`/legal/${best.slug}`}>{best.name}</Link>);
    rest = rest.slice(best.index + best.name.length);
  }
  return parts;
}

function Body({ block }: { block: Block }) {
  if (typeof block === "string") return <p>{linkify(block)}</p>;
  if ("list" in block) return <ul>{block.list.map(item => <li key={item}>{linkify(item)}</li>)}</ul>;
  if ("note" in block) return <p className="doc-note">{block.note}</p>;
  const blank = block.table.head.every(cell => !cell);
  return <div className="table-wrap"><table>{!blank && <thead><tr>{block.table.head.map(cell => <th key={cell} scope="col">{cell}</th>)}</tr></thead>}<tbody>{block.table.rows.map((row, index) => <tr key={index}>{row.map((cell, i) => i === 0 && blank ? <th key={i} scope="row">{cell}</th> : <td key={i} data-label={block.table.head[i] || undefined}>{linkify(cell)}</td>)}</tr>)}</tbody></table></div>;
}

export default function DocView({ doc }: { doc: Doc }) {
  const others = DOCS.filter(other => other.slug !== doc.slug);
  return <main id="main-content" className="doc-page">
    <nav className="crumbs" aria-label="Breadcrumb"><Link href="/legal">Policies</Link><span aria-hidden="true">/</span><span aria-current="page">{doc.title}</span></nav>
    <header className="doc-head"><h1>{doc.title}</h1><p className="lede">{doc.summary}</p><p className="doc-meta"><FileText size={14} aria-hidden="true" /> For: {doc.audience} · Last updated {SITE.updated} · Version {SITE.version}</p></header>
    <aside className="callout callout-warn"><strong>Prototype notice</strong><p>Maxx is a prototype with no operating company and no live payments. This document describes how the service is designed to work and is a draft for review by a qualified lawyer before any public launch. It is not legal advice.</p></aside>
    <div className="doc-layout">
      <aside className="doc-toc"><h2>On this page</h2><SectionNav items={doc.sections.map(section => ({id:section.id,label:section.title}))} /></aside>
      <article className="doc-body">{doc.sections.map(section => <section key={section.id} id={section.id} aria-labelledby={`${section.id}-h`}><h2 id={`${section.id}-h`}>{section.title}</h2>{section.body.map((block, index) => <Body key={index} block={block} />)}</section>)}</article>
    </div>
    <nav className="doc-more" aria-label="Related policies"><h2>Other policies</h2><ul>{others.map(other => <li key={other.slug}><Link href={`/legal/${other.slug}`}>{other.title}</Link></li>)}</ul></nav>
  </main>;
}
