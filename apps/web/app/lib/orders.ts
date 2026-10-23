export type OrderStatus = "AWAITING_ADDRESS" | "AWAITING_SHIPMENT" | "SHIPPED" | "DELIVERED" | "CANCELLED" | "REFUNDED";
export type CaseMessage = { actor: "buyer" | "seller" | "maxx"; body: string; at: number };
export type CaseView = { id: string; kind: string; status: string; opened_at: number; respond_by: number; resolution: string; messages: CaseMessage[] };
export type OrderView = {
  id: string; bloc_id: string; title: string; amount: string; currency: string; status: OrderStatus; ship_by: number; carrier: string; tracking: string;
  shipped_at: number | null; delivered_at: number | null; created_at: number; has_address: boolean; seller: { code: string; name: string }; open_case_id: string | null; cases: CaseView[];
  simulated: boolean; tracking_status: string; estimated_delivery: number | null; tracking_events: { status: string; message: string; location: string; at: number }[]; tracking_simulated: boolean;
};
export type AddressSummary = { id: string; label: string; name: string; line1: string; city: string; postal: string; country: string };
export type TraderInfo = { code: string; business_name: string; legal_name: string; business_type: string; address: string; phone: string; support_email: string; website: string; trade_register_no: string; ship_within_days: number; return_days: number; return_policy: string; self_certified: boolean; simulated?: boolean };

export const STATUS_LABEL: Record<OrderStatus, string> = {
  AWAITING_ADDRESS: "Needs your address", AWAITING_SHIPMENT: "Waiting for the seller to ship", SHIPPED: "Shipped", DELIVERED: "Delivered", CANCELLED: "Cancelled and refunded", REFUNDED: "Refunded",
};
export const CASE_KINDS: Record<string, string> = { not_received: "Item not received", not_as_described: "Not as described or damaged", return_request: "I want to return it", other: "Something else" };

/** "in 3 days", "in 5 h", or "overdue" for a deadline given in epoch seconds. */
export function deadlineText(seconds: number, now = Date.now() / 1000): string {
  const delta = seconds - now;
  if (delta <= 0) return "now overdue";
  if (delta < 3600) return `in ${Math.max(1, Math.round(delta / 60))} min`;
  if (delta < 86400) return `in ${Math.round(delta / 3600)} h`;
  return `in ${Math.round(delta / 86400)} days`;
}
