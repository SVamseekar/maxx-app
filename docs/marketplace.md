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

After that, `maxx/sellers/lifecycle.py` decides the status in one place. A seller is `ACTIVE` only when every step is done:

1. **Payout email confirmed.**
2. **Identity verified** (`VERIFY_MODE=stripe`: a Stripe Identity document check with a matching live selfie, `/sell/verify-identity`). The webhook (`POST /webhooks/identity`, `Stripe-Signature` checked with a 5-minute tolerance) is only a hint: the result is always re-read from Stripe with the secret key. For an individual, the name on the ID must match the legal name given, or the account goes to a person.
3. **Sanctions screening.** Legal, trading and verified names are matched against the U.S. Treasury OFAC SDN list and its aliases (about 40,000 names, refreshed hourly from `sanctionslistservice.ofac.treas.gov`): normalised (accents, punctuation, company suffixes), then word-by-word Jaro-Winkler at `SANCTIONS_THRESHOLD` (0.9). A possible match is never decided by the code: it puts the seller in the `/admin` review queue, where a person clears or blocks it.
4. **Review** by an administrator when `SELLER_REVIEW=manual` (required in production).

Until then a seller is `PENDING` (a step is theirs) or `UNDER_REVIEW` (Maxx is checking); the console shows the steps. Rejecting, suspending, reinstating and closing are decisions with an audit entry. A suspended seller keeps a limited console: they must still ship and answer for orders they already have.

**Staying compliant** (`lifecycle.can_sell`). Under the INFORM Consumers Act, a seller with `HIGH_VOLUME_SALES` (200) sales and `HIGH_VOLUME_REVENUE` ($5,000) in 12 months must give a tax id within `SELLER_INFO_DAYS` (10). Every seller re-confirms their details once a year. Until they do, their offers sit out of new Blocs; existing orders are unaffected. Tax ids are encrypted (AES-GCM) and only the last four digits are shown.

Buyers see a seller's trader details (never the payout address) for sellers they bought from: `GET /sellers/{code}`.

## Offers, listings and seller agents

- **Standing offer** on demand that already exists: units, a **floor** never gone below, an opening price and a style (firm 2%, balanced 5%, eager 9% concession per round).
- **Listing** (`POST /seller/listings`) for a product nobody has asked for yet. It opens a Bloc that buyers can join. Rules: the exact product title, an optional GTIN/UPC/EAN checked with the GS1 check digit (listings with the same barcode share one Bloc), a category from a fixed list, a screen for prohibited goods, `floor ≤ opening ≤ typical price`, and `LISTING_MAX_PER_SELLER` (20) live listings. An administrator can take a listing down; its Bloc ends and every hold is released.
- **Who negotiates.** *Rules* (default): the concession style above, no language model. *AI agent*: a Nemotron seller agent bids for the seller, steered by up to 280 characters of guidance. Every AI bid passes `guard_ai_bid` at the execution boundary: never below the floor, never above the opening price or its own previous offer, at most `SELLER_AI_MAX_ROUND_DROP_PERCENT` (15%) of the opening price lower per round, never more units than stock. Clamped bids are shown in the room.

When a Bloc negotiates, `sellers.store.attach` adds every active seller allowed to sell with an offer for that product. Sellers cannot buy a product they have an offer on.

## Order lifecycle

```
captured ─> AWAITING_ADDRESS ─ address given ─> AWAITING_SHIPMENT ─ seller ships (tracking) ─> SHIPPED ─ carrier: delivered ─> DELIVERED
   │              │ deadline (7 d)                    │ deadline + 2 d grace
   │              └─> CANCELLED + full refund         └─> CANCELLED + full refund + seller strike
   └ buyer can cancel before it ships ─> CANCELLED + full refund
```

- **Address after winning** (`ADDRESS_WAIT_DAYS`), so non-winners never give one. Addresses are encrypted (AES-GCM) and only the selling account can read an order's copy; it is wiped `ADDRESS_RETENTION_DAYS` (90) after the order finishes, and on account closure.
- **Tracking numbers are checked, not trusted.** The carrier is chosen from a list (UPS, USPS, FedEx, DHL, Canada Post, Royal Mail, UPU S10 posts, DPD, OnTrac, Amazon, Purolator, Yodel, LaserShip, other). The number must match that carrier's format and check digit (vendored tracking_number_data rules) and cannot be reused for another order. With `TRACKING_MODE=easypost` a tracker is registered and the carrier's events are shown to the buyer and the seller; webhooks (`POST /webhooks/tracking`, HMAC-checked) only trigger a re-read with the API key, and every tracker is also polled every `TRACKING_POLL_MINUTES`. The tracking number is also sent to PayPal (`/v2/checkout/orders/{id}/track`) for seller protection.
- **When the seller is paid.** A new seller is paid when the carrier reports delivery. After `PAYOUT_TRUSTED_AFTER_DELIVERIES` (5) delivered orders without strikes, at the carrier's first scan. A parcel never scanned within `TRACKING_NO_SCAN_DAYS` (4), returned to sender, delivered to another country or reported failed is flagged and its payout held for a person in `/admin`. One payout per order, with a deterministic batch id; each PayPal payout item is followed until it is `SUCCESS`, `UNCLAIMED` or failed, and failed items are retried and shown to the seller. Payout also waits while a problem is open, while payments are frozen, or inside the cooldown after a payout-address change.
- **Strikes.** An unshipped order or an unanswered problem report gives the seller a strike; three suspend the account.
- **Delivery** comes from the carrier, or is confirmed by the buyer, or automatically after `DELIVERY_AUTO_CONFIRM_DAYS` (14) without a problem report.
- **Simulated sellers** (the demo's built-in competitors, `SIMULATED_SELLERS`) turn their wins into real orders like everyone else: an automatic, clearly labelled stand-in ships them after `SIMULATED_SELLER_SHIP_SECONDS` with a valid test number and simulated tracking, and answers problem reports with a refund.

### Problems (cases)

A buyer opens a problem after shipment (within 60 days): not received, not as described, return request, other. The seller has `CASE_RESPONSE_HOURS` (24) to reply. If they do not, the buyer is refunded in full and the seller gets a strike. The seller can agree to refund in one click; if they disagree an administrator decides. A refund after a payout creates a **seller adjustment**: the amount owed is deducted from the seller's later payouts.

### Refunds

`PayPalClient.refund_capture` (idempotent, request id `refund-{order}`), always for the full amount, back to the original PayPal payment method. The payment ledger row becomes `REFUNDED`; the books (`/money/blocs/{id}/ledger`) show refunded money and money held for shipping, and "Reconciled" means everything captured is paid out, held for shipping, or accounted for.

## Notifications

Every order, payout, deadline and account event is a row in `notifications` (bell and `/notifications` for buyers and sellers). Email is sent from that table as an outbox: a row is claimed before sending, failures retry with growing gaps up to `EMAIL_MAX_ATTEMPTS`, and a dedupe key makes each reminder go out once. Money, deadlines, problem reports and account decisions are always emailed; other kinds can be switched off. Emails contain only fixed sentences, a product title stripped of links, and a link to a page on this site, never text another person wrote.

## Seller tour (judges)

On `/judge`, a signed-in judge can open a demo seller account with onboarding already passed and watch it win orders from three demo buyers against two simulated competitors, then ship with test tracking numbers (`EZ1000000001` to `EZ7000000007`, one per carrier outcome) and see the payout and notifications. It runs only with `PAYPAL_MODE=simulator` and `DEMO_TOOLS` on (default outside production). Tour Blocs are never listed and never accept real buyers; demo sellers can sell only in their own tour, and real sellers never join one.

## Operator console (`/admin`, administrators only)

Seller review queue (including possible sanctions matches, with clear or block), flagged deliveries with release, open disputes with the full thread, listing take-downs, decisions with a required note, payment health (failed payouts, stuck payments, partial settlements, orders waiting, email outbox, sanctions list age, the provider modes in use), a **pause all payments** switch (fresh identity check required; existing holds stay safe), reconcile-with-PayPal, and the audit log.

## Account rights

`GET /me/export` returns everything held about the account (fresh identity check). Closing an account is blocked while an order is undelivered, a problem is open or a seller owes money; it voids open holds, deletes addresses and offers, and keeps only what the law needs (payments with an opaque id; the seller trader record, closed).

## Configuration

`SELLER_REVIEW`, `SHIP_GRACE_DAYS`, `ADDRESS_WAIT_DAYS`, `DELIVERY_AUTO_CONFIRM_DAYS`, `ADDRESS_RETENTION_DAYS`, `PAYOUT_COOLDOWN_HOURS`, `CASE_RESPONSE_HOURS`, `PLATFORM_FEE_PERCENT`, `ADMIN_EMAILS`; tracking: `TRACKING_MODE`, `EASYPOST_API_KEY`, `EASYPOST_WEBHOOK_SECRET`, `TRACKING_POLL_MINUTES`, `TRACKING_NO_SCAN_DAYS`, `PAYOUT_TRUSTED_AFTER_DELIVERIES`; identity and screening: `VERIFY_MODE`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `SELLER_IDENTITY_REQUIRED`, `SANCTIONS_THRESHOLD`, `HIGH_VOLUME_SALES`, `HIGH_VOLUME_REVENUE`, `SELLER_INFO_DAYS`; listings and agents: `LISTING_MAX_PER_SELLER`, `SELLER_AI_MAX_ROUND_DROP_PERCENT`; demo: `SIMULATED_SELLERS`, `SIMULATED_SELLER_SHIP_SECONDS`, `DEMO_TOOLS`; `EMAIL_MAX_ATTEMPTS`. See `.env.example`. The housekeeping sweep (deadlines, tracking, payouts, emails, purges, compliance) runs from the worker every 20 seconds, so `WORKER_ENABLED` must be on. Production refuses EasyPost without a webhook secret and the seller tour without the PayPal simulator. The tracking and identity simulators are allowed there, labelled on every screen, because live payments are refused anyway and `SELLER_REVIEW=manual` keeps a person approving each seller.

## Not built, or not verified

- **Not run against the real providers yet:** PayPal sandbox payouts and add-tracking, EasyPost and Stripe Identity. Their clients are tested against mock transports; the simulators are what the demo uses, and every screen says so. EasyPost's webhook signature format is implemented from its documentation and needs a check on the first live delivery.
- PayPal marketplace (platform) onboarding. In production the money should reach sellers through PayPal for Marketplaces rather than the Maxx account; PayPal's multiparty orders fix the payee at order creation, which does not fit a Bloc whose winning sellers are known only after negotiation, so Payouts are used.
- Business (KYB) verification of companies beyond the trader details, partial refunds, return labels, seller messaging outside problem reports.
- Tax: Maxx adds none and sellers are responsible. Marketplace-facilitator tax rules need specialist advice per country.
- Enforcement of the legal retention schedules other than address wiping.
