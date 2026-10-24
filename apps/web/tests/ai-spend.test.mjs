import assert from "node:assert/strict";
import test from "node:test";
import { aiSpendRows, guardSummary } from "../app/admin/ai-spend.ts";

const bucket = (cap, spent, reserved = "0") => ({ cap_usd: cap, spent_usd: spent, reserved_usd: reserved, remaining_usd: String(Number(cap) - Number(spent) - Number(reserved)) });

test("every shared AI limit is shown with what is left, and a nearly used limit is flagged", () => {
  const rows = aiSpendRows({
    total: bucket("20", "3.5"),
    day: bucket("0.40", "0.35", "0.02"),
    anonymous_day: bucket("0.08", "0"),
    negotiation_day: bucket("0.20", "0.05"),
    tavily_month: { cap_credits: "900", spent_credits: "120", reserved_credits: "0", remaining_credits: "780" },
    tavily_day: { cap_credits: "40", spent_credits: "40", reserved_credits: "0", remaining_credits: "0" },
  });
  assert.deepEqual(rows.map(r => r.label), ["Total", "Today", "Visitors today", "Negotiations today", "Web search this month", "Web search today"]);
  assert.equal(rows[0].text, "$3.50 of $20.00 · $16.50 left");
  assert.equal(rows[1].warn, true);
  assert.equal(rows[2].warn, false);
  assert.equal(rows[3].text, "$0.05 of $0.20 · $0.15 left");
  assert.equal(rows[4].text, "120 of 900 credits · 780 left");
  assert.equal(rows[5].warn, true);
});

test("guard hits are listed most frequent first", () => {
  assert.deepEqual(guardSummary({ verdict_numbers: 2, schema_retry: 5 }), ["schema retry × 5", "verdict numbers × 2"]);
  assert.deepEqual(guardSummary({}), []);
});
