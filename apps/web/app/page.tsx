import type { Metadata } from "next";
import PageEffects from "./components/page-effects";
import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
import { Band, ButtonLink, CtaRow, Faq } from "./components/marketing";
import LiveBloc from "./components/live-bloc";
import DemoFilm from "./components/demo-film";
import { SITE } from "./lib/site";
import BuyingJourney from "./components/buying-journey";
import EditorialImage from "./components/editorial-image";

export const metadata: Metadata = {
  title: "Maxx · More buying power, together", description: "Find your product. Set your maximum. Join a group and watch seller agents compete for your collective demand.",
  openGraph: { title: "Maxx · More buying power, together", description: "Your next purchase has people behind it.", type: "website", siteName: "Maxx" },
};

export default function Home() {
  return <main id="main-content" className="info-page home-page">
    <section className="purchase-hero" aria-labelledby="home-h">
      <div className="purchase-heading"><h1 id="home-h">Want it.<br />Buy it together.</h1><div className="purchase-intro"><p>Your next purchase has people behind it. Set your price limit. Bring your demand together. Let seller agents compete for the group.</p><div className="hero-actions"><ButtonLink href="/blocs" primary>Find your Bloc</ButtonLink><Link className="text-action" href="/how-it-works">How it works <ArrowUpRight size={16} /></Link></div></div></div>
      <div className="purchase-stage"><figure className="purchase-art"><Image src="/artwork/collection-editorial-v2.png" alt="Original illustrative still life of a sneaker, camera, lamp and game controller on limestone" fill sizes="(max-width: 900px) 100vw, 65vw" preload /><figcaption>Things you want. A different way to buy them.<span>Illustrative product artwork</span></figcaption></figure><LiveBloc /></div>
      <div className="purchase-footnote"><span><ShieldCheck size={15} /> Your maximum stays your maximum.</span><span>Prototype · simulated sellers · no live payments</span><Link href="/trust">See how it works <ArrowUpRight size={14} /></Link></div>
    </section>
    <Band id="how" title="One purchase. More people on your side." intro="You choose what you want and what it is worth to you. Maxx brings the demand together.">
      <BuyingJourney />
    </Band>
    <section className="scan-editorial" aria-labelledby="screenshot-h"><div className="scan-photo"><EditorialImage kind="scan" /><span className="editorial-scan-frame" aria-hidden="true"><i /></span></div><div><p className="section-label">A second look, before you buy</p><h2 id="screenshot-h">See the product.<br />Know the price.</h2><p>Start with a screenshot. Get a price comparison, the supporting sources, and a clear next step.</p><ol className="visual-scan-steps"><li><span>01</span> Identify the exact item</li><li><span>02</span> Compare delivered prices</li><li><span>03</span> Buy, wait or join a Bloc</li></ol><ButtonLink href="/scan" primary>Check a price</ButtonLink></div></section>
    <DemoFilm />
    <section className="seller-editorial" aria-labelledby="seller-home-h"><div><p className="section-label">For sellers</p><h2 id="seller-home-h">Less guessing.<br />Demand you can see.</h2><p>Set your stock, your opening price, and a floor your agent cannot cross. Meet buyers who have already decided what they would pay.</p><div className="hero-actions"><ButtonLink href="/for-sellers" primary>Meet your next buyers</ButtonLink><Link className="text-action" href="/sell">Seller console <ArrowUpRight size={15} /></Link></div></div><div className="seller-visual"><EditorialImage kind="marketplace" /><div className="seller-fee"><span className="fee-number">{SITE.feePercent}<span>%</span></span><p>Platform fee when you sell.<br />No listing fee. No monthly fee.</p><Link href="/pricing#sellers">Fees and responsibilities <ArrowUpRight size={15} /></Link></div></div></section>
    <Band id="faq" title="Good questions. Clear answers."><Faq items={[
      { q: "Am I charged when I join?", a: "Joining creates a hold for your maximum when payments are enabled. You are charged only if you win, and only the allocated price. This prototype uses simulated payments or PayPal sandbox." },
      { q: "Who ships my purchase?", a: "The seller on your order. Maxx coordinates the group and payment; the seller ships and supports the goods. Check the shipping and refund terms before joining." },
      { q: "Is the negotiation real?", a: "You can follow actual recorded events from the app. Demo sellers and stock are simulated; live model calls are labelled separately. A deal is never guaranteed." },
    ]} /><CtaRow><ButtonLink href="/faq">More answers</ButtonLink><ButtonLink href="/under-the-hood">Inspect the evidence</ButtonLink></CtaRow></Band>
    <PageEffects />
  </main>;
}
