"use client";

import Image from "next/image";
import { useState } from "react";
import { motion } from "motion/react";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
import { useMotionPreferences } from "./motion-system";

const benefits = [
  { label: "Your choice", title: "Start with something you want.", body: "Find buyers of the exact same product." },
  { label: "Your limit", title: "You set the boundary.", body: "Choose the most you would pay." },
  { label: "Together", title: "Give sellers a reason to compete.", body: "Bring your demand to one buying group." },
];
export default function AuthShowcase({ signup }: { signup: boolean }) {
  const [selected, setSelected] = useState(0);
  const { reduced } = useMotionPreferences();
  const art = signup ? { src: "/artwork/sneaker-editorial-v2.png", alt: "Illustrative ivory and burnt-orange running shoes" } : { src: "/artwork/home-editorial-v2.png", alt: "Illustrative green lamp, coffee maker and ceramic cup" };
  return <aside className="auth-showcase" aria-label="Discover Maxx">
    <div className="auth-showcase-heading"><span>Buying, together.</span><ArrowUpRight size={24} strokeWidth={1.3} /></div>
    <h2>{signup ? <>A little more<br />within reach.</> : <>Good to have<br />you back.</>}</h2>
    <div className="auth-image-stage"><Image src={art.src} alt={art.alt} fill sizes="(max-width: 760px) 90vw, 40vw" preload /><span className="auth-art-credit">Original illustrative artwork</span></div>
    <div className="auth-category-picker" role="group" aria-label="Explore buying benefits">{benefits.map((item, index) => <button type="button" key={item.label} aria-pressed={index === selected} onClick={() => setSelected(index)}>{item.label}</button>)}</div>
    <motion.div className="auth-benefit" key={selected} initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : .25 }} aria-live="polite"><ShieldCheck size={18} /><div><strong>{benefits[selected].title}</strong><p>{benefits[selected].body}</p></div></motion.div>
  </aside>;
}
