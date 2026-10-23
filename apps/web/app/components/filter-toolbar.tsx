"use client";

import { Search, X } from "lucide-react";
import { useId } from "react";
import { motion } from "motion/react";
import { useMotionPreferences } from "./motion-system";

export type FilterOption = { value: string; label: string; count?: number };

/** Shared, labelled filtering. Selection never moves focus or alters the source data. */
export default function FilterToolbar({ query, onQuery, filter, onFilter, options, count, label = "Search", placeholder = "Search…" }: {
  query: string; onQuery: (value: string) => void; filter: string; onFilter: (value: string) => void;
  options: FilterOption[]; count: number; label?: string; placeholder?: string;
}) {
  const id = useId();
  const { reduced } = useMotionPreferences();
  const dirty = query !== "" || filter !== options[0]?.value;
  return <div className="collection-tools">
    <div className="collection-toolbar">
      <div className="collection-search"><Search size={17} aria-hidden="true" /><label htmlFor={id} className="sr-only">{label}</label><input id={id} type="search" value={query} onChange={event => onQuery(event.target.value)} placeholder={placeholder} autoComplete="off" />{query && <button type="button" className="search-clear" onClick={() => { onQuery(""); document.getElementById(id)?.focus(); }} aria-label={`Clear ${label.toLowerCase()}`}><X size={15} /></button>}</div>
      {options.length > 1 && <div className="segmented-control" role="group" aria-label="Filter results">{options.map(option => <button type="button" key={option.value} aria-pressed={filter === option.value} onClick={() => onFilter(option.value)}>{filter === option.value && <motion.i className="filter-selection" layoutId={`${id}-selection`} transition={{ duration: reduced ? 0 : .22 }} />}<span className="filter-label">{option.label}</span>{option.count !== undefined && <span>{option.count}</span>}</button>)}</div>}
    </div>
    <div className="collection-meta"><span role="status" aria-live="polite">{count} {count === 1 ? "result" : "results"}{query && <> for “{query}”</>}</span>{dirty && <button type="button" className="text-action" onClick={() => { onQuery(""); onFilter(options[0]?.value ?? "all"); }}>Reset filters <X size={12} /></button>}</div>
  </div>;
}
