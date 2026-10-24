import type { BlocEvent } from "./types";

export type ConversationGroup = {
  id: number;
  kind: string;
  round: number;
  events: BlocEvent[];
};
const visibleEvents = new Set([
  "round_start", "reserve_set", "negotiator_message", "seller_offer",
  "seller_withdrew", "seller_unavailable", "provider_retry", "tentative_allocation",
  "negotiator_fallback",
]);

/** Collapse only adjacent, equivalent messages. Every original event stays available. */
export function conversationGroups(events: BlocEvent[]): ConversationGroup[] {
  const groups: ConversationGroup[] = [];
  let round = 0;
  for (const event of events) {
    if (event.data.round !== undefined) round = event.data.round;
    if (!visibleEvents.has(event.type)) continue;
    const previous = groups.at(-1);
    const sameBatch = previous?.kind === event.type && previous.round === round;
    const sameRequest = event.type === "negotiator_message" && previous?.events[0].data.text === event.data.text;
    if (sameBatch && (sameRequest || event.type === "seller_offer")) {
      previous.events.push(event);
    } else {
      groups.push({ id: event.id, kind: event.type, round, events: [event] });
    }
  }
  return groups;
}

/** Price this seller quoted before `beforeId`, or null if it had not offered yet. Display-only. */
export function previousOfferPrice(events: BlocEvent[], seller: string | undefined, beforeId: number): number | null {
  let price: number | null = null;
  for (const event of events) {
    if (event.id >= beforeId) break;
    if (event.data.seller !== seller) continue;
    if (event.type === "seller_offer" && event.data.price !== undefined) price = Number(event.data.price);
    else if (event.type === "seller_withdrew" || event.type === "seller_unavailable") price = null;
  }
  return price !== null && Number.isFinite(price) ? price : null;
}
