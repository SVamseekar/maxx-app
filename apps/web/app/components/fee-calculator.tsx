"use client";

import { useId, useState } from "react";
import { AnimatedNumber } from "./motion-system";
import { SITE } from "../lib/site";

export default function FeeCalculator() {
  const [amount, setAmount] = useState(100);
  const id = useId();
  const fee = Math.round(amount * Number(SITE.feePercent)) / 100;
  return <section className="fee-calculator" aria-labelledby={`${id}-title`}><div><p className="section-label">Seller payout calculator</p><h2 id={`${id}-title`}>See what stays yours.</h2><p>One sale. One transparent platform fee.</p><label htmlFor={id}>Example sale price <strong>${amount.toFixed(2)}</strong></label><input id={id} type="range" min={20} max={1000} step={10} value={amount} onChange={e => setAmount(Number(e.target.value))} aria-valuetext={`Sale price $${amount}`} /><div className="range-extents"><span>$20</span><span>$1,000</span></div></div><div className="fee-breakdown" aria-live="polite"><div><span>Your payout before PayPal fees</span><strong><AnimatedNumber value={amount - fee} currency /></strong></div><div className="fee-proportion" role="img" aria-label={`${100 - Number(SITE.feePercent)} percent seller payout, ${SITE.feePercent} percent platform fee`}><span style={{ flex: 100 - Number(SITE.feePercent) }} /><span style={{ flex: Number(SITE.feePercent) }} /></div><div className="fee-legend"><span><i />You keep {100 - Number(SITE.feePercent)}%</span><span><i />Maxx {SITE.feePercent}%</span></div><dl><div><dt>Buyer pays</dt><dd>${amount.toFixed(2)}</dd></div><div><dt>Maxx platform fee</dt><dd>${fee.toFixed(2)}</dd></div></dl><p>Illustrative estimate. PayPal fees and currency conversion may apply. Payout follows shipment.</p></div></section>;
}
