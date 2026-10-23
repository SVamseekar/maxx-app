/** Match every search term; accents and extra whitespace should not hide an item. */
export function matchesQuery(text: string, query: string): boolean {
  const normalize = (value: string) => value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const haystack = normalize(text);
  return normalize(query).trim().split(/\s+/).every(term => haystack.includes(term));
}
