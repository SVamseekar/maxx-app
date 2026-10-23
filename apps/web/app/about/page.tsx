import EditorialImage from "../components/editorial-image";
import PageEffects from "../components/page-effects";
import type { Metadata } from "next";
import { Band, ButtonLink, Callout, CtaRow, Features, PageHero } from "../components/marketing";

export const metadata: Metadata = { title: "About Maxx", description: "Why shoppers should not bargain alone, how Maxx works, and what is real in this prototype." };

export default function About() {
  return <main id="main-content" className="info-page">
    <PageHero eyebrow="About" title="Shoppers bargain alone. Sellers should have to bargain with all of them.">Every shopper chooses between paying the sticker price or waiting for a sale. Maxx adds a third option: join everyone else who wants the same thing, and let sellers compete for the group.</PageHero>
    <EditorialImage kind="collective">Individual wants. Collective demand.</EditorialImage>
    <Band id="idea" title="The idea"><p>Sellers will cut a price for volume they can count on. Buyers will commit to a limit when their money is safe. Maxx puts the two together: buyers set a private maximum and a PayPal hold reserves it, AI agents negotiate openly, and the buyer pays only the winning price. If there is no deal, the holds vanish and nobody has lost anything.</p></Band>
    <Band id="principles" title="What we will not compromise on" tone="raised"><Features items={[
      { title: "Your limit is a limit", body: "No agent, seller or bug may charge you above the maximum you chose. We check it twice and test it." },
      { title: "Honest about what is real", body: "Every screen says whether payments are simulated, in the PayPal sandbox, or live. Simulated sellers and offers are labelled." },
      { title: "Sellers answer for their goods", body: "Maxx is not the seller and does not pretend to be. We make sellers accountable by holding the money until they ship, refunding when they do not, and suspending those who keep failing." },
      { title: "AI that cannot spend", body: "Agents negotiate inside limits set by people. They cannot move money, and a fixed procedure, not a model, decides the outcome." },
    ]} /></Band>
    <Band id="status" title="Where Maxx is today"><Callout title="A prototype" tone="warn">Maxx is a working prototype built for a hackathon. Payments run in a simulator or PayPal’s sandbox. There is no operating company, no live payments and no real fulfilment. What you can try end to end: joining a Bloc with a hold, a negotiation, partial capture, seller onboarding, orders with shipping and refunds, disputes, agent checkout and PYUSD verification. What a launch would still need: PayPal marketplace approval, seller identity verification, legal review in each country, and an independent security and accessibility audit.</Callout></Band>
    <CtaRow><ButtonLink href="/blocs" primary>Browse Blocs</ButtonLink><ButtonLink href="/for-sellers">Sell on Maxx</ButtonLink><ButtonLink href="/under-the-hood">Under the hood</ButtonLink></CtaRow>
    <PageEffects />
  </main>;
}
