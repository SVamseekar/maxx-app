"use client";
import { useState } from "react";
import FilterToolbar from "./filter-toolbar";
import { matchesQuery } from "../lib/collection";

type Group = { id: string; title: string; items: { q: string; a: string }[] };
export default function FaqExplorer({ groups }: { groups: Group[] }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const visible = groups.filter(group => category === "all" || group.id === category).map(group => ({ ...group, items: group.items.filter(item => matchesQuery(`${item.q} ${item.a}`, query)) })).filter(group => group.items.length);
  const count = visible.reduce((sum, group) => sum + group.items.length, 0);
  return <><FilterToolbar query={query} onQuery={setQuery} filter={category} onFilter={setCategory} options={[{value:"all",label:"All questions"},...groups.map(group => ({value:group.id,label:group.id === "orders" ? "Orders" : group.id === "agents" ? "AI agents" : group.id.charAt(0).toUpperCase()+group.id.slice(1)}))]} count={count} label="Search questions" placeholder="Search holds, shipping, refunds…" />
    {visible.map(group => <section className="band" key={group.id} id={group.id} aria-labelledby={`${group.id}-h`}><div className="band-head"><h2 id={`${group.id}-h`}>{group.title}</h2></div><div className="faq-list">{group.items.map(item => <details key={item.q} open={query.trim() ? true : undefined}><summary>{item.q}</summary><div><p>{item.a}</p></div></details>)}</div></section>)}
    {count === 0 && <div className="empty-state"><h2>No answers match that search</h2><p>Try a shorter phrase or reset the filters. You can also contact us below.</p></div>}
  </>;
}
