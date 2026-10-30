"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, Users } from "lucide-react";
import { request } from "../lib/client";
import { usd, type BlocSummary } from "../blocs/types";
import { statusLabel } from "../presentation";
import { useMoneyConfig, moneyLabel } from "../lib/money";
import { AnimatedNumber } from "./motion-system";
import { useServerReady } from "./server-wake";

/** Every displayed metric comes from the selected Bloc. No decorative demand data. */
export default function LiveBloc() {
  const money = useMoneyConfig();
  const [bloc, setBloc] = useState<BlocSummary | null | undefined>(undefined);
  const ready = useServerReady();
  useEffect(() => {
    if (!ready) return;
    let live = true;
    request<BlocSummary[]>("/api/blocs").then(rows => { if (live) setBloc(rows.filter(row => row.status === "OPEN" && row.buyers > 0).sort((a, b) => b.buyers - a.buyers)[0] ?? rows.filter(row => row.buyers > 0).sort((a, b) => b.buyers - a.buyers)[0] ?? rows[0] ?? null); }).catch(() => { if (live) setBloc(null); });
    return () => { live = false; };
  }, [ready]);
  if (!bloc) return <aside className="live-purchase" aria-busy={bloc === undefined}><span className="section-label">The collective advantage</span><h2>Your purchase.<br />With company.</h2><p>{bloc === undefined ? "Finding a group on this server…" : "Start a Bloc for your exact product and bring buyers together."}</p><Link className="button primary" href="/blocs">Explore Blocs <ArrowUpRight size={17} /></Link></aside>;
  return <aside className="live-purchase" aria-label="A buying group on this server">
    <div className="live-purchase-top"><span className="section-label">On Maxx now</span><span className="live-purchase-status">{statusLabel(bloc.status)}</span></div>
    <h2>{bloc.title}</h2><div className="collective-count"><Users size={25} strokeWidth={1.2} /><strong><AnimatedNumber value={bloc.buyers} /></strong><span>{bloc.id.startsWith("demo-") ? <>simulated<br />buyers</> : <>buyers<br />together</>}</span></div>
    <dl className="purchase-values"><div><dt>Typical price</dt><dd>{usd(bloc.typical_price)}</dd></div><div><dt>Reference target</dt><dd>{usd(bloc.target_price)}</dd></div></dl>
    <p className="live-purchase-note">A target, not a guaranteed price. Each buyer sets their own maximum.</p>
    <Link className="button primary" href={`/blocs/${bloc.id}/room`}>Meet the group <ArrowUpRight size={17} /></Link><small>{moneyLabel(money)} · {bloc.id.startsWith("demo-") ? "demo crowd" : "real buyers"} · {bloc.mode === "fixture" ? "replayed offers" : "live Nemotron agents"}</small>
  </aside>;
}
