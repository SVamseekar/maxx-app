import type { Metadata } from "next";
import PageEffects from "../components/page-effects";
import FaqExplorer from "../components/faq-explorer";
import { SITE } from "../lib/site";
import { ButtonLink, CtaRow, PageHero } from "../components/marketing";

export const metadata: Metadata = { title: "Questions · Maxx", description: "Straight answers about holds, charges, sellers, shipping, refunds, AI agents, PYUSD and the prototype." };

export default function Questions() {
  return <main id="main-content" className="info-page">
    <PageHero eyebrow="Questions" title="Straight answers.">If your question is not here, write to {SITE.supportEmail}.</PageHero>
    <FaqExplorer groups={[
{id:"buying",title:"Buying in a Bloc",items:[
      { q: "Am I charged when I join?", a: "No. PayPal places a hold for your maximum price. It reserves the money but takes none of it. You are charged only if you win, and then only the allocated price." },
      { q: "Can I be charged more than my maximum?", a: "No. Your maximum is a hard limit, enforced on our server and checked again before PayPal is asked to take payment." },
      { q: "What if the group does not get a deal?", a: "Every hold is released and nobody pays. Blocs can fail: sellers will not always offer a price within the group’s limits." },
      { q: "Can I leave?", a: "Yes, until the negotiation starts. Your hold is released immediately. After the negotiation starts your maximum is locked for that Bloc." },
      { q: "How long does a hold last?", a: "PayPal holds last up to 29 days, but Blocs normally finish within an hour or so of closing. A hold that PayPal ends early means you cannot be charged for that Bloc." },
      { q: "Who sets the typical price and the target?", a: "The typical price is the reference for the product. The target is a reference taken from trusted independent delivered prices when available. It is not a promise that the group will get it." },
    ]},
{id:"orders",title:"After you win",items:[
      { q: "Who ships my order?", a: "The seller named on your order. Maxx does not ship, store or inspect goods. We tell the seller where to ship once you give an address, and we pay them after they ship." },
      { q: "What if the seller never ships?", a: "Give your address within the deadline (7 days). The seller must ship within the time they committed to, plus a 2 day grace period. If they do not, the order is cancelled and you are refunded in full." },
      { q: "Can I cancel?", a: "Yes, until the seller marks the order shipped. You get a full refund to your PayPal." },
      { q: "What if the item is wrong, damaged or never arrives?", a: "Open a problem report from the order within 60 days. The seller must reply within 24 hours or you are refunded. If you disagree, a person at Maxx decides." },
      { q: "Can I return it?", a: "Every seller must allow returns for at least 14 days, and consumer law may give you more rights. The seller handles returns and shows its policy in its trader details." },
      { q: "Who sees my address?", a: "Only the seller you bought from, only for that order. It is encrypted at rest and wiped 90 days after the order finishes. Other buyers never see who you are." },
    ]},
{id:"agents",title:"AI agents",items:[
      { q: "Is there a real person negotiating for me?", a: "No. The negotiation is carried out by software agents, and every message from one is labelled as an agent. A fixed procedure, not an AI model, decides who gets which unit at which price." },
      { q: "Can an agent spend my money or break my limit?", a: "No. Agents cannot spend. They cannot make you pay above your maximum or make a seller sell below its floor. Those limits are enforced in code." },
      { q: "Does the AI see my identity?", a: "No. The negotiator sees the group’s demand curve, not names. A screenshot you scan is read by an AI model in live mode and is not stored." },
      { q: "What if the AI gets it wrong?", a: "You confirm the product and set your maximum, and you approve any checkout total yourself, so the worst outcome is bounded by what you chose. You can ask for a human review of any result." },
    ]},
{id:"sellers",title:"Selling",items:[
      { q: "How do I sell?", a: "Apply with your trader details, confirm your payout PayPal email with a code, then publish a standing offer for a product: units, a floor price you will never go below, an opening price and a negotiating style." },
      { q: "What does it cost?", a: `${SITE.feePercent}% of each sale, taken from your payout. No listing or monthly fees.` },
      { q: "When am I paid?", a: "When you mark an order shipped with a tracking number. A newly changed payout address may wait before it is paid." },
      { q: "Is Maxx responsible for shipping or returns?", a: "No. You are the seller of record and responsible for the goods, shipping, returns, warranties, customer service and taxes. See the Seller Agreement." },
      { q: "What are strikes?", a: "Orders you do not ship in time and problem reports you do not answer in 24 hours earn a strike and cause a refund. Three strikes suspend your account." },
    ]},
{id:"payments",title:"Payments and the prototype",items:[
      { q: "Is real money moving?", a: "Not yet. Maxx is a prototype. Payments run in a simulator or in PayPal’s sandbox, and a banner on every page says which. Live PayPal is not enabled." },
      { q: "Can I pay with crypto?", a: "You can pay a checkout with PYUSD, a US dollar stablecoin issued by Paxos, from your own wallet. Maxx only reads the blockchain to confirm the payment and holds no keys. It cannot be used for Bloc holds, and blockchain payments cannot be reversed by Maxx." },
      { q: "Are the other buyers and sellers real?", a: "In demo Blocs, most buyers and the sellers are simulated and labelled as such. Real accounts can join and real sellers can onboard." },
      { q: "How do I delete my data?", a: "Account settings has Download my data and Delete my account. See the Privacy Policy for what is kept and why." },
    ]}
]} />
    <CtaRow><ButtonLink href="/how-it-works" primary>How it works</ButtonLink><ButtonLink href="/trust">Money protection</ButtonLink><ButtonLink href="/contact">Contact us</ButtonLink></CtaRow>
    <PageEffects />
  </main>;
}
