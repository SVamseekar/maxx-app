import EditorialImage from "../components/editorial-image";
import PageEffects from "../components/page-effects";
import BuyingJourney from "../components/buying-journey";
import MoneyExplainer from "../components/money-explainer";
import type { Metadata } from "next";
import { Bot, Hand, Lock, PackageCheck, Users, Wallet } from "lucide-react";
import { Band, ButtonLink, Callout, CtaRow, PageHero, Steps, Table } from "../components/marketing";

export const metadata: Metadata = { title: "How Maxx works · Maxx", description: "Set the most you would pay, join a group, let AI agents negotiate, and pay only the winning price. Step by step, with what happens to your money." };

export default function HowItWorks() {
  return <main id="main-content" className="info-page">
    <PageHero eyebrow="How it works" title="One group. One price. Your limit stays yours.">Maxx brings people who want the same product together, so sellers compete for the whole group instead of one shopper. Here is exactly what happens, including what happens to your money at each step.</PageHero>
    <BuyingJourney />
    <section className="exact-product-story"><EditorialImage kind="detail" /><div><h2>Exact product.<br />Shared demand.</h2><p>A Bloc is built around one model and variant. Match the details first, then set your own limit. Your choice of color, size or specification matters.</p><ButtonLink href="/blocs">Find your Bloc</ButtonLink></div></section>
    <Band id="steps" title="From screenshot to doorstep" intro="Six steps. You decide at the first four, and software handles the rest.">
      <Steps items={[
        { icon: <Users size={18} />, title: "1. Find or start a Bloc", body: <>A Bloc is a group of buyers of the exact same product. Browse open Blocs, or screenshot something you are about to buy: Maxx finds the product, checks the price elsewhere, and opens or joins a Bloc.</> },
        { icon: <Hand size={18} />, title: "2. Set your maximum", body: <>Choose the most you would pay, between half of the typical price and the typical price. That number is a hard limit. You are never charged above it.</> },
        { icon: <Lock size={18} />, title: "3. PayPal holds it", body: <>PayPal reserves your maximum with a hold. It is not a charge. Leave before the negotiation starts and the hold is released at once.</> },
        { icon: <Bot size={18} />, title: "4. Agents negotiate", body: <>When the Bloc closes, a negotiator agent speaks for the group and each seller has its own agent. You can watch every round. The final allocation is calculated by a fixed procedure, not by AI.</> },
        { icon: <Wallet size={18} />, title: "5. You pay the winning price", body: <>Win, and PayPal charges only your allocated price. The rest of the hold is released. No deal? Every hold is released and nobody pays.</> },
        { icon: <PackageCheck size={18} />, title: "6. The seller ships", body: <>You give a delivery address. The seller ships with tracking and is paid when they do. If they do not ship, you are refunded in full.</> },
      ]} />
    </Band>
    <Band id="money" title="What happens to your money" tone="raised">
      <MoneyExplainer />
      <Table head={["Moment", "Your money", "Who acts"]} rows={[
        ["You join", "A hold up to your maximum. Not charged", "You and PayPal"],
        ["You leave before the negotiation", "Hold released immediately", "You"],
        ["The Bloc has no deal", "Every hold released. $0 charged", "Maxx"],
        ["You win", "Only the allocated price is charged; the rest released", "Maxx, through PayPal"],
        ["The seller has not shipped", "Held by Maxx. You can cancel for a full refund", "You"],
        ["The seller ships", "The seller is paid, minus Maxx’s fee. You are not charged extra", "Maxx"],
        ["The seller never ships", "Order cancelled and refunded in full after their deadline", "Maxx"],
        ["Something is wrong after delivery", "Report a problem. The seller must answer in 24 hours or you are refunded", "You, then the seller, then Maxx"],
      ]} />
    </Band>
    <Band id="responsibility" title="Who is responsible for what">
      <Table head={["", "Maxx", "The seller"]} rows={[
        ["Running a fair Bloc and the negotiation", "Yes", "No"],
        ["Charging you only the winning price", "Yes", "No"],
        ["Holding your money until they ship, and refunding if they do not", "Yes", "No"],
        ["The product, its description, shipping, delivery and customs", "No", "Yes"],
        ["Returns, warranties and customer service for the goods", "No", "Yes"],
        ["Taxes on the sale", "No", "Yes"],
      ]} />
      <Callout title="Maxx is not the seller">We never ship, store or inspect goods. We make sure the money moves honestly and that sellers keep their promises, or you are refunded. Read the <a href="/legal/terms">Terms</a> and the <a href="/legal/refunds">refund policy</a>.</Callout>
    </Band>
    <Band id="agent" title="Buying alone? Let an agent find the cheaper offer.">
      <p>From a screenshot, the checkout agent proposes the cheapest offer it can verify: exactly the same item, in stock, with a known delivered price. You approve the exact total. A guard refuses any charge that differs from what you approved. Pay with PayPal or with PYUSD from your own wallet.</p>
      <CtaRow><ButtonLink href="/scan" primary>Try a screenshot</ButtonLink><ButtonLink href="/blocs">Browse open Blocs</ButtonLink><ButtonLink href="/trust">How your money is protected</ButtonLink></CtaRow>
    </Band>
    <PageEffects />
  </main>;
}
