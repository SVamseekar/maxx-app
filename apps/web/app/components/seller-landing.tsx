import type { CSSProperties, ReactNode } from "react";
import { BadgeCheck, Banknote, Check, TrendingUp, Truck } from "lucide-react";
import { CountUp } from "./page-effects";
import { SITE } from "../lib/site";

/** Sections for the seller landing page. Illustrations are decorative and always labelled as simulated. */

const fee = Number(SITE.feePercent);

/** A standing offer whose price walks down and stops at the seller's floor. CSS only; static when motion is reduced. */
export function OfferCard() {
  return <aside className="offer-card" data-reveal aria-label="Illustration of a standing offer. The numbers are simulated.">
    <header><span className="offer-live">Standing offer</span><span className="offer-tag">Illustration</span></header>
    <h2>Demo headphones · Black</h2>
    <div className="offer-demand">
      <div><strong>601</strong><span>buyers committed</span></div>
      <div><strong>$200</strong><span>typical price</span></div>
    </div>
    <div className="floor-meter" aria-hidden="true">
      <div className="floor-track">
        <span className="floor-fill" />
        <span className="floor-line"><em>Your floor · $150</em></span>
        <span className="floor-price"><b /></span>
      </div>
      <div className="floor-scale"><span>$200</span><span>$120</span></div>
    </div>
    <ol className="offer-rounds">
      <li><span>Opening</span><strong>$199</strong></li>
      <li><span>Round 2</span><strong>$176</strong></li>
      <li><span>Round 3</span><strong>$158</strong></li>
      <li className="holds"><span><Check size={13} aria-hidden="true" /> Floor holds</span><strong>$150</strong></li>
    </ol>
    <footer>Your agent can never offer below your floor. Simulated numbers for illustration.</footer>
  </aside>;
}

export function StatStrip() {
  const tiles: { value: number; prefix?: string; suffix?: string; label: string }[] = [
    { value: fee, suffix: "%", label: "Fee, taken only when you sell" },
    { value: 0, prefix: "$", label: "Listing or monthly fees" },
    { value: 14, suffix: " days", label: "Longest you can take to ship" },
    { value: 24, suffix: "h", label: "To reply to a problem report" },
  ];
  return <div className="stat-strip">{tiles.map(tile => <div key={tile.label} className="stat-tile" data-reveal><strong><CountUp value={tile.value} prefix={tile.prefix} suffix={tile.suffix} /></strong><span>{tile.label}</span></div>)}</div>;
}

function Feature({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return <article className="seller-feature" data-reveal><span className="feature-icon" aria-hidden="true">{icon}</span><h3>{title}</h3><p>{children}</p></article>;
}

const bar = (height: string): CSSProperties => ({ "--h": height } as CSSProperties);
const dot = (index: number): CSSProperties => ({ "--i": index } as CSSProperties);

/** Two features that are easier to show than to describe, then the rest as plain ruled columns. */
export function SellerBento() {
  return <>
    <div className="seller-pair">
      <article className="seller-proof" data-reveal>
        <div className="seller-proof-visual" aria-hidden="true"><div className="buyer-dots">{Array.from({ length: 40 }, (_, i) => <i key={i} className={i < 31 ? "on" : ""} style={dot(i)} />)}</div><p>One dot per buyer. Filled dots have committed.</p></div>
        <h3>Volume you can count</h3>
        <p>Buyers in a Bloc want the exact same product, and their money is already reserved. No chasing, no abandoned carts.</p>
      </article>
      <article className="seller-proof" data-reveal>
        <div className="seller-proof-visual" aria-hidden="true"><div className="ladder"><span style={bar("100%")} /><span style={bar("82%")} /><span style={bar("66%")} /><span style={bar("54%")} /><span style={bar("54%")} /><em>Your floor</em></div><p>Each round the price falls, then stops at your floor.</p></div>
        <h3>A floor that cannot be broken</h3>
        <p>You set the lowest price you will accept. Your agent can never offer below it or beyond your stock, whatever happens in the negotiation.</p>
      </article>
    </div>
    <div className="seller-features">
      <Feature icon={<TrendingUp size={22} />} title="Standing offers">Publish once. Your offer joins every Bloc for that product, and you can pause it at any time.</Feature>
      <Feature icon={<Banknote size={22} />} title="Fee only on sales">{fee}% of each sale, taken from your payout. No listing or monthly fees.</Feature>
      <Feature icon={<Truck size={22} />} title="Paid when you ship">Mark the order shipped with a tracking number and you are paid by PayPal Payouts. No waiting for delivery.</Feature>
      <Feature icon={<BadgeCheck size={22} />} title="Trusted by buyers">Verified trader details and clear commitments earn buyers’ confidence. Buyers see your return policy after they buy.</Feature>
    </div>
  </>;
}
