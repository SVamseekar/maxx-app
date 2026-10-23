"use client";


import { useId, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Check, LockKeyhole, Users, Undo2, Camera, Footprints, LampDesk } from "lucide-react";
import { AnimatedNumber, useMotionPreferences } from "./motion-system";
import { PRODUCT_EXAMPLES } from "../lib/product-examples";

const categoryIcons = [Footprints, Camera, LampDesk];
const steps = [
  { title: "Find your people", short: "Find", body: "Different wishlists. A shared way to buy. Choose a category, then bring buyers of the exact same product together." },
  { title: "Name your limit", short: "Set a limit", body: "Try the slider. Choose the most you would pay and see how your limit changes the example outcome." },
  { title: "Let sellers compete", short: "Negotiate", body: "Compare the example offers against your limit. In a real Bloc, seller agents negotiate within their price and stock boundaries." },
  { title: "See where you stand", short: "Your outcome", body: "Your limit carries through every step. An allocation below it means you pay that price. Otherwise, your full hold is released." },
];

export default function BuyingJourney() {
  const [step, setStep] = useState(0);
  const [selected, setSelected] = useState(0);
  const [ceiling, setCeiling] = useState<number>(PRODUCT_EXAMPLES[0].limit);
  const id = useId();
  const { reduced } = useMotionPreferences();
  const product = PRODUCT_EXAMPLES[selected];
  const CategoryIcon = categoryIcons[selected];
  const won = ceiling >= product.offer;
  const offers = [product.offer + 30, product.offer + 15, product.offer];
  function choose(index: number) { setSelected(index); setCeiling(PRODUCT_EXAMPLES[index].limit); }
  function move(index: number) { setStep(index); document.getElementById(`${id}-tab-${index}`)?.focus(); }
  return <div className="buying-journey journey-v2">
    <div className="journey-tabs" role="tablist" aria-label="Explore the buying process">{steps.map((item, index) => <button key={item.short} role="tab" id={`${id}-tab-${index}`} aria-selected={step === index} aria-controls={`${id}-panel`} tabIndex={step === index ? 0 : -1} onClick={() => setStep(index)} onKeyDown={event => {
      const next = event.key === "ArrowRight" ? (step + 1) % 4 : event.key === "ArrowLeft" ? (step + 3) % 4 : event.key === "Home" ? 0 : event.key === "End" ? 3 : null;
      if (next !== null) { event.preventDefault(); move(next); }
    }}><span className="journey-index">0{index + 1}</span>{item.short}{step === index && <motion.span className="journey-underline" layoutId={`${id}-active`} transition={{ duration: reduced ? 0 : .3 }} />}</button>)}</div>
    <div className="journey-category-bar"><span>Try a purchase</span><div role="group" aria-label="Example product category">{PRODUCT_EXAMPLES.map((item, index) => <button key={item.id} aria-pressed={selected === index} onClick={() => choose(index)}><span style={{ background: item.color }} />{item.category}</button>)}</div><small>Illustrative prices & artwork</small></div>
    <div className="journey-panel" role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-tab-${step}`} tabIndex={0}>
      <div className={`journey-scene scene-${product.id}`}>
        <AnimatePresence mode="wait" initial={false}><motion.div className={`journey-frame journey-frame-${step}`} key={step} initial={{ opacity: 0, y: reduced ? 0 : 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduced ? 0 : -10 }} transition={{ duration: reduced ? 0 : .25 }}>
          {step === 0 && <div className="product-assembly">
            <div className="product-fan" aria-label={`${product.category} selected`}>{PRODUCT_EXAMPLES.map((item, index) => { const Icon = categoryIcons[index]; const offset = (index - selected + 3) % 3; const side = offset === 2 ? -1 : offset; return <motion.div className={`fan-photo ${side === 0 ? "is-front" : ""}`} key={item.id} initial={reduced ? false : { opacity: 0, y: 25 }} animate={{ opacity: side === 0 ? 1 : .65, y: Math.abs(side) * 18, x: `${side * 57}%`, rotate: side * 11, scale: side === 0 ? 1 : .83 }} transition={{ duration: reduced ? 0 : .5, delay: reduced ? 0 : index * .06 }} style={{ zIndex: side === 0 ? 3 : 1 }}><div className={`category-art category-art-${item.id}`}><Icon size={100} strokeWidth={.85} aria-hidden="true" /><p>{item.name}</p></div><span>{item.category}</span></motion.div>; })}</div>
            <div className="assembly-route" aria-hidden="true"><motion.svg viewBox="0 0 300 44" fill="none"><motion.path d="M25 2v12q0 8 8 8h109q8 0 8 8v12M275 2v12q0 8-8 8H158q-8 0-8 8M150 2v40" stroke="currentColor" strokeWidth="1.5" initial={{ pathLength: reduced ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: reduced ? 0 : .65, delay: reduced ? 0 : .2 }} /></motion.svg></div>
            <motion.div className="group-ticket" initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reduced ? 0 : .35 }}><Users size={23} strokeWidth={1.3} /><div><strong>One exact product. One Bloc.</strong><span>Find others with the same item in mind.</span></div><Check size={17} /></motion.div>
          </div>}
          {step === 1 && <div className="ceiling-scene"><div className="demo-product-mini"><CategoryIcon size={34} strokeWidth={1.2} aria-hidden="true" /><span>{product.category}<strong>Your example purchase</strong></span><LockKeyhole size={20} /></div><label htmlFor={`${id}-limit`}>Your maximum</label><strong><AnimatedNumber value={ceiling} currency /></strong><input id={`${id}-limit`} type="range" min={product.min} max={product.max} step={5} value={ceiling} onChange={event => setCeiling(Number(event.target.value))} aria-valuetext={`$${ceiling}, illustrative price limit`} /><div className="range-extents"><span>${product.min}</span><span>${product.max}</span></div><p>Move the slider. You set the boundary.</p><span className="example-hold"><LockKeyhole size={14} /> Reserved, not charged</span></div>}
          {step === 2 && <div className="offers-scene"><div className="offers-scene-head"><Users size={23} /><span>Your limit <b>${ceiling}</b></span></div>{offers.map((price, index) => <div className={`example-offer ${price <= ceiling ? "within-limit" : "above-limit"}`} key={price}><span>Seller {String.fromCharCode(65 + index)}<small>{price <= ceiling ? "Within your limit" : "Above your limit"}</small></span><div><motion.i initial={{ width: reduced ? `${price / product.max * 100}%` : "0%" }} animate={{ width: `${price / product.max * 100}%` }} transition={{ duration: reduced ? 0 : .65, delay: reduced ? 0 : index * .14 }} /><strong>${price}</strong></div></div>)}<p>Example offers for {product.category.toLowerCase()}.<br />Actual allocation also depends on available stock.</p></div>}
          {step === 3 && <div className="outcome-scene">{won ? <motion.svg viewBox="0 0 80 80" fill="none" aria-hidden="true"><circle cx="40" cy="40" r="37" stroke="currentColor" strokeOpacity=".2" /><motion.path d="m24 40 11 11 22-24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: reduced ? 0 : .6 }} /></motion.svg> : <Undo2 size={50} strokeWidth={1.2} />}<span>{won ? "Example allocation · you pay" : "No offer within your limit · you pay"}</span><strong><AnimatedNumber value={won ? product.offer : 0} currency /></strong><div className="outcome-equation"><span>${ceiling} reserved</span><ArrowRight size={14} /><span>${won ? ceiling - product.offer : ceiling} released</span></div><p>{won ? "A price inside your boundary." : "Your boundary held. No charge."}<br /><b>This is an illustration, not a live allocation.</b></p></div>}
        </motion.div></AnimatePresence>
      </div>
      <div className="journey-explanation"><div className="journey-step-progress" aria-hidden="true">{steps.map((_, i) => <span key={i} className={i <= step ? "is-complete" : ""} />)}</div><AnimatePresence mode="wait" initial={false}><motion.div className="journey-copy" key={step} initial={{ opacity: 0, y: reduced ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reduced ? 0 : .18 }}><span className="section-label">0{step + 1} / 04</span><h3>{steps[step].title}</h3><p>{steps[step].body}</p></motion.div></AnimatePresence><div className="journey-proof"><Check size={16} /><span>{["Explore footwear, cameras and home", "Your private limit. Your decision.", "Clear offers, recorded in the room", "An itemised payment receipt"][step]}</span></div><button className="button primary journey-next" onClick={() => move((step + 1) % 4)}>{step === 3 ? "Try another scenario" : "Next step"}<ArrowRight size={16} /></button></div>
    </div>
  </div>;
}
