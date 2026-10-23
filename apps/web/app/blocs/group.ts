import type { Member } from "./types";

export type GroupBuyer = { id: string; limit: number; status: Member["status"] };

/** Buyers who took part. Held, won, below-clearing and released buyers all count; people who left do not. */
export function activeBuyers(members: Pick<Member, "id" | "max_price" | "status">[]): GroupBuyer[] {
  return members
    .filter(member => member.status !== "LEFT")
    .map(member => ({ id: member.id, limit: Number(member.max_price), status: member.status }))
    .filter(buyer => Number.isFinite(buyer.limit) && buyer.limit > 0);
}

/** Buyers whose limit covers `price`. `limitsAsc` must be sorted ascending. */
export function buyersAtOrAbove(limitsAsc: number[], price: number): number {
  let low = 0, high = limitsAsc.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (limitsAsc[mid] < price) low = mid + 1; else high = mid;
  }
  return limitsAsc.length - low;
}

export function median(limitsAsc: number[]): number | null {
  if (!limitsAsc.length) return null;
  const mid = limitsAsc.length >> 1;
  return limitsAsc.length % 2 ? limitsAsc[mid] : (limitsAsc[mid - 1] + limitsAsc[mid]) / 2;
}

/** Share of the group whose limit is strictly below `value`, as a whole percentage. */
export function percentBelow(limitsAsc: number[], value: number): number {
  if (!limitsAsc.length) return 0;
  const below = limitsAsc.length - buyersAtOrAbove(limitsAsc, value);
  return Math.round((below / limitsAsc.length) * 100);
}

/**
 * Corner points of the demand step curve: how many buyers would pay at least each price.
 * Starts at the full group on the left and ends at zero on the right.
 */
export function demandSteps(limitsAsc: number[], low: number, high: number): [number, number][] {
  const steps: [number, number][] = [[low, limitsAsc.length]];
  const distinct = [...new Set(limitsAsc)];
  for (const limit of distinct) {
    steps.push([limit, buyersAtOrAbove(limitsAsc, limit)]);
    steps.push([limit, buyersAtOrAbove(limitsAsc, limit + 1e-9)]);
  }
  steps.push([high, 0]);
  return steps;
}

/** Price range for the chart, padded so edge markers stay inside and a single-buyer group still draws. */
export function chartDomain(limitsAsc: number[], extras: number[] = []): [number, number] {
  const values = [...limitsAsc, ...extras.filter(Number.isFinite)];
  if (!values.length) return [0, 1];
  const min = Math.min(...values), max = Math.max(...values);
  const pad = Math.max((max - min) * .06, max * .02, .5);
  return [Math.max(0, min - pad), max + pad];
}
