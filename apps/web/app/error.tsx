"use client";
import Link from "next/link";
export default function ErrorPage({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return <main id="main-content" className="recovery-page"><span className="dialog-kicker">Connection interrupted</span><h1>Let’s try that again.</h1><p>This page could not finish loading. Retry to reload it. If you were making a payment, check your receipts before starting another.</p><div className="hero-actions"><button className="button primary" onClick={retry}>Try again</button><Link className="button" href="/receipts">Check receipts</Link></div></main>;
}
