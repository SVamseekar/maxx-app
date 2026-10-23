"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowUpRight } from "lucide-react";

export default function DemoFilm() {
  const video = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    const observer = new IntersectionObserver(entries => { if (!entries[0]?.isIntersecting) element.pause(); }, { threshold: .1 });
    const visibility = () => { if (document.hidden) element.pause(); };
    observer.observe(element); document.addEventListener("visibilitychange", visibility);
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", visibility); };
  }, []);
  return <section className="demo-film-section" aria-labelledby="film-h"><div className="film-heading"><div><p className="section-label">A look inside</p><h2 id="film-h">Follow the negotiation.</h2></div><p>From the product to the offers and the outcome. A recording of the Maxx prototype, with simulated sellers and prices.</p></div>
    {failed ? <div className="film-fallback"><p>The recording could not load. Explore the same experience in the demo lab.</p><Link className="button primary" href="/judge">Open demo lab</Link></div> : <video ref={video} controls playsInline preload="none" poster="/artwork/demo-poster.png" aria-label="Recorded Maxx product walkthrough, using simulated data" onError={() => setFailed(true)}><source src="/media/maxx-walkthrough.webm" type="video/webm" /><track kind="captions" src="/media/maxx-walkthrough.vtt" srcLang="en" label="English" default />Your browser cannot play this recording. Visit the demo lab instead.</video>}
    <div className="film-caption"><span>Recorded prototype · no live payments · no audio</span><Link href="/judge">Try it yourself <ArrowUpRight size={14} /></Link></div>
  </section>;
}
