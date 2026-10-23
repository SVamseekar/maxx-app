"use client";
import { Bot, SlidersHorizontal } from "lucide-react";
import { STRATEGY_TEXT, type Overview } from "./types";

export type AgentChoice = { strategy: string; agent: "rules" | "ai"; guidance: string };

/** How a seller's offers are made: fixed rules, or an AI agent inside the same hard limits. */
export default function AgentFields({ overview, value, onChange }: { overview: Overview; value: AgentChoice; onChange: (next: AgentChoice) => void }) {
  const set = (patch: Partial<AgentChoice>) => onChange({ ...value, ...patch });
  return <fieldset className="agent-fields">
    <legend>Who negotiates for you</legend>
    <div className="agent-options" role="radiogroup" aria-label="Negotiating agent">
      <label className={value.agent === "rules" ? "agent-option is-selected" : "agent-option"}><input type="radio" name="agent" checked={value.agent === "rules"} onChange={() => set({ agent: "rules" })} /><SlidersHorizontal size={16} aria-hidden="true" /><span><strong>Fixed rules</strong><small>Lowers your price by the same step each round. Predictable; no AI involved.</small></span></label>
      <label className={value.agent === "ai" ? "agent-option is-selected" : "agent-option"}><input type="radio" name="agent" checked={value.agent === "ai"} onChange={() => set({ agent: "ai" })} /><Bot size={16} aria-hidden="true" /><span><strong>AI agent</strong><small>Reads each round's result and holds or concedes. {overview.negotiation_mode === "live" ? "Runs on Nemotron." : "In this demo a labelled replay stands in for the model."}</small></span></label>
    </div>
    <label className="select-field">{value.agent === "ai" ? "Starting style" : "Concession per round"}<select value={value.strategy} onChange={event => set({ strategy: event.target.value })}>{Object.keys(STRATEGY_TEXT).map(key => <option key={key} value={key}>{STRATEGY_TEXT[key]} ({overview.strategies[key]?.concession_percent}% per round)</option>)}</select></label>
    {value.agent === "ai" && <><label className="select-field">A note to your agent (optional)<textarea rows={2} maxLength={280} value={value.guidance} onChange={event => set({ guidance: event.target.value })} placeholder="For example: I would rather sell all units this week than hold out for a higher price." /></label>
      <p className="small muted agent-limits">Hard limits Maxx enforces on every AI bid: never below your floor, never above your opening price, never higher than its last offer, at most {overview.ai_max_round_drop_percent}% of your opening price lower per round, never more units than your stock. Your note stays private to your agent.</p></>}
  </fieldset>;
}
