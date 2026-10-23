# Maxx frontend refresh research

13 October 2026. Research and generated visual concepts; implementation awaits approval of the revised dark direction.

## User brief and revisions

Refresh the existing scan, Bloc, negotiation, judge and transparency flows with high-quality motion and a distinctive high-tech visual identity. BeautifulUI.dev is the requested source of interface primitives. Preserve actual API contracts, deterministic pricing, demo disclosures and existing work.

The first light/violet concepts were rejected as too generic. The revised direction uses graphite, platinum typography and restrained arctic blue, with product photography and compact controls. The user requested a richer verdict. The latest concept adds a Money Score dial, delivered-price comparison rail, source rows and an expandable score breakdown.

Generated concepts are in `generated/`. They are design explorations, not screenshots of implemented software or live evidence. Preserve previous iterations for comparison.

## Sources inspected

- Gallery: https://www.beautifului.dev/
- Source and installation/dependency notes: https://github.com/slev12397/beautiful-ui
- MIT licence: https://www.beautifului.dev/license
- LoadingState source inspected through the gallery's View code panel; grid timing, elapsed timer and reduced-motion behavior reviewed.
- Motion layout animations: https://motion.dev/docs/react-layout-animations
- Motion exit transitions: https://motion.dev/docs/react-animate-presence
- Motion accessibility: https://motion.dev/docs/react-accessibility
- Seller volume economics: https://www.shopify.com/enterprise/blog/b2b-ecommerce-wholesale
- Bulk-order pricing: https://www.shopify.com/enterprise/blog/wholesale-ecommerce-websites
- Threshold funding analogy, not a Maxx payment guarantee: https://updates.kickstarter.com/why-is-funding-all-or-nothing/
- Installed Next.js documentation: server/client boundaries, local images and font self-hosting in `node_modules/next/dist/docs/01-app/01-getting-started/`.

BeautifulUI code can be adapted under MIT with the copyright and permission notice retained. Its SidebarNav imports a commercial icon package; replace those icons rather than installing that dependency. Do not import gallery analytics, newsletter capture, example external integrations or decorative video.

## All 21 gallery primitives mapped to the existing product

| Primitive | Meaningful Maxx adaptation |
|---|---|
| Loading State | Compact scan/metadata/negotiation waiting state with actual elapsed time; no invented progress percentage |
| Thinking | Expandable grounded score explanation and actual task/event status; no fabricated model reasoning |
| Streaming Text | Reveal newly received recommendations once complete; incremental negotiation updates remain real SSE events |
| Approval Card | Existing exact product/variant confirmation and maximum-price commitment |
| Tool Chips | Provider purpose/status/latency from actual call records |
| Task Rows | Round and offer activity from actual events |
| Chat | Compact read-only negotiation feed; no unsupported chat composer |
| Prompt Bar | Screenshot chooser and existing extracted-field corrections; no model picker or dictation feature |
| Recommendation Card | Verdict headline, confidence wording and primary action |
| Context Cards | Comparable listings with source URL, shipping, stock, variant and evidence |
| Diff Table | Observed versus comparable delivered price; preserve semantic differences |
| Records Table | Actual provider metadata and seller offer rows |
| Filter Table | Search/status filtering of actual Blocs; optional filtering of recorded provider calls |
| Sidebar Nav | Navigation/gliding active indicator adapted to slim desktop navigation and mobile controls |
| Search | Local search of loaded Blocs, with honest empty state |
| Flowchart | Existing scan → confirm → commit → negotiate → outcome journey |
| Insight Cards | Actual Money Score, price gap, round averages and allocation results |
| Code Block | Optional developer details showing sanitized actual metadata on transparency page |
| Fine-tune Card | Existing maximum-price slider and correction inputs |
| Selection Actions | Existing extracted detail edit/recheck actions |
| Agent Screen | Uploaded screenshot preview and negotiation activity view; no simulated browser automation |

These are adaptations of the gallery's interaction patterns into the app's existing capabilities. The goal is a coherent product, not rendering an unrelated component gallery inside Maxx.

## Evidence and motion rules

- Current sample fixture: Sony WH-1000XM5 Black, observed $349.99, comparable delivered $299.99 and $309.99. With no ownership deduction or qualifying OPEN Bloc bonus, Money Score is 75.
- Money Score is price competitiveness, not probability of a successful negotiation or a calibrated AI confidence percentage.
- Use the result's actual recommendation headline and explanation. Do not hardcode conceptual demo values into the production UI.
- The mockup's dial end label `240` is a generation error: the implementation must use 0–100. Source-bar geometry in mockups is illustrative; implemented bars must derive from actual values.
- Initial hero artwork is decorative and labelled as such; show the real uploaded screenshot when selected. Never imply generated imagery depicts every scanned product.
- Use opacity/transform and interruptible layout transitions, restrained press feedback, segmented navigation, score/price changes and SSE event insertion.
- Honor reduced-motion settings, retain keyboard focus, avoid moving content while a person reads older events, and keep all functionality available without animation.
- Do not fake scan stages: the scan endpoint returns synchronously, so use one truthful working state with an elapsed timer.
- Keep evidence states explicit: fixture, live, shipping unknown, wrong variant, stock unconfirmed, no comparable sources, unknown costs.
- Refresh OPEN-room totals when another client leaves; the server already persists that event.

## Why sellers might accept

The proposed benefit is a profitable batch of qualified demand with less acquisition effort, inventory clearance or better capacity utilization. It is a hypothesis for Maxx, not validated merchant demand. Sellers and stock currently remain simulated; there is no real merchant negotiation integration or payment guarantee.

Seller decision rule:

`group revenue − product cost − shipping/fulfilment − expected returns − payment/platform fees − acquisition effort`

must meet that seller's required profit and be attractive relative to its available alternatives. Volume alone does not imply cheaper fulfilment: 100 separate delivery addresses still require 100 fulfilments. Margin floors, capacity, minimum batch size, shipping, returns, payment certainty and merchant approval are essential commercial constraints. The current engine enforces simulated floors/stock, not all of those commercial conditions.

Illustrative arithmetic, not measured merchant economics: retail $200 − product $120 − fulfilment $15 − expected returns $5 − acquisition $30 = $30 contribution. Group $180 − product $120 − fulfilment $15 − returns $5 − 5% platform fee $9 = $31 contribution. If the merchant's real acquisition savings are smaller, the group offer may be worse and should be declined.

Initial seller validation should focus on willing DTC/excess-stock sellers or suitable services, confirm minimum batch and net economics, and request written quotes on real batches. Do not claim arbitrary major retailers will discount because an AI asks them to. A single-buyer fixture win validates software flow, not collective bargaining power.

## Validation after design approval

Frontend lint, typecheck, existing state tests and production build; focused regression coverage for the cross-client leave refresh and meaningful derived price/offer data; desktop and 360px browser inspection of scan/confirmation/commitment/room/outcome; success/no-deal/withdrawal fixture paths; console and keyboard checks; preserve server numeric rules and secrets. Run production build separately from the user's development server because both use `.next/`.
