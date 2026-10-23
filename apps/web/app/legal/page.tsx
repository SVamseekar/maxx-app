import type { Metadata } from "next";
import Link from "next/link";
import { SITE } from "../lib/site";
import { PageHero } from "../components/marketing";
import { DOCS } from "./docs";

export const metadata: Metadata = { title: "Policies · Maxx", description: "Every policy that governs Maxx, in plain language: terms, privacy, refunds, sellers, AI, security and accessibility." };
const GROUPS: { title: string; blurb: string; slugs: string[] }[] = [
  { title: "Using Maxx", blurb: "The rules for everyone.", slugs: ["terms", "acceptable-use", "privacy", "cookies"] },
  { title: "Buying", blurb: "Your money, your rights, and what to do when something goes wrong.", slugs: ["refunds", "consumer-rights", "payments", "ai"] },
  { title: "Selling", blurb: "What sellers promise and what is not allowed.", slugs: ["seller-terms", "prohibited"] },
  { title: "Trust and compliance", blurb: "How we keep Maxx safe and answerable.", slugs: ["security", "notice-and-action", "accessibility", "subprocessors", "imprint"] },
];
export default function Policies() {
  return <main id="main-content" className="doc-page">
    <PageHero eyebrow="Policies" title="Everything we promise, in one place.">Maxx is a marketplace where buyers and sellers deal with each other and we coordinate the payment. These policies say who is responsible for what. Last updated {SITE.updated}.</PageHero>
    {GROUPS.map(group => <section key={group.title} className="band" aria-labelledby={`${group.slugs[0]}-g`}><div className="band-head"><h2 id={`${group.slugs[0]}-g`}>{group.title}</h2><p>{group.blurb}</p></div><div className="policy-grid">{group.slugs.map(slug => { const doc = DOCS.find(item => item.slug === slug)!; return <Link key={slug} className="policy-card" href={`/legal/${slug}`}><h3>{doc.title}</h3><p>{doc.summary}</p></Link>; })}</div></section>)}
  </main>;
}
