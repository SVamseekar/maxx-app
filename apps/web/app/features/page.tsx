import type { Metadata } from "next";
import FeatureCatalog from "../components/feature-catalog";
import { PageHero } from "../components/marketing";

export const metadata: Metadata = {
  title: "Features · Maxx",
  description: "Everything Maxx does for buyers and sellers: price checks, group buying with AI negotiation, PayPal holds, carrier-verified shipping, seller verification and protection.",
};

export default function Features() {
  return <main id="main-content" className="info-page features-page">
    <PageHero eyebrow="Features" title="Everything Maxx does, in one place.">For buyers and for sellers, grouped the way you use it. Each feature says what it does in one line, and what protects you is spelled out with real numbers.</PageHero>
    <FeatureCatalog />
  </main>;
}
