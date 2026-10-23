"use client";
import FilterToolbar from "../components/filter-toolbar";
import ProductIdentity from "../components/product-identity";
import { matchesQuery } from "../lib/collection";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Users } from "lucide-react";
import { AppFooter, Badge, ErrorNotice, PageIntro, Working } from "../components/ui";
import { useAuth } from "../components/auth";
import { request } from "../lib/client";
import { loginPath } from "../lib/auth-helpers";
import { statusLabel } from "../presentation";
import { usd, type Bloc } from "../blocs/types";

export default function MyBlocs() {
  const { user, status } = useAuth();
  const router = useRouter();
  const [blocs, setBlocs] = useState<Bloc[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  useEffect(() => { if (status === "ready" && !user) router.replace(loginPath("/my-blocs")); }, [status, user, router]);
  async function load() { setError(""); try { setBlocs(await request<Bloc[]>("/api/me/blocs")); } catch (cause) { setError(cause instanceof Error ? cause.message : "Cannot load your Blocs."); } }
  useEffect(() => { if (user) void load(); }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const visible = (blocs ?? []).filter(b => matchesQuery(b.title, query) && (filter === "all" || (filter === "active" ? ["OPEN", "NEGOTIATING"].includes(b.status) : ["SETTLED", "FAILED"].includes(b.status))));
  return <main id="main-content">
    <PageIntro title="Your Blocs." description="Every group you created or joined, with your own limit and the outcome."><Link className="button primary" href="/blocs">Find more Blocs <ArrowUpRight size={15} /></Link></PageIntro>
    {error && <ErrorNotice message={error} retry={() => void load()} />}
    {!blocs && !error && <div className="loading-surface"><Working label="Loading your Blocs" /></div>}
    {blocs && blocs.length === 0 && <div className="empty-state"><Users size={28} /><h2>No Blocs yet.</h2><p>Join a Bloc or create one for the exact product you want. Your commitments and results will collect here.</p><Link className="button primary" href="/blocs">Browse Blocs</Link></div>}
    {blocs && blocs.length > 0 && <><FilterToolbar query={query} onQuery={setQuery} filter={filter} onFilter={setFilter} options={[{value:"all",label:"All Blocs"},{value:"active",label:"Active"},{value:"completed",label:"Completed"}]} count={visible.length} label="Search your Blocs" />{visible.length === 0 && <div className="empty-state"><h2>No matching groups</h2><p>Try another product or reset the filters above.</p></div>}</>}
    <section className="bloc-grid" aria-label="Your Blocs">{visible.map(bloc => {
      const mine = [...bloc.members].reverse().find(member => member.user_id === "me" && member.status !== "LEFT");
      return <Link key={bloc.id} className="bloc-card" href={`/blocs/${bloc.id}/room`}>
        <div className="card-top"><ProductIdentity title={bloc.title} /><Badge tone={bloc.status === "OPEN" ? "good" : bloc.status === "FAILED" ? "warn" : "accent"}>{statusLabel(bloc.status)}</Badge></div>
        <h2>{bloc.title}</h2>
        <p className="scenario-label">{bloc.viewer_is_owner ? "You created this Bloc" : "You joined this Bloc"}</p>
        <div className="card-price"><div><span>Your maximum</span><strong>{mine ? usd(mine.max_price) : "Left"}</strong></div><div><span>{mine?.status === "WIN" ? "You paid" : "Typical price"}</span><strong>{usd(mine?.status === "WIN" ? mine.final_price : bloc.typical_price)}</strong></div></div>
        <p>{mine?.status === "WIN" ? `Allocated from seller ${mine.seller_id}. Check Receipts for payment details.` : mine?.status === "BELOW_CLEARING" ? "Your maximum could not secure an allocation." : mine?.status === "RELEASED" ? "Commitment released. No deal this time." : mine ? "Waiting for the negotiation." : "You are no longer in this Bloc."}</p>
        <div className="card-link">Open negotiation room <ArrowUpRight size={17} /></div>
      </Link>;
    })}</section>
    <AppFooter />
  </main>;
}
