/** Notification kinds as people see them. Keys match the API's notify.service.KINDS. */
export type NotificationItem = { id: string; kind: string; title: string; body: string; link: string; created_at: number; read: boolean };
export type Inbox = { unread: number; items: NotificationItem[] };
export type Preferences = { email: Record<string, boolean>; always: string[] };

export const KIND_LABEL: Record<string, string> = {
  "order.won": "You won an order",
  "order.address_reminder": "Delivery address reminders",
  "order.shipped": "Your order shipped",
  "order.out_for_delivery": "Out for delivery",
  "order.delivered": "Delivered",
  "order.refunded": "Refunds",
  "order.tracking_issue": "Delivery problems",
  "case.reply": "Seller replies to your problem reports",
  "case.resolved": "Problem reports closed",
  "bloc.released": "Holds released when a Bloc ends without you",
  "seller.status": "Seller account decisions",
  "seller.identity": "Identity check results",
  "seller.order_new": "New orders",
  "seller.order_ready": "Orders ready to ship",
  "seller.ship_reminder": "Shipping deadline reminders",
  "seller.order_cancelled": "Cancelled orders",
  "seller.case_opened": "Problems reported by buyers",
  "seller.case_reminder": "Problem reply reminders",
  "seller.case_reply": "Buyer messages and case outcomes",
  "seller.payout_sent": "Payouts that reached your PayPal",
  "seller.payout_failed": "Payouts that failed",
  "seller.strike": "Strikes",
  "seller.tracking_issue": "Delivery problems on your orders",
  "seller.info_required": "Details and tax id requests",
  "seller.bloc_result": "What your offers won",
  "seller.listing": "Listing removals",
};

/** Only links into this site are followed (the API enforces the same list). */
export function safeLink(link: string): string | null {
  return /^\/((orders|sell|my-blocs|account|notifications|receipts)(\/|\?|#|$)|blocs\/[\w-]+)/.test(link) ? link : null;
}
