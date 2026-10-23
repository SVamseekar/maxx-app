import Link from "next/link";
export default function NotFound() {
  return <main id="main-content" className="recovery-page"><span className="recovery-code">404</span><h1>This page has moved<br />out of reach.</h1><p>The link may be old, or the address may be incomplete. Your next group purchase is still here.</p><div className="hero-actions"><Link className="button primary" href="/blocs">Explore Blocs</Link><Link className="button" href="/">Back to Maxx</Link></div></main>;
}
