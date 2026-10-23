import Link from "next/link";
import { SITE } from "../lib/site";
import { ModeNotice } from "./mode-notice";

const COLUMNS: { title: string; links: { href: string; label: string }[] }[] = [
  { title: "Buy together", links: [
    { href: "/blocs", label: "Open Blocs" }, { href: "/scan", label: "Scan a screenshot" }, { href: "/features#buyers", label: "Features for buyers" }, { href: "/how-it-works", label: "How it works" },
    { href: "/trust", label: "How your money is protected" }, { href: "/pricing", label: "Pricing and fees" }, { href: "/faq", label: "Questions" },
  ] },
  { title: "Sell to groups", links: [
    { href: "/for-sellers", label: "Why sell on Maxx" }, { href: "/features#sellers", label: "Features for sellers" }, { href: "/sell", label: "Seller console" }, { href: "/legal/seller-terms", label: "Seller Agreement" },
    { href: "/legal/prohibited", label: "Prohibited items" }, { href: "/pricing#sellers", label: "Seller fees and payouts" },
  ] },
  { title: "Trust and safety", links: [
    { href: "/legal/refunds", label: "Refunds and problems" }, { href: "/legal/consumer-rights", label: "Your rights as a buyer" }, { href: "/legal/payments", label: "Payments, PayPal and PYUSD" },
    { href: "/legal/ai", label: "AI agents" }, { href: "/legal/security", label: "Security and disclosure" }, { href: "/legal/notice-and-action", label: "Report content, appeal" },
  ] },
  { title: "Legal", links: [
    { href: "/legal/terms", label: "Terms of Service" }, { href: "/legal/privacy", label: "Privacy Policy" }, { href: "/legal/cookies", label: "Cookies" },
    { href: "/legal/acceptable-use", label: "Acceptable Use" }, { href: "/legal/subprocessors", label: "Service providers" }, { href: "/legal/accessibility", label: "Accessibility" }, { href: "/legal/imprint", label: "Legal notice" },
  ] },
  { title: "Company", links: [
    { href: "/about", label: "About Maxx" }, { href: "/contact", label: "Contact" }, { href: "/judge", label: "Demo lab" }, { href: "/under-the-hood", label: "Under the hood" }, { href: "/legal", label: "All policies" },
  ] },
];

export default function SiteFooter() {
  return <footer className="site-footer" aria-label="Site footer">
    <div className="footer-inner">
      <div className="footer-brand">
        <Link href="/" className="wordmark" aria-label="Maxx home">maxx<span className="brand-dot" /></Link>
        <p>{SITE.tagline} Name your price, join a group, and let AI agents bargain with sellers. PayPal holds your money until you win.</p>
        <ModeNotice />
      </div>
      <nav className="footer-columns" aria-label="Footer">
        {COLUMNS.map(column => <div key={column.title}><h2>{column.title}</h2><ul>{column.links.map(link => <li key={link.href}><Link href={link.href}>{link.label}</Link></li>)}</ul></div>)}
      </nav>
    </div>
    <div className="footer-base"><span>© {new Date().getFullYear()} Maxx · Prototype</span><span>Maxx is a marketplace platform. Sellers ship and support what they sell; Maxx does not. <Link href="/legal/terms">Terms</Link> · <Link href="/legal/privacy">Privacy</Link></span></div>
  </footer>;
}
