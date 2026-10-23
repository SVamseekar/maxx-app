import type { BlocEvent } from "./blocs/types";

type PriceEvidence = { price: string; shipping: string | null; same_item: boolean; in_stock: boolean };
/** Display-only comparisons. The server remains the authority for scores and allocations. */
export function priceComparison(price: string | null, currency: string | null, rows: PriceEvidence[]) {
  if (currency !== "USD" || price === null || !Number.isFinite(Number(price)) || Number(price) <= 0) return null;
  const trusted = rows.filter(row => row.same_item && row.in_stock && row.shipping !== null)
    .map(row => Number(row.price) + Number(row.shipping))
    .filter(total => Number.isFinite(total) && total > 0);
  if (!trusted.length) return null;
  const best = Math.min(...trusted);
  return { best, difference: Math.round((Number(price) - best) * 100) / 100, trustedCount: trusted.length };
}

export function latestOffers(events: Pick<BlocEvent, "type" | "data">[]) {
  const offers = new Map<string, { seller: string; price: string; qty: number; round: number }>();
  const unavailable = new Set<string>();
  for (const event of events) {
    const { seller, price, qty, round } = event.data;
    if (!seller) continue;
    if (["seller_withdrew", "seller_unavailable"].includes(event.type)) {
      unavailable.add(seller); offers.delete(seller);
    } else if (event.type === "seller_offer" && !unavailable.has(seller) && price !== undefined) {
      offers.set(seller, { seller, price, qty: qty ?? 0, round: round ?? 0 });
    }
  }
  return [...offers.values()].sort((a, b) => a.seller.localeCompare(b.seller));
}

export function needsRoomSnapshot(type: string) {
  return ["cleared", "failed", "member_joined", "commitment_released"].includes(type);
}

export function statusLabel(status: string) {
  return ({ FORMING: "Forming", OPEN: "Open to join", NEGOTIATING: "Negotiating", SETTLED: "Deal settled", FAILED: "No deal" } as Record<string, string>)[status] ?? status;
}
