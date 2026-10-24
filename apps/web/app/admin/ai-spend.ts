/** The admin console's view of the AI spending cap. Pure, so it is tested without a browser. */
export type Bucket = { cap_usd: string; spent_usd: string; reserved_usd: string; remaining_usd: string };
export type Credits = { cap_credits: string; spent_credits: string; reserved_credits: string; remaining_credits: string };
export type AiBudget = { total: Bucket; day: Bucket; anonymous_day: Bucket; tavily_month: Credits; tavily_day: Credits };
export type AiRole = { calls: number; refused: number; rejected: number; cost_usd: string };
export type AiOverview = { paused: boolean; budget: AiBudget; roles: Record<string, AiRole>; guards: Record<string, number> };

const money = (value: string) => `$${Number(value).toFixed(2)}`;
// A limit with under a tenth left is about to pause live AI.
const nearlyUsed = (cap: string, remaining: string) => Number(cap) > 0 && Number(remaining) <= Number(cap) / 10;

export function aiSpendRows(budget: AiBudget) {
  const dollars = (label: string, b: Bucket) => ({ label, text: `${money(b.spent_usd)} of ${money(b.cap_usd)} · ${money(b.remaining_usd)} left`, warn: nearlyUsed(b.cap_usd, b.remaining_usd) });
  const credits = (label: string, c: Credits) => ({ label, text: `${Number(c.spent_credits)} of ${Number(c.cap_credits)} credits · ${Number(c.remaining_credits)} left`, warn: nearlyUsed(c.cap_credits, c.remaining_credits) });
  return [
    dollars("Total", budget.total),
    dollars("Today", budget.day),
    dollars("Visitors today", budget.anonymous_day),
    credits("Web search this month", budget.tavily_month),
    credits("Web search today", budget.tavily_day),
  ];
}

export function guardSummary(guards: Record<string, number>) {
  return Object.entries(guards).sort((a, b) => b[1] - a[1]).map(([rule, count]) => `${rule.replaceAll("_", " ")} × ${count}`);
}
