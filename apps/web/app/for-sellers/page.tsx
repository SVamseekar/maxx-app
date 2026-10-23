import EditorialImage from "../components/editorial-image";
import PageEffects from "../components/page-effects";
import type { Metadata } from "next";
import FeeCalculator from "../components/fee-calculator";
import { RevealText } from "../components/ambient";
import { OfferCard, SellerBento, StatStrip } from "../components/seller-landing";
import { Band, ButtonLink, Callout, Steps, Table } from "../components/marketing";

export const metadata: Metadata = { title: "Sell on Maxx · Maxx", description: "Sell to groups of buyers who have already committed. Set a floor you never go below, get paid when you ship, and pay a fee only on sales." };

export default function ForSellers() {
  return <main id="main-content" className="info-page">
    <section className="seller-hero" aria-labelledby="sellers-h">
      <div className="seller-hero-copy">
        <p className="eyebrow">For sellers</p>
        <h1 id="sellers-h"><RevealText lines={["Sell to demand that", "is already committed."]} /></h1>
        <p className="lede">Every buyer in a Bloc has set a maximum price and put the money on hold with PayPal. You see the demand before you bid, you can never be pushed below your floor, and you are paid when you ship.</p>
        <div className="hero-actions"><ButtonLink href="/sell" primary>Start selling</ButtonLink><ButtonLink href="/legal/seller-terms">Read the Seller Agreement</ButtonLink></div>
      </div>
      <OfferCard />
    </section>
    <StatStrip />
    <Band id="why" title="Why sellers use Maxx"><SellerBento /></Band>
    <div id="earn" className="earn-block"><FeeCalculator /></div>
    <Band id="how" title="How selling works"><Steps variant="timeline" items={[
      { title: "Apply", body: "Give your trader details, shipping and return commitments, and certify you sell only lawful, new goods. Confirm your payout PayPal email with a code." },
      { title: "Get approved", body: "Verified sellers go live. Applications may be reviewed by a person first." },
      { title: "Publish an offer", body: "Pick a product with demand. Set units, a floor, an opening price and how fast your agent concedes." },
      { title: "Your agent negotiates", body: "In each Bloc your agent bargains within your limits. You watch results in the console." },
      { title: "Ship and get paid", body: "Buyers who win give an address. You ship with tracking and are paid, minus the fee." },
    ]} /></Band>
    <Band id="responsibility" title="What you are responsible for">
      <div className="split"><EditorialImage kind="fulfilment">The work behind every order.</EditorialImage><p>You are the seller of record. That means you are responsible for the goods and their description, packing, shipping and customs, delivery, returns and refunds, warranties, product safety, customer service and tax. Maxx does not ship, store, inspect or insure anything. We run the Bloc and the payment, and we protect buyers by refunding them if you do not meet your commitments.</p></div>
      <Table head={["Commitment", "Rule"]} rows={[
        ["Ship within", "The time you choose (1 to 14 days), with tracking. Late orders are refunded after 2 more days"],
        ["Reply to a problem report", "Within 24 hours, or the buyer is refunded"],
        ["Returns", "At least 14 days, following consumer law where your buyers live"],
        ["Strikes", "Each missed commitment is a strike. Three suspend your account"],
        ["Refunds after payout", "Deducted from your later payouts"],
      ]} />
      <Callout title="What we ask for">Legal and trading name, address, phone, support email, trade register number for EU companies, and your payout email. We show these trader details to buyers after they buy, as marketplace law requires, and we never show your payout details.</Callout>
    </Band>
    <section className="cta-panel" data-reveal aria-labelledby="sellers-cta-h">
      <div><h2 id="sellers-cta-h">Meet buyers who have already decided.</h2><p>Apply, publish a standing offer and let your agent do the bargaining inside the limits you set.</p></div>
      <div className="hero-actions"><ButtonLink href="/sell" primary>Open the seller console</ButtonLink><ButtonLink href="/pricing#sellers">Seller fees</ButtonLink><ButtonLink href="/legal/prohibited">Prohibited items</ButtonLink></div>
    </section>
    <PageEffects />
  </main>;
}
