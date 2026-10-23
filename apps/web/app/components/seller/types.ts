export type Profile = {
  code: string; business_name: string; legal_name: string; business_type: "individual" | "company"; country: string; payout_email: string; payout_verified: boolean;
  status: "PENDING" | "UNDER_REVIEW" | "ACTIVE" | "SUSPENDED" | "REJECTED" | "CLOSED"; review_note: string; ship_within_days: number; ships_to: string[]; return_days: number;
  return_policy: string; support_email: string; phone: string; website: string; strikes: number; owed: string;
};
export type Overview = {
  seller: Profile | null; terms: string[]; terms_version: string; prohibited: string[]; countries: string[]; eu_countries: string[]; min_return_days: number; fee_percent: string;
  review: "auto" | "manual"; email_verified: boolean; strategies: Record<string, { concession_percent: string }>; payments: boolean;
};
export type Offer = { id: string; product_key: string; title: string; stock: number; floor: string; opening_price: string; strategy: string; active: boolean };
export type Opportunity = { bloc_id: string; product_key: string; title: string; typical_price: string; closes_at: number; buyers: number; median_max: string | null; curve: { price: string; buyers: number }[]; my_offer: Offer | null };
export type Result = { bloc_id: string; title: string; status: string; units: number; paid_units: number; average_price: string | null; payout: { gross: string; fee: string; net: string; status: string; simulated: boolean } | null };
export type ShipTo = { name: string; line1: string; line2: string; city: string; region: string; postal: string; country: string; phone: string };
export type SellerOrder = { id: string; title: string; amount: string; your_share: string; status: string; ship_by: number; carrier: string; tracking: string; created_at: number; case_id: string | null; address: ShipTo | null };
export type SellerCase = { id: string; order_id: string; title: string; amount: string; kind: string; status: string; opened_at: number; respond_by: number; resolution: string; messages: { actor: string; body: string; at: number }[] };
export const STRATEGY_TEXT: Record<string, string> = { firm: "Firm: concede slowly", balanced: "Balanced: steady concessions", eager: "Eager: concede fast for volume" };
export const CARRIERS = ["UPS", "FedEx", "USPS", "DHL", "Royal Mail", "DPD", "Evri", "Canada Post", "Australia Post", "Other"];
