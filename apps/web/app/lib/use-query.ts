"use client";
import { useEffect, useState } from "react";

/** Read the query string after hydration. Avoids useSearchParams' Suspense requirement. */
export function useQuery(): URLSearchParams | null {
  const [query, setQuery] = useState<URLSearchParams | null>(null);
  useEffect(() => { setQuery(new URLSearchParams(window.location.search)); }, []);
  return query;
}
