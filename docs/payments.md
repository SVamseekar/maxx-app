# Payments: PayPal holds, agentic checkout and PYUSD

Maxx can move money through PayPal. This page says what is built, how to run it, what is real and what is not.

## Three modes

| `PAYPAL_MODE` | What happens | Keys needed |
|---|---|---|
| `off` (default) | The original demo. Joining a Bloc is a simulated commitment. No money anywhere. | none |
| `simulator` | A built-in stand-in for PayPal runs inside the API. It follows PayPal's rules (authorize, partial capture, void, idempotent request ids) and stores its state in the database. Every screen is labelled "Simulated PayPal". | none |
| `sandbox` | The API calls PayPal's sandbox (`api-m.sandbox.paypal.com`) with your credentials and the browser opens PayPal's own approval window. | `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` |

Live (production) PayPal is refused at start-up. Maxx is a hackathon prototype and has no seller onboarding, KYC or legal review.

**Verification status.** The simulator and the PayPal client are covered by automated tests (the client against a mock HTTP transport that checks request bodies, headers and error handling). The sandbox mode has **not** been run against PayPal itself in this repository, because no sandbox credentials were available. Treat the first sandbox run as a test: the checklist below lists what to look at.

## What each part does

### Group buy with a PayPal hold
1. **Join.** The member picks a maximum. The API creates an order with `intent: AUTHORIZE` for that amount. The buyer approves it on PayPal. The API then authorizes the order, which places a hold, and only then adds the member to the Bloc. If the Bloc changed in the meantime, the hold is voided.
2. **Leave.** The member is marked as left first, then the hold is voided. A PayPal outage can delay the release but can never leave someone committed.
3. **Clear.** When the negotiation ends, each winner is captured at their own final price with `final_capture: true`, so PayPal releases the rest of the hold. Everyone else is voided. If there is no deal, every hold is voided.
4. **Pay sellers.** The Maxx fee (`PLATFORM_FEE_PERCENT`, default 5%) is taken from the seller side, so buyers never pay more than the winning price. Simulated demo sellers get one Payouts batch per Bloc straight after capture. **Real sellers are paid per order, when they ship** (see [marketplace](marketplace.md)); unshipped orders are refunded. Buyers pay nothing extra.
5. **Reconcile.** `GET /money/blocs/{id}/ledger` shows the books for the Bloc. "Reconciled" means everything captured equals fees plus sent payouts, to the cent.

Safety rules in code, each with a test:
- A capture can never exceed the member's maximum (checked against the member, the ledger row and PayPal's hold).
- Every PayPal write has a deterministic `PayPal-Request-Id`, so a retry returns the first result.
- Every step is recorded before and after the call. A crash resumes without capturing twice (`settlements` row plus per-payment status).
- A retryable failure (429/5xx/network) leaves the hold untouched and the settlement `PARTIAL`; the worker retries it. A non-retryable one (for example a declined capture) is recorded as `CAPTURE_FAILED` and shown to the buyer.
- Demo members seeded with a Bloc have no real hold and are never charged.

### Webhooks
`POST /money/webhooks/paypal` is called by PayPal, not by browsers. It checks the signature (sandbox: PayPal's `verify-webhook-signature` with `PAYPAL_WEBHOOK_ID`; simulator: HMAC with `SIMULATOR_WEBHOOK_SECRET`), stores each event id once, and updates the ledger: capture completed/denied/refunded, authorization voided, payout batch result, subscription activated/cancelled. A redelivered event is acknowledged and ignored. A webhook cannot raise a capture above its hold.

Register the URL `https://<your-api-host>/money/webhooks/paypal` in the PayPal developer dashboard for the events `PAYMENT.AUTHORIZATION.VOIDED`, `PAYMENT.CAPTURE.*`, `PAYMENT.PAYOUTSBATCH.*` and `BILLING.SUBSCRIPTION.*`. The Next.js proxy deliberately does not forward this path.

### Agentic checkout ("Let the agent buy it")
From a scan verdict, the checkout agent proposes the cheapest offer it can verify: the exact item, in stock, with a known delivered price, below the price in the screenshot.

- The proposal is signed by the server (HMAC) and expires after `CHECKOUT_PROPOSAL_MINUTES`. It cannot be edited or used by another account.
- The agent's tools are named like PayPal's Agent Toolkit: `create_order`, `get_order`, `capture_order` (`GET /checkout/tools`). They run only through a **guard** that compares the amount to the signed proposal, refuses anything over the limit and refuses a total you did not confirm.
- **You approve the exact total** by typing it. Nothing is created before that, and confirming twice returns the first order instead of a second charge.
- Limit: `CHECKOUT_MAX_AMOUNT` ($500), or `CHECKOUT_PREMIUM_MAX_AMOUNT` ($2,000) with Maxx Plus.
- The planner is rule-based, not a language model. The AI in Maxx is the negotiation (Nebius models in live mode); the checkout agent shows how an agent can be given PayPal-style tools safely. It does not use PayPal's MCP server. The integration works the same way a model-driven agent would: through those three tools and the guard.
- In this demo the checkout pays the Maxx sandbox account. No goods are shipped; Maxx has no merchant integration.

### Maxx Plus (PayPal Subscriptions)
Weekly ($6.99) or yearly ($49). The only benefit is the higher agent-checkout limit; nothing about fairness in a Bloc depends on it. Plus switches on only when the **webhook** says `BILLING.SUBSCRIPTION.ACTIVATED`, never because the browser said so. For sandbox, create the two billing plans in PayPal and set `PAYPAL_PLAN_WEEKLY` and `PAYPAL_PLAN_YEARLY`.

### PYUSD (crypto)
PYUSD is PayPal's dollar stablecoin, issued by Paxos. I found no documented PayPal API for paying merchants with it, so Maxx treats it as a plain ERC-20 payment that it verifies on chain:

1. At checkout the buyer picks "PYUSD stablecoin". Maxx shows the deposit address and an **exact amount whose last three digits are an order tag** (PYUSD has six decimals: $299.99 becomes 299.990173).
2. The buyer sends that amount from their own wallet and pastes the transaction hash.
3. Maxx reads the receipt from an Ethereum JSON-RPC node (`eth_getTransactionReceipt`, `eth_blockNumber`) and accepts it only if the token contract, recipient, exact amount and confirmation depth (`PYUSD_MIN_CONFIRMATIONS`) all match, the block is no older than the order, and the hash has not paid another order. Tags are unique among open orders, and the transaction is claimed in the same database transaction that marks the order paid (primary key on `used_transactions`), so two requests cannot both win. A transfer cannot be tied to a specific sender; anyone who sends the exact tagged amount to the address pays that order.

Maxx never holds a wallet key and never signs a transaction. It is read-only. What PYUSD does **not** do here: it cannot be used for Bloc holds (a blockchain transfer cannot be "held and partly released"), and sellers are not paid in PYUSD.

Set `PYUSD_RPC_URL`, `PYUSD_CONTRACT`, `PYUSD_DEPOSIT_ADDRESS` (and `PYUSD_CHAIN` as a label). Use a testnet token first. Check the contract address against Paxos's published list before relying on it. With no RPC configured and `PAYPAL_MODE=simulator`, a simulated chain is used and the interface offers "Simulate sending from a wallet".

## Try it with no keys

```bash
# .env
PAYPAL_MODE=simulator
make db migrate        # adds the payments tables (migration 0005)
make api               # and, in another terminal, make web
```

1. Sign in (or `make dev-account EMAIL=you@example.com PASSWORD='a long passphrase'`).
2. Open **Demo lab**, enter "Successful deal", choose **Join with a PayPal hold**, approve the simulated PayPal sheet.
3. **Close Bloc & negotiate.** Watch the settlement panel: your hold, what you paid (less than your maximum), the group books and the seller payouts, marked Reconciled.
4. Open **Receipts** for every id.
5. Scan the headphones sample, click **Ask the agent for an offer**, type the total, and pay with PayPal or PYUSD.
6. Account settings → **Maxx Plus**.

Add `PAYPAL_NEGATIVE_TESTING=true` to get a "Test a failure" menu in the hold dialog (decline the final charge, decline the hold) and see how failures are shown.

## Run against PayPal's sandbox

1. In the PayPal developer dashboard create a sandbox REST app, a business account (the platform) and a personal buyer account.
2. Set `PAYPAL_MODE=sandbox`, `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and `PAYPAL_SELLER_RECEIVER` (a sandbox account that will receive seller payouts; Payouts must be enabled for the app).
3. Create a webhook for your API URL, set `PAYPAL_WEBHOOK_ID`. For a local API, tunnel it (for example with a Cloudflare or ngrok tunnel).
4. Set `PAYPAL_MODE=sandbox` for the web app too: it loosens the page's Content-Security-Policy for `www.sandbox.paypal.com` only in this mode.
5. Run the join, close and receipts steps above with the sandbox buyer.

First-run things to check (not yet verified here): that the v6 SDK popup opens and returns an approval (`apps/web/app/components/paypal-approval.tsx`), that authorize returns an authorization id, that the partial capture shows the lower amount in the buyer's PayPal activity, and that the payout batch succeeds.

## Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `PAYPAL_MODE` | `off` | `off`, `simulator` or `sandbox` |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` | empty | Sandbox credentials. The client id is sent to the browser (it is public by design). The secret never leaves the API. |
| `PAYPAL_BASE_URL` | PayPal sandbox | Must be a sandbox host or the server refuses to start |
| `PLATFORM_FEE_PERCENT` | `5` | Taken from the seller side of each payout |
| `SETTLEMENT_CONCURRENCY` | `10` | Parallel PayPal calls during a settlement |
| `PAYPAL_NEGATIVE_TESTING` | `false` | Shows the "Test a failure" menu |
| `PAYPAL_SELLER_RECEIVER` | placeholder | Receiver for seller payouts (one account for all sellers in the demo) |
| `PAYPAL_PLAN_WEEKLY`, `PAYPAL_PLAN_YEARLY` | empty | PayPal billing plan ids (sandbox) |
| `CHECKOUT_MAX_AMOUNT`, `CHECKOUT_PREMIUM_MAX_AMOUNT` | `500`, `2000` | Agent checkout limits |
| `SIMULATOR_WEBHOOK_SECRET` | published default | Must be changed in production if the simulator is on |
| `PYUSD_RPC_URL`, `PYUSD_CONTRACT`, `PYUSD_DEPOSIT_ADDRESS`, `PYUSD_CHAIN`, `PYUSD_MIN_CONFIRMATIONS` | empty / `3` | PYUSD verification |

## Hardening added with the marketplace

- **Limits:** `HOLD_MAX_AMOUNT` per hold, `HOLD_OUTSTANDING_MAX_PER_USER` in total, `HOLD_OPEN_MAX_PER_USER` holds. Large holds (`HOLD_REAUTH_OVER`) and checkouts (`CHECKOUT_REAUTH_OVER`) need a fresh identity check.
- **Emergency brake:** `PAYMENTS_FROZEN` or the admin switch stops new holds, captures and payouts. Holds already placed stay safe; settlement resumes when thawed.
- **Audit log:** an append-only table of money and trust decisions (`hold.placed`, `payment.captured`, `refund.sent`, `payout.sent`, seller decisions, freezes, rejected webhooks). Writing it never blocks a payment.
- **Webhooks:** events older than three days or from the future are refused, bad signatures are rate limited and only the first few per minute are logged, and events cannot raise a capture above its hold.
- **Reconciliation:** `GET /admin/reconcile` compares recent holds with PayPal (`get_authorization`) and reports differences. The Bloc ledger also reports refunds and money held until shipping.
- **Self-dealing:** a seller with an offer on a product cannot place a hold on it.
- **Logs:** a filter redacts configured secrets and bearer tokens from every log line.
- **Refunds:** `refund_capture`, idempotent, full amount, to the original payment method.

## Not built

- **Vault (saved PayPal) for one-tap repeat joins.** Every join asks for approval.
- **Pots (no-buy challenges).** Dropped: it needs a separate rules and legal review and adds nothing to the hold, capture and payout story.
- **Cashback payouts to buyers.** Buyers keep the difference between their maximum and the winning price automatically, because the hold is only partly captured.
- **Reauthorization of holds older than 29 days**, refunds from the interface, and disputes.
- **PayPal's MCP server / Agent Toolkit package.** The tools follow its names; the package is not installed.
