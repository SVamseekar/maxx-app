"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import {
  ArrowUpRight, BadgeCheck, Barcode, Bell, Bot, Camera, ChartLine, CircleDollarSign, Download, FileCheck2, Fingerprint, Gauge, Handshake, HandCoins,
  KeyRound, Landmark, ListChecks, Lock, MailCheck, MapPinned, MessageSquareWarning, PackageCheck, PackagePlus, Radar, Receipt, RefreshCcw, ScanLine,
  Search, ShieldBan, ShieldCheck, SlidersHorizontal, Store, Tag, Truck, Undo2, UserCheck, Users, Wallet,
} from "lucide-react";

type Item = { icon: ReactNode; title: string; body: string; demo?: boolean; href?: string };
type Category = { id: string; title: string; summary: string; items: Item[] };
type Audience = { id: "buyers" | "sellers"; label: string; heading: string; intro: string; categories: Category[]; cta: { href: string; label: string }[] };

const i = (Icon: typeof Bell) => <Icon size={18} aria-hidden="true" />;

const AUDIENCES: Audience[] = [
  {
    id: "buyers", label: "For buyers", heading: "Buy better, together.",
    intro: "From the screenshot of something you want to the parcel at your door: every step, and what protects you at each one.",
    cta: [{ href: "/scan", label: "Scan a screenshot" }, { href: "/blocs", label: "Browse open Blocs" }],
    categories: [
      { id: "decide", title: "Decide what to buy", summary: "Know if a price is good before you commit.", items: [
        { icon: i(ScanLine), title: "Screenshot scan", body: "Upload a screenshot of a product page; Maxx reads the product, price and seller.", href: "/scan" },
        { icon: i(Search), title: "Comparable delivered prices", body: "Prices from other shops for the exact model and variant, with shipping included." },
        { icon: i(Gauge), title: "Money Score", body: "One score for how good the deal is, calculated the same way every time, with its reasons shown." },
        { icon: i(ChartLine), title: "Target price", body: "A reference price from trusted independent sources, so you know what the group should aim for." },
      ] },
      { id: "together", title: "Buy together", summary: "Sellers compete for the whole group instead of one shopper.", items: [
        { icon: i(Users), title: "Blocs", body: "Join everyone who wants the same product, or start a new Bloc in one tap.", href: "/blocs" },
        { icon: i(SlidersHorizontal), title: "Your own maximum", body: "Set the most you would pay. It is a hard limit: you are never charged above it." },
        { icon: i(Bot), title: "AI negotiation you can watch", body: "A negotiator agent speaks for the group, round by round, in a live room.", demo: true },
        { icon: i(Store), title: "Seller listings", body: "Join Blocs that verified sellers opened for new products, before anyone else asks." },
        { icon: i(Undo2), title: "Leave any time before it closes", body: "Change your mind and your hold is released at once." },
      ] },
      { id: "pay", title: "Pay safely with PayPal", summary: "A hold, not a charge, until there is a deal.", items: [
        { icon: i(Lock), title: "PayPal hold", body: "PayPal reserves your maximum. Nothing is charged while the group forms.", demo: true },
        { icon: i(HandCoins), title: "Pay only the winning price", body: "Win and PayPal charges your allocated price; the rest of the hold is released." },
        { icon: i(RefreshCcw), title: "No deal, no charge", body: "If sellers do not meet the group's prices, every hold is released." },
        { icon: i(CircleDollarSign), title: "PYUSD option", body: "Pay a single checkout with PayPal's stablecoin, confirmed on-chain." },
        { icon: i(Handshake), title: "Agent checkout with a guard", body: "Let an agent buy a cheaper offer for you; it cannot spend more than you confirmed." },
        { icon: i(Receipt), title: "Receipts", body: "Every hold, charge, release and refund, with PayPal's own references.", href: "/receipts" },
      ] },
      { id: "delivery", title: "Delivery and orders", summary: "Your details go only to the seller who ships, and only after you win.", items: [
        { icon: i(MapPinned), title: "Address after you win", body: "Encrypted, shown only to the seller of that order, and wiped 90 days after it ends." },
        { icon: i(Truck), title: "Carrier tracking", body: "The carrier's own updates for your parcel, and delivery is detected automatically.", demo: true },
        { icon: i(PackageCheck), title: "Cancel before it ships", body: "Changed your mind after winning? Cancel for a full refund until the seller ships." },
      ] },
      { id: "protection", title: "Protection", summary: "Maxx holds the seller's money until the carrier shows they shipped.", items: [
        { icon: i(ShieldCheck), title: "Refund if it never ships", body: "Not shipped by the seller's deadline? You are refunded in full, automatically." },
        { icon: i(MessageSquareWarning), title: "Problem reports", body: "Report a problem within 60 days. The seller must reply in 24 hours or you are refunded." },
        { icon: i(UserCheck), title: "Checked sellers", body: "Sellers confirm their identity and are screened against sanctions lists before they sell.", demo: true },
        { icon: i(Landmark), title: "Who you bought from", body: "The seller's legal name, address and contact details, as EU and US law require." },
      ] },
      { id: "account", title: "Your account and privacy", summary: "Strong sign-in, and your data is yours to take or delete.", items: [
        { icon: i(KeyRound), title: "Passkeys and two-step", body: "Sign in with a passkey, an emailed link, or Google, Apple, Microsoft or GitHub; add an authenticator app." },
        { icon: i(ShieldBan), title: "New-device alerts", body: "An email when someone signs in from a device you have not used, and a log of activity." },
        { icon: i(Download), title: "Export or delete", body: "Download everything Maxx holds about you, or close your account.", href: "/account" },
        { icon: i(Bell), title: "Notifications", body: "An inbox for wins, shipments, refunds and replies; emails for anything about money or deadlines.", href: "/notifications" },
      ] },
    ],
  },
  {
    id: "sellers", label: "For sellers", heading: "Sell to groups that are ready to pay.",
    intro: "Verified once, then your offers and listings find buyers who have already put money on hold. You ship, the carrier confirms, you are paid.",
    cta: [{ href: "/sell", label: "Open the seller console" }, { href: "/for-sellers", label: "Why sell on Maxx" }],
    categories: [
      { id: "verify", title: "Get verified", summary: "One application, checked properly, so buyers can trust every seller.", items: [
        { icon: i(FileCheck2), title: "Trader details", body: "Legal name, address and contacts, collected as the EU Digital Services Act and US INFORM Act require." },
        { icon: i(MailCheck), title: "Payout email code", body: "Prove you control the PayPal email you are paid to; changing it needs a fresh sign-in check." },
        { icon: i(Fingerprint), title: "Identity check", body: "A government ID and a live selfie on the provider's own page; Maxx never stores the document.", demo: true },
        { icon: i(Radar), title: "Sanctions screening", body: "Names are checked against the US Treasury's OFAC lists, refreshed daily; a person reviews any match." },
      ] },
      { id: "demand", title: "Find demand", summary: "See what buyers want, and what they will pay, before you offer.", items: [
        { icon: i(ChartLine), title: "Demand curves", body: "How many buyers would pay at least each price, for every open Bloc." },
        { icon: i(ListChecks), title: "Standing offers", body: "One offer joins every future Bloc for the same product automatically." },
      ] },
      { id: "list", title: "List products", summary: "Open your own Bloc for a product nobody has asked for yet.", items: [
        { icon: i(PackagePlus), title: "Listings", body: "Publish a product with your units, floor and opening price; buyers can join right away." },
        { icon: i(Barcode), title: "Barcode check", body: "GTIN, UPC and EAN numbers are checked with GS1's check digit, so one product means one Bloc." },
        { icon: i(Tag), title: "Category and rules screen", body: "Prohibited goods are refused before they are published; administrators can take a listing down." },
      ] },
      { id: "negotiate", title: "Negotiate automatically", summary: "Your agent bargains for you, never past your limits.", items: [
        { icon: i(SlidersHorizontal), title: "Fixed rules", body: "Lower your price by the same step each round. Predictable, with no AI involved." },
        { icon: i(Bot), title: "AI agent", body: "Holds or concedes from each round's result, with a private note from you.", demo: true },
        { icon: i(ShieldCheck), title: "Hard limits on every bid", body: "Never below your floor or above your opening price, never higher than its last offer, never past your stock." },
      ] },
      { id: "ship", title: "Ship and get paid", summary: "Paid by carrier evidence, not by a button.", items: [
        { icon: i(Truck), title: "Checked tracking numbers", body: "Format and check digit verified for 12 carriers and international post; a number reused for another buyer is refused." },
        { icon: i(PackageCheck), title: "Carrier updates", body: "Every scan for every parcel, in your console and the buyer's.", demo: true },
        { icon: i(Wallet), title: "Paid on carrier evidence", body: "New sellers are paid on delivery; established sellers at the first carrier scan." },
        { icon: i(RefreshCcw), title: "Payouts followed to the end", body: "If PayPal cannot deliver a payout, you are told and it is sent again once you fix your email." },
      ] },
      { id: "problems", title: "Handle problems", summary: "Clear rules, the same for everyone.", items: [
        { icon: i(MessageSquareWarning), title: "Problem reports", body: "Reply within 24 hours, agree to refund in one click, or ask Maxx to decide." },
        { icon: i(BadgeCheck), title: "Strikes, not surprises", body: "Missed deadlines count against you; three suspend the account. Each one is notified." },
      ] },
      { id: "compliance", title: "Stay compliant", summary: "The paperwork marketplaces need, kept short.", items: [
        { icon: i(FileCheck2), title: "Tax id for high-volume sellers", body: "Asked for only after 200 sales and $5,000 in a year, as US law requires, and stored encrypted." },
        { icon: i(ListChecks), title: "Yearly confirmation", body: "Confirm your details once a year in a minute; you are reminded two weeks before." },
        { icon: i(Bell), title: "Notifications", body: "New orders, ship-by and reply reminders, payouts and decisions, by email and in your inbox.", href: "/notifications" },
      ] },
    ],
  },
];

const STATS = [
  { value: "5%", label: "Maxx fee, from the seller's side only" },
  { value: "$0", label: "charged to buyers when there is no deal" },
  { value: "24 h", label: "for a seller to answer a problem report" },
  { value: "60 days", label: "to report a problem with an order" },
];

/** The features, split by audience and grouped by category, with a jump list for each. */
export default function FeatureCatalog() {
  const [audience, setAudience] = useState<Audience["id"]>("buyers");
  useEffect(() => {
    const read = () => { const hash = window.location.hash.replace("#", ""); if (hash === "sellers" || hash === "buyers") setAudience(hash); };
    read(); window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);
  const current = AUDIENCES.find(a => a.id === audience)!;
  function choose(id: Audience["id"]) { setAudience(id); history.replaceState(null, "", `#${id}`); }
  return <>
    <div className="audience-switch" role="tablist" aria-label="Who the features are for">{AUDIENCES.map(a => <button key={a.id} type="button" role="tab" id={`aud-${a.id}`} aria-selected={audience === a.id} aria-controls="audience-panel" className={audience === a.id ? "is-selected" : ""} onClick={() => choose(a.id)} onKeyDown={event => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const next = a.id === "buyers" ? "sellers" : "buyers"; choose(next); document.getElementById(`aud-${next}`)?.focus(); } }} tabIndex={audience === a.id ? 0 : -1}>{a.label}</button>)}</div>
    <div id="audience-panel" role="tabpanel" aria-labelledby={`aud-${audience}`} className="feature-catalog">
      <header className="feature-head"><h2>{current.heading}</h2><p>{current.intro}</p></header>
      <nav className="feature-index" aria-label={`${current.label}: categories`}>{current.categories.map(c => <a key={c.id} href={`#${current.id}-${c.id}`}>{c.title}<span>{c.items.length}</span></a>)}</nav>
      {current.categories.map(category => <section key={category.id} id={`${current.id}-${category.id}`} className="feature-category" aria-labelledby={`${current.id}-${category.id}-h`}>
        <div className="feature-category-head"><h3 id={`${current.id}-${category.id}-h`}>{category.title}</h3><p>{category.summary}</p></div>
        <ul className="feature-grid">{category.items.map(item => <li key={item.title}>
          <span className="feature-icon">{item.icon}</span>
          <div><h4>{item.title}{item.demo && <span className="demo-tag" title="Runs as a clearly labelled stand-in in this demo until the provider is configured">demo stand-in</span>}</h4><p>{item.body}</p>{item.href && <Link href={item.href} className="feature-link">Open <ArrowUpRight size={13} aria-hidden="true" /></Link>}</div>
        </li>)}</ul>
      </section>)}
      <div className="feature-cta">{current.cta.map((link, index) => <Link key={link.href} className={index === 0 ? "button primary" : "button"} href={link.href}>{link.label} <ArrowUpRight size={15} aria-hidden="true" /></Link>)}</div>
    </div>
    <section className="feature-stats" aria-label="Commitments in numbers">{STATS.map(stat => <div key={stat.label}><strong>{stat.value}</strong><span>{stat.label}</span></div>)}</section>
    <p className="feature-footnote"><Camera size={14} aria-hidden="true" /> Items marked <span className="demo-tag">demo stand-in</span> run as clearly labelled simulators in this prototype (PayPal sandbox simulator, carrier tracking, identity checks, and a replay in place of the language model) until each provider's keys are configured. Nothing is hidden: the same code paths run either way.</p>
  </>;
}
