# Marketplace: sellers, orders and who is responsible

Maxx is a marketplace platform. **The seller is the seller of record; Maxx does not ship, store, inspect or insure goods.** Maxx runs the Bloc and the negotiation, collects the payment, coordinates the order and protects the buyer's money until the seller ships. The legal pages say the same thing, and this page is how the code does it.

## Responsibility split

| | Maxx | Seller |
|---|---|---|
| Fair Bloc, negotiation, allocation | yes | no |
| Charge only the allocated price, never above the maximum | yes | no |
| Hold buyer money until the seller ships; refund if they do not | yes | no |
| Goods, listing accuracy, packing, shipping, customs, delivery | no | yes |
| Returns, warranty, customer service, product safety, tax | no | yes |

## Seller onboarding

`POST /seller/apply` takes the whole application, validated on the server:

- **Trader details** (EU Digital Services Act art. 30, US INFORM Consumers Act): trading and legal name, individual or company, country (from a supported list), business address, phone, support email, website (https only), trade register number (required for EU companies).
- **Commitments buyers can rely on:** ship within 1 to 14 days, countries shipped to, a return window of at least 14 days and a return policy of at least 20 characters.
- **Self-certification and agreement:** four explicit checkboxes (terms, accuracy, lawful new goods, authorised to sell and receive payout). The terms are in `maxx/sellers/rules.py`, the single source for the API, the form and the legal page.
- **Payout email, confirmed by a six-digit code** (rate limited, single use, bound to the address it was sent to). Changing it later needs a fresh identity check, pauses the seller until the new address is confirmed, and can wait out `PAYOUT_COOLDOWN_HOURS` before being paid.

Status: `PENDING` (code not confirmed) → `ACTIVE` when `SELLER_REVIEW=auto`, or `UNDER_REVIEW` → `ACTIVE` after an administrator approves when `SELLER_REVIEW=manual` (required in production). Administrators can also reject, suspend and reinstate, always with an audit entry. `CLOSED` is set when a seller closes their account.

What this does **not** do: verify identity or business registration, or screen against sanctions lists. A real launch needs PayPal's partner onboarding and a verification provider. The form says so.

Buyers see a seller's trader details (never the payout address) for sellers they bought from: `GET /sellers/{code}`.

## Standing offers

A verified seller publishes a standing offer for a product: units, a **floor** they never go below, an opening price and a style (firm 2%, balanced 5%, eager 9% concession per round). When a Bloc for that product starts negotiating, `sellers.store.attach` adds every active, verified seller. Their agent is bounded by the same clamps as every other seller (never below floor, never above stock). Sellers cannot buy a product they have an offer on.

## Order lifecycle

```
captured ─> AWAITING_ADDRESS ─ address given ─> AWAITING_SHIPMENT ─ seller ships (tracking) ─> SHIPPED ─> DELIVERED
   │              │ deadline (7 d)                    │ deadline + 2 d grace                         │
   │              └─> CANCELLED + full refund         └─> CANCELLED + full refund + seller strike    └─ problem report ─> case
   └ buyer can cancel before it ships ─> CANCELLED + full refund
```

- **Address after winning** (`address_wait_days`), so non-winners never give one. Addresses are encrypted (AES-GCM) and only the selling account can read an order's copy; it is wiped `ADDRESS_RETENTION_DAYS` (90) after the order finishes, and on account closure.
- **Pay on ship.** The seller is paid by PayPal Payouts when they enter a carrier and tracking number, minus the Maxx fee. One payout per order, with a deterministic batch id. Payout waits while a problem is open, while payments are frozen, or inside the cooldown after a payout-address change.
- **Strikes.** An unshipped order or an unanswered problem report gives the seller a strike; three suspend the account.
- **Delivery** is confirmed by the buyer, or automatically after `DELIVERY_AUTO_CONFIRM_DAYS` (14) without a problem report.

### Problems (cases)

A buyer opens a problem after shipment (within 60 days): not received, not as described, return request, other. The seller has `CASE_RESPONSE_HOURS` (24) to reply. If they do not, the buyer is refunded in full and the seller gets a strike. The seller can agree to refund in one click; if they disagree an administrator decides. A refund after a payout creates a **seller adjustment**: the amount owed is deducted from the seller's later payouts.

### Refunds

`PayPalClient.refund_capture` (idempotent, request id `refund-{order}`), always for the full amount, back to the original PayPal payment method. The payment ledger row becomes `REFUNDED`; the books (`/money/blocs/{id}/ledger`) show refunded money and money held for shipping, and "Reconciled" means everything captured is paid out, held for shipping, or accounted for.

## Operator console (`/admin`, administrators only)

Seller review queue, open disputes with the full thread, decisions with a required note, payment health (failed payouts, stuck payments, partial settlements, orders waiting), a **pause all payments** switch (fresh identity check required; existing holds stay safe), reconcile-with-PayPal, and the audit log.

## Account rights

`GET /me/export` returns everything held about the account (fresh identity check). Closing an account is blocked while an order is undelivered, a problem is open or a seller owes money; it voids open holds, deletes addresses and offers, and keeps only what the law needs (payments with an opaque id; the seller trader record, closed).

## Configuration

`SELLER_REVIEW`, `SHIP_GRACE_DAYS`, `ADDRESS_WAIT_DAYS`, `DELIVERY_AUTO_CONFIRM_DAYS`, `ADDRESS_RETENTION_DAYS`, `PAYOUT_COOLDOWN_HOURS`, `CASE_RESPONSE_HOURS`, `PLATFORM_FEE_PERCENT`, `ADMIN_EMAILS`. The housekeeping sweep (deadlines, payouts, purges) runs from the worker every 20 seconds, so `WORKER_ENABLED` must be on.

## Not built

- Identity/KYC and sanctions screening; PayPal marketplace (platform) onboarding. In production the money should flow to the seller through PayPal for Marketplaces rather than through the Maxx account.
- Carrier tracking integration (the tracking number is taken on trust), partial refunds, return-label flow, seller messaging outside problem reports, email notifications for order events (the interface and audit log show them).
- Tax: Maxx adds none and sellers are responsible. Marketplace-facilitator tax rules need specialist advice per country.
- Enforcement of the legal retention schedules other than address wiping.
