/** One line naming where a negotiation's model calls went: the judge's own proof of Nemotron. */
type Call = { provider: string; model: string | null; cost_usd: string | null };

export function callSummary(calls: Call[]): string {
  const models = new Map<string, number>();
  for (const call of calls) {
    if (call.provider !== "nebius" || !call.model) continue; // model listings carry no model
    const name = call.model.split("/").pop() ?? call.model;
    models.set(name, (models.get(name) ?? 0) + 1);
  }
  const searches = calls.filter(call => call.provider === "tavily").length;
  const cost = calls.reduce((sum, call) => sum + (call.cost_usd === null ? 0 : Number(call.cost_usd)), 0);
  const total = [...models.values()].reduce((sum, n) => sum + n, 0);
  if (!total) return searches ? `${searches} Tavily ${searches === 1 ? "search" : "searches"}, no model calls` : "No model calls";
  const named = [...models].sort((a, b) => b[1] - a[1]).map(([name, n]) => `${name} ×${n}`).join(", ");
  return [
    `${total} Nemotron ${total === 1 ? "call" : "calls"} on Nebius Token Factory (${named})`,
    searches ? `${searches} Tavily ${searches === 1 ? "search" : "searches"}` : "",
    cost > 0 ? `about $${cost.toFixed(3)}` : "",
  ].filter(Boolean).join(" · ");
}

/** A call's token usage in words, short enough to wrap on a phone. */
export function tokenLine(tokens: Record<string, unknown> | null): string {
  if (!tokens) return "tokens unavailable";
  const { prompt_tokens: input, completion_tokens: output, total_tokens: total } = tokens;
  if (typeof input === "number" && typeof output === "number") return `${input.toLocaleString("en-US")} in, ${output.toLocaleString("en-US")} out tokens`;
  if (typeof total === "number") return `${total.toLocaleString("en-US")} tokens`;
  return Object.entries(tokens).map(([key, value]) => `${key} ${String(value)}`).join(", ");
}
