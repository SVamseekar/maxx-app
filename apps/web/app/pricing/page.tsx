import FeeCalculator from "../components/fee-calculator";
import PageEffects from "../components/page-effects";
import type { Metadata } from "next";
import { SITE } from "../lib/site";
import { Band, ButtonLink, Callout, CtaRow, PageHero, Table } from "../components/marketing";

export const metadata: Metadata = { title: "Pricing and fees · Maxx", description: "Buyers pay no fee. Sellers pay a percentage only when they sell. No listing fees, no subscriptions required." };

export default function Pricing() {
  return <main id="main-content" className="info-page">
    <PageHero eyebrow="Pricing" title="Free for buyers. Sellers pay only when they sell.">There are no listing fees and no monthly fees. Maxx earns a percentage of each sale, taken from the seller’s payout, so the price a buyer is allocated is the price a buyer pays.</PageHero>
    <FeeCalculator />
    <Band id="buyers" title="For buyers">
      <Table head={["", "Cost"]} rows={[
        ["Joining a Bloc and the PayPal hold", "Free"],
        ["Leaving a Bloc, a Bloc with no deal, or a released hold", "Free"],
        ["The allocated price when you win", "That price only. No Maxx fee, shipping or tax is added on top"],
        ["Cancelling before the seller ships, or a refund", "Free. The full amount returns to your PayPal"],
        ["Checkout agent", "Free"],
      ]} />
    </Band>
    <Band id="sellers" title="For sellers" tone="raised">
      <Table head={["", "Cost"]} rows={[
        ["Applying, verification and standing offers", "Free"],
        ["Maxx fee on each sale", <strong key="f">{SITE.feePercent}% of the sale price</strong>],
        ["When the fee is taken", "From your payout, only for orders that ship"],
        ["Unshipped or refunded orders", "No fee. Refunds after payout are deducted from later payouts"],
        ["PayPal’s own fees and currency conversion", "As in your PayPal account terms"],
      ]} />
      <Callout title={`Example at ${SITE.feePercent}%`}>A buyer is allocated a unit at $100.00. When you ship, you receive ${(100 - Number(SITE.feePercent)).toFixed(2)} and Maxx keeps ${Number(SITE.feePercent).toFixed(2)}. The buyer paid $100.00 and nothing else.</Callout>
    </Band>
    <Band id="plus" title="Maxx Plus (optional)">
      <p>Plus is an optional subscription billed through PayPal. In the prototype it raises the checkout agent’s per-order limit from $500 to $2,000. It does not change how Blocs work or anyone’s price.</p>
      <Table head={["Plan", "Price"]} rows={[["Weekly", "$6.99 per week"], ["Yearly", "$49 per year"]]} />
    </Band>
    <Band id="limits" title="Limits that apply to everyone" tone="raised">
      <Table head={["Limit", "Default"]} rows={[
        ["A single PayPal hold", "$1,000"],
        ["Total open holds per account", "$3,000 across up to 10 holds"],
        ["Agent checkout per order", "$500 ($2,000 with Plus)"],
        ["Identity re-check required above", "$300 for a hold, $200 for a checkout"],
      ]} />
      <p className="small muted">Limits protect accounts and money and may change. They are set when the service is configured.</p>
    </Band>
    <CtaRow><ButtonLink href="/blocs" primary>Browse Blocs</ButtonLink><ButtonLink href="/for-sellers">Sell on Maxx</ButtonLink><ButtonLink href="/legal/payments">Payments policy</ButtonLink></CtaRow>
    <PageEffects />
  </main>;
}
