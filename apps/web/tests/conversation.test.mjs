import assert from "node:assert/strict";
import test from "node:test";
import { conversationGroups, previousOfferPrice } from "../app/blocs/conversation.ts";

test("identical adjacent requests become one reply while preserving every recipient and event", () => {
  const events = [
    { id: 1, type: "round_start", data: { round: 1 } },
    { id: 2, type: "negotiator_message", data: { to: "A", text: "Improve your offer." } },
    { id: 3, type: "negotiator_message", data: { to: "B", text: "Improve your offer." } },
    { id: 4, type: "negotiator_message", data: { to: "C", text: "Can you supply more units?" } },
  ];
  const groups = conversationGroups(events);
  assert.equal(groups.length, 3);
  assert.deepEqual(groups[1].events.map(e => e.data.to), ["A", "B"]);
  assert.deepEqual(groups.flatMap(g => g.events), events);
});

test("requests never merge across rounds or an intervening seller event", () => {
  const events = [
    { id: 1, type: "negotiator_message", data: { round: 1, to: "A", text: "Improve." } },
    { id: 2, type: "seller_offer", data: { round: 1, seller: "A", price: "100", qty: 1 } },
    { id: 3, type: "negotiator_message", data: { round: 1, to: "B", text: "Improve." } },
    { id: 4, type: "negotiator_message", data: { round: 2, to: "B", text: "Improve." } },
  ];
  assert.equal(conversationGroups(events).length, 4);
});

test("offer batches retain chronology, withdrawal, retry and allocation results", () => {
  const events = [
    { id: 1, type: "seller_offer", data: { round: 1, seller: "A", price: "100", qty: 1 } },
    { id: 2, type: "seller_offer", data: { round: 1, seller: "B", price: "110", qty: 2 } },
    { id: 3, type: "seller_withdrew", data: { round: 1, seller: "A" } },
    { id: 4, type: "provider_retry", data: { round: 1 } },
    { id: 5, type: "tentative_allocation", data: { round: 1, served: 2, avg_price: "110" } },
  ];
  const groups = conversationGroups(events);
  assert.equal(groups[0].events.length, 2);
  assert.deepEqual(groups.flatMap(g => g.events), events);
  assert.equal(groups.at(-1).kind, "tentative_allocation");
});

test("previous offer price is the seller's earlier quote and resets after withdrawal", () => {
  const events = [
    { id: 1, type: "seller_offer", data: { round: 1, seller: "A", price: "150.00" } },
    { id: 2, type: "seller_offer", data: { round: 1, seller: "B", price: "140.00" } },
    { id: 3, type: "seller_offer", data: { round: 2, seller: "A", price: "142.50" } },
    { id: 4, type: "seller_withdrew", data: { round: 2, seller: "B" } },
    { id: 5, type: "seller_offer", data: { round: 3, seller: "B", price: "130.00" } },
  ];
  assert.equal(previousOfferPrice(events, "A", 3), 150);
  assert.equal(previousOfferPrice(events, "A", 1), null);
  assert.equal(previousOfferPrice(events, "A", 99), 142.5);
  assert.equal(previousOfferPrice(events, "B", 5), null);
  assert.equal(previousOfferPrice(events, undefined, 5), null);
});
