import type { Metadata } from "next";
import PageEffects from "../components/page-effects";
import Link from "next/link";
import { SITE } from "../lib/site";
import { Band, PageHero, Table } from "../components/marketing";

export const metadata: Metadata = { title: "Contact · Maxx", description: "How to reach Maxx for support, privacy requests, sellers, security reports and legal matters." };

export default function Contact() {
  return <main id="main-content" className="info-page">
    <PageHero eyebrow="Contact" title="Talk to a person.">We read everything. Pick the address that fits and include the order or seller code if you have one.</PageHero>
    <Band id="addresses" title="Where to write">
      <Table head={["For", "Write to", "We reply"]} rows={[
        ["Help with an order, a refund or a problem", <a key="s" href={`mailto:${SITE.supportEmail}`}>{SITE.supportEmail}</a>, "Within 1 business day"],
        ["Selling on Maxx", <a key="se" href={`mailto:${SITE.sellerEmail}`}>{SITE.sellerEmail}</a>, "Within 2 business days"],
        ["Your data: access, export, delete, correct", <a key="p" href={`mailto:${SITE.privacyEmail}`}>{SITE.privacyEmail}</a>, "Within 1 month, usually sooner"],
        ["A security vulnerability", <a key="sec" href={`mailto:${SITE.securityEmail}`}>{SITE.securityEmail}</a>, "Acknowledged within 3 business days"],
        ["Report illegal content, or appeal a decision", <a key="l" href={`mailto:${SITE.legalEmail}`}>{SITE.legalEmail}</a>, "Within 14 days"],
        ["Anything else", <a key="h" href={`mailto:${SITE.email}`}>{SITE.email}</a>, "Within 3 business days"],
      ]} />
      <p className="small muted">These are placeholder addresses until Maxx has an operating entity. Operator details are on the <Link href="/legal/imprint">Legal notice</Link>.</p>
    </Band>
    <Band id="faster" title="Often faster" tone="raised"><ul className="plain-list">
      <li><strong>An order problem:</strong> open a problem report from the order in <Link href="/orders">Your orders</Link>. The seller is told at once and has 24 hours to respond.</li>
      <li><strong>Your data:</strong> Account settings has <em>Download my data</em> and <em>Delete my account</em>.</li>
      <li><strong>Accessibility:</strong> see the <Link href="/legal/accessibility">Accessibility statement</Link>.</li>
    </ul></Band>
    <PageEffects />
  </main>;
}
