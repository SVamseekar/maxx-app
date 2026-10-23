import MoneyExplainer from "../components/money-explainer";
import PageEffects from "../components/page-effects";
import type { Metadata } from "next";
import { Ban, Bot, Eye, Lock, RotateCcw, ShieldCheck, Truck } from "lucide-react";
import { Band, ButtonLink, Callout, CtaRow, Features, PageHero } from "../components/marketing";

export const metadata: Metadata = { title: "How Maxx protects your money · Maxx", description: "Holds not charges, a hard price limit, money held until the seller ships, automatic refunds, human review of disputes, and AI that cannot spend." };

export default function Trust() {
  return <main id="main-content" className="info-page">
    <PageHero eyebrow="Trust and safety" title="Your money is protected at every step.">Group buying only works if you can trust the group and the seller. These are the protections built into Maxx, what each one covers, and where our responsibility stops.</PageHero>
    <MoneyExplainer />
    <Band id="protections" title="Seven protections">
      <Features items={[
        { icon: <Lock size={20} />, title: "A hold, not a charge", body: "Joining reserves your maximum with PayPal. Nothing is taken unless you win, and a hold you leave before the negotiation is released at once." },
        { icon: <ShieldCheck size={20} />, title: "A limit that cannot be crossed", body: "You are charged the winning price, never above your maximum. The limit is enforced in code on the server and checked again before PayPal is asked to take the payment." },
        { icon: <Truck size={20} />, title: "Held until the seller ships", body: "For orders from real sellers, Maxx pays the seller only after they ship with a tracking number. No tracking, no payout." },
        { icon: <RotateCcw size={20} />, title: "Automatic refunds", body: "No address, no shipment in time, or no answer to your problem report within 24 hours: you are refunded in full to your PayPal." },
        { icon: <Eye size={20} />, title: "Agents you can watch", body: "Every negotiation is visible, labelled as AI, and decided by a fixed procedure. Agents cannot see who you are or spend your money." },
        { icon: <Ban size={20} />, title: "Verified sellers, accountable sellers", body: "Sellers give their trader details, confirm a payout address and certify they sell only lawful new goods. Missed commitments earn strikes; three suspend the account." },
        { icon: <Bot size={20} />, title: "Limits and a brake", body: "Caps on how much can be on hold, fresh identity checks for large amounts, a full audit log of every money decision, and the ability to pause all payments at once." },
      ]} />
    </Band>
    <Band id="limits" title="What Maxx does not do" tone="raised">
      <ul className="plain-list">
        <li><strong>We are not the seller.</strong> We do not make, ship, store, inspect or insure goods. The seller you buy from is responsible for the goods, delivery and returns.</li>
        <li><strong>We cannot promise a deal.</strong> A Bloc succeeds only if sellers offer a price within the group’s limits.</li>
        <li><strong>We do not replace your legal rights.</strong> Everything here is in addition to consumer law, PayPal’s terms and your bank’s protections.</li>
        <li><strong>The prototype is a prototype.</strong> Payments run on a simulator or PayPal’s sandbox. Sellers and most buyers in demo Blocs are simulated. A banner always says which mode you are in.</li>
      </ul>
      <Callout title="If something goes wrong">Open a problem report from your order. The seller has 24 hours to reply, and if you disagree a person at Maxx decides. See <a href="/legal/refunds">cancellations, refunds and problem reports</a>.</Callout>
    </Band>
    <CtaRow><ButtonLink href="/how-it-works" primary>How it works</ButtonLink><ButtonLink href="/legal/security">Security and disclosure</ButtonLink><ButtonLink href="/legal/consumer-rights">Your rights as a buyer</ButtonLink></CtaRow>
    <PageEffects />
  </main>;
}
