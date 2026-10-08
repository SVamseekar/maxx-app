export type ScanResult = {
  request_id: string;
  open_bloc_id: string | null;
  mode: "live" | "fixture";
  item: { title: string | null; price: string | null; currency: string | null; merchant: string | null; variant: string | null; confidence: number };
  rows: { title: string; url: string; price: string; shipping: string | null; same_item: boolean; in_stock: boolean; evidence: string }[];
  score: { value: number | null; best: string | null; price_gap: string; ownership_penalty: number; bloc_bonus: number; low_confidence: boolean };
  recommendation: { primary: "CHEAPER" | "WAIT" | "SKIP" | "JOIN_BLOC"; headline: string; explanation: string };
  warnings: string[];
  latency_ms: number;
  calls: { provider: string; purpose: string; model?: string | null; status: string; latency_ms: number; tokens?: { prompt_tokens?: number; completion_tokens?: number } | null; cost_usd?: string | null }[];
};
