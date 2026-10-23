# Maxx: full interface audit and redesign brief

14 October 2026 · Initial codebase scan complete · Proposed direction, not an implemented redesign

## Brief

Modernize every page and every control for a public launch and hackathon submission. The user explicitly prohibits an AI-generated template aesthetic. Success means a distinctive Maxx identity, thoughtful interactions, real product storytelling, readable operational screens, and consistent quality across the entire application. Motion and video must have a clear purpose.

The existing research records a preference for graphite, platinum typography and restrained blue, and rejection of generic light/violet concepts. This proposal retains the preference for dark surfaces while removing the ornamental patterns now competing with the product.

## What was scanned

- Active app repository: `maxx/`. The parent folder contains hackathon planning and archived work, rather than a second application.
- Structural inventory of 276 source, test, migration, documentation, deployment and evaluation files: 29,097 lines at the time of scanning. Excludes dependencies, build output, secrets, generated concepts, caches and archived planning. This is a structural scan with focused code reads, not a line-by-line correctness audit of every backend module.
- 28 Next.js page templates. The legal slug template expands into 15 policies: 42 route entries when each policy and the negotiation-room pattern are counted individually. Individual Bloc IDs add instances, not new page designs.
- 37 files under `components/`, including the seller type module; 17 API proxy route files; five global CSS files totaling 974 physical lines, many containing multiple rules per line.
- TypeScript AST inventory records 233 control declarations/component invocations with source locations. This is a source count, not a count of rendered controls: mapped rows and conditional states produce additional instances.
- Frontend source read in depth: app shell, navigation, shared forms, motion, scan/verdict, Bloc discovery, room/SSE, conversation, demand, money approval, checkout, account/data, orders, seller application and console, admin, document renderer. Other pages and backend modules were mapped through imports, handlers, endpoints and structure.
- Repository already contains extensive modified and untracked work. No product files were edited, reset or committed during this scan.

See `source-inventory.json` for file fingerprints, imports, functions, components, endpoints and control locations. Inventory excludes this audit directory itself.

## Architecture to preserve

Next.js App Router and React frontend, Motion animation library, Lucide icons, self-hosted Manrope font. The actual interface relies heavily on hand-written global CSS despite Tailwind being installed. Browser requests use same-origin Next.js API proxies; FastAPI owns authentication, seller workflows, order fulfilment, PayPal/simulator flows, scanning, negotiation and persistence.

`layout.tsx` owns the nonce-bearing theme script, motion/auth/reauth providers, header, email verification banner and footer. `template.tsx` currently adds an entrance animation to every navigation. `proxy.ts` handles anonymous redirects and CSP. Read the installed Next.js guides specified by `apps/web/AGENTS.md` before implementing framework changes.

Negotiation uses saved snapshots and SSE. Preserve event ordering, replay, reset-generation handling, withdrawn-offer exclusion, maximum-price enforcement and decimal-money formatting. Preserve authentication and explicit payment approvals, including reauthentication and exact-total confirmation. A visual refresh is not authority to weaken any of these flows.

## Findings that should drive the redesign

1. **The decorative layer conflicts with the new brief.** `motion.css` adds aurora blobs, a dot grid, shimmering status text, cursor-following spotlights, lifting cards, infinitely rotating button outlines and broad fade/blur entrances. Remove these as global treatments. Reserve animation for a useful change or a deliberately composed product demonstration.
2. **Too much content shares one card treatment.** Marketing steps, benefits, policies, operational panels and products are frequently similar bordered rounded rectangles. Differentiate through composition, hierarchy, density and material, not a second accent color.
3. **The first screen needs stronger product identity.** The home hero is headline/copy plus a stats card. Lead with the physical purchase and the group negotiation around it. Avoid a disconnected abstract AI illustration.
4. **One graphic misrepresents its source.** `components/live-bloc.tsx` draws `SHAPE = [100, 88, 80, 66, 54, 40, 28, 16]` while describing it as buyers by maximum price. The live counts are real API data; the bars are not. Derive a curve from actual data or explicitly label/remove the illustration.
5. **Product identity is generic on discovery screens.** `/blocs` and `/my-blocs` use a headphones icon for every product. Use verified product imagery where available and a considered category/typographic fallback; do not present unrelated imagery as the actual item.
6. **Filters are fragmented.** Bloc status/search, conversation search, seller tabs, reauthentication tabs, country selections, payment methods and operational selections use separate patterns. Standardize selection, focus, clearing, result counts and small-screen behavior. Keep labels aligned with real backend states.
7. **Destructive confirmations use mixed surfaces.** Order cancellation, seller refunds, passkey removal and admin actions use browser `window.confirm`; PayPal and reauthentication use custom dialogs. Introduce a consistent accessible confirmation dialog without reducing confirmation strength.
8. **Several account pages lack navigation within long content.** Account profile, passkeys, MFA, providers, devices, activity, addresses, subscription and deletion are one vertical experience. Introduce clear section navigation and focused editing surfaces.
9. **Seller/admin pages need operational density.** Demand, offers, fulfilment, disputes, reviews and audit records should support scanning and decisions. They should not become enlarged marketing cards.
10. **Global and embedded motion can overlap.** Page template, auth shell and individual elements each animate. Consolidate timing; protect focus, reading position and reduced-motion preferences. Do not hide useful content until a decorative sequence finishes.
11. **Error/loading infrastructure is uneven.** There are component-level states but no app-specific `error.tsx`, `loading.tsx`, or `not-found.tsx` files in the scanned app. Add appropriate route recovery and missing-page designs as part of coverage.
12. **The asset library is small.** Public assets contain two product artwork images and five screenshot samples. No video asset exists. A premium video treatment needs an actual asset, poster, playback behavior and fallback; an empty video container does not count.
13. **Launch copy needs reconciliation.** `lib/site.ts` has prototype entity/contact defaults. Marketing includes broad assurances, while some auth/Bloc components still hardcode simulation language. Tie capability statements to actual modes and reconcile contradictory claims with the backend and existing operator checklist. This audit does not certify payment, legal or launch readiness.

## Proposed art direction

**Recommendation: a product-led buying experience with a precise negotiation workspace.** The recognizable Maxx moment is seeing independent buyers become enough demand to receive a better offer. Express that through physical product composition, aggregate demand and price movement backed by actual events.

Two alternatives considered: a fully cinematic site would offer stronger first impressions but burden everyday operational tasks; a dense trading-terminal treatment would suit negotiations but make onboarding and shopping feel technical. Use a composed product scene on the public entry points and clear, compact workspaces for active tasks.

### Visual foundation

- Graphite `#202324`: primary dark canvas.
- Carbon `#2A3031`: raised surfaces, used selectively.
- Platinum `#EDF0EA`: primary text and neutral emphasis.
- Stone `#A9B1AD`: secondary text, subject to contrast measurement.
- Glacial blue `#7DC7CD`: selected interactions and price references.
- Sage `#9EC5A1`: successful allocations and completed states; never the only status cue.

These are candidate tokens for visual review, not yet validated accessible color pairings. Light mode needs its own deliberate contrast and surface scale.

Use the existing self-hosted Manrope as a practical starting point; create identity through a considered wordmark, firm display hierarchy and highly legible tabular prices. Body copy should generally be 15–16px, forms at least 16px on mobile, and long text limited to roughly 65–75 characters per line. Avoid forced line breaks that only work at one viewport.

Use a 12-column desktop grid with generous but purposeful space. Each page type gets its own information layout. Use few surface levels, consistent spacing and radii based on function. Align text and actions to the same grid. Remove gratuitous all-caps labels and repeated arrow decorations.

### Page composition

```text
Public entry                  Buying workspace
Navigation                    Navigation + context
Headline | product scene      Product + actual state
Action   | group/offer moment  Evidence | decision panel
Live proof with mode label    Sources  | price limit/action
Process explanation           Detailed history when needed

Negotiation                   Seller / operator
Product + group context       Workspace navigation
Your limit | best offer        Attention queue + filters
Conversation | offer book      Work list | selected detail
Demand + settled outcome      Persistent action feedback
```

### Motion and video

- A single composed opening moment on the homepage: the product remains anchored while buyer commitments and an offer visibly relate to it. Any illustrative sequence is labelled as such.
- Short transitions on selected filters, expanded evidence, dialog opening, wizard steps and refreshed results. Working target: 140–220ms controls, 220–320ms panels, longer motion only for a deliberate demonstration.
- In the room, animate actual newly received offer/price changes once. History remains stable. Preserve manual scrolling and the jump-to-latest control.
- Use a self-hosted product film or recorded demo with a poster, visible playback controls, captions when spoken, and a static equivalent. Pause when offscreen; avoid download until relevant. The film cannot imply generated scenes are live activity.
- Prefer a click-to-play demonstration. If a muted decorative loop is used in the hero, provide pause, stop for reduced motion, and keep it out of forms, legal pages and operational screens.
- Every interaction works with animation disabled. No infinite border beams, global aurora, scroll hijacking, cursor trails, autoplay sound, fake progress percentages or artificially delayed actions.

## Route coverage: nothing omitted

All rows below are redesign obligations. None is marked implemented.

| Route/template | Complete scope |
| --- | --- |
| `/` | Product composition, honest live Bloc, demo/video, process, buyer/seller entry, disclosures, FAQ |
| `/scan` | Empty/upload/drag/preview/remove, samples, ownership, working/error/retry, corrections, verdict, score, sources, checkout |
| `/blocs` | Search, all/open/completed selections, count/reset/no results, product cards, match candidates, custom variant, confirmation/create, demo reset |
| `/blocs/[id]/room` | Loading/missing, open/expired/negotiating/settled/failed, viewer/member/owner, limit slider, hold, leave/start, reconnect, conversation/offers/search/copy, demand, history, settlement |
| `/my-blocs` | Member/creator/left/won/unserved/released states, useful overview and product identity |
| `/orders` | Empty/loaded/error, needs-address summary, saved/new address, shipment, delivered, cancel/refund, trader details, report/reply/withdraw/history |
| `/receipts` | Disabled/loading/empty/error, totals, all payment statuses, identifiers and Bloc links |
| `/account` | Profile/email, passkeys, MFA/recovery, password/providers, devices/trusted devices, security activity, addresses/export, Plus, deletion |
| `/login` | Email link/password/passkey/OAuth, MFA, recovery, captcha, pending/resend/failure and return destination |
| `/signup` | Fields, agreement, captcha, OAuth, pending/resend/errors |
| `/complete-signup` | Invalid/expired/verifying/completed link, password/passkey setup |
| `/signin-link` | Verifying/invalid/expired/completed, MFA and safe return |
| `/verify-email` | Verifying/invalid/expired/success and next action |
| `/forgot-password` | Email entry, validation, submitted/resend/error |
| `/reset-password` | Missing/expired token, password strength, saving and completion |
| `/sell` | Application wizard, payout verification, review/rejected/suspended/closed; active offers/orders/problems/account tabs |
| `/admin` | Unauthorized/loading/error, health/freeze/reconcile, seller approval/rejection/suspension, disputes, recent sellers and audit log |
| `/judge` | Scenarios, entry instructions, reset, mode and evidence, success/no-deal/withdrawal paths |
| `/under-the-hood` | Model configuration, real provider records, refresh, no calls/error states, mode/cost disclosures |
| `/how-it-works` | Visual group journey, differing allocations, shipping/refunds, readable examples |
| `/for-sellers` | Seller economics, eligibility, onboarding, fee illustration and responsibilities |
| `/pricing` | Buyer/seller fees, Plus, payment costs, limits and clear comparisons |
| `/trust` | Money lifecycle, agency limits, responsibilities and evidence |
| `/faq` | Categories, coherent accordion behavior, links and optional local search |
| `/about` | Product rationale, honest prototype/team status and next actions |
| `/contact` | Clear support paths and actual configured contact details |
| `/legal` | Policy directory organized by purpose/audience; useful finding/navigation |
| `/legal/[slug]` | Readable document layout, metadata, desktop/mobile contents, tables, anchor offsets, related documents, unknown slug |

The 15 policy pages must each be checked: `/legal/terms`, `/legal/privacy`, `/legal/cookies`, `/legal/acceptable-use`, `/legal/seller-terms`, `/legal/prohibited`, `/legal/refunds`, `/legal/payments`, `/legal/consumer-rights`, `/legal/ai`, `/legal/security`, `/legal/accessibility`, `/legal/imprint`, `/legal/notice-and-action`, `/legal/subprocessors`. Preserve policy substance during the visual pass; factual/legal changes are a separate concern.

## Controls and embedded states

| Surface | Obligations beyond the route's first screen |
| --- | --- |
| Navigation | Active state, anonymous/authenticated menu, account menu, theme, motion preference, mobile destinations, footer and verification banner |
| Discovery | Search input, status control, result counts, clear/reset, keyboard focus and no-result recovery |
| Product matching | Candidate radio selection, custom product, confirmation checkbox, validation and busy state |
| Negotiation | Range input, precise amount presentation, conversation/offers tabs, message search, clear/escape, copy feedback, reconnect, unread/latest, expandable offers |
| Money | Hold terms, loading/cancel/error/decline, simulator/sandbox distinctions, PayPal buttons, payment method radios, typed-total approval, PYUSD address/copy/hash/verification |
| Account security | Show password, strength feedback, passkey naming/removal, MFA setup/QR/code/trust/recovery, reauth method tabs, session revoke, provider unlink, delete confirmation |
| Seller application | Four steps, back/next/validation, company/individual radios, country, shipping deadline, destination checkboxes, return window, policy text and certification checkboxes |
| Seller operations | Offer floor/opening/stock/strategy, pause/resume, results, carrier/tracking, case reply/refund, payout/profile settings |
| Buyer fulfilment | Address selector/country/new form, status timeline, cancellation dialog, problem kind/text/reply and past cases |
| Operator | Review notes, approve/reject, freeze/resume, reconcile result, refund decision, suspend/reinstate and audit rows |
| Content | FAQ expansion, policy contents and anchors, responsive semantic tables and related links |
| Global feedback | Focus/hover/press/disabled/busy/error/success, retry, unauthorized/expired session, skeleton/empty/offline, unknown route and route error |

Use shared primitives for fields, segmented controls, tabs, selects, disclosures, dialogs, status feedback and data tables. Shared visuals must not erase domain-specific semantics. Large option lists can use a searchable selection surface; small enums should remain simple. Keep native input semantics and keyboard behavior.

## Implementation sequence after design alignment

1. Establish token, typography, shell and accessible interaction foundations. Replace the decorative global layer and add recovery surfaces.
2. Build the distinctive public landing and scan/verdict experience, including the actual media asset and static fallback.
3. Complete discovery, product confirmation, room, offer book, demand and all payment states.
4. Complete buyer history, orders, receipts, authentication and account/security workflows.
5. Complete seller application and all console tabs, then admin operational surfaces.
6. Complete every explanatory/policy page, judge and transparency experience; reconcile navigation and capability copy.
7. Verify the entire coverage matrix across roles, viewports, themes and motion preferences. Compare screenshots against the art direction before calling the refresh complete.

## Baseline evidence and limitations

- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `npm test --workspace @maxx/web`: 36 passed, zero failed.
- Desktop browser navigation covered 41 concrete static/policy paths plus one existing negotiation room. Public paths rendered successfully. Six protected paths (`/my-blocs`, `/orders`, `/receipts`, `/account`, `/sell`, `/admin`) redirected to login, as expected for the anonymous browser. Their interiors were source-reviewed, not visually verified.
- At 360×800, ten representative routes plus the room were checked for page-level overflow: none found. This is not a complete accessibility audit. Wide semantic tables use their own overflow container.
- Baseline screenshots: `home-before.png`, `home-mobile-before.png`, `scan-mobile-before.png`, `blocs-mobile-before.png`, `room-mobile-before.png`, `room-desktop-before.png`.
- Browser log reported two hydration warnings involving injected `caret-color: transparent` attributes during the screenshot sweep. The shown diff does not establish a product-code cause; reproduce in an isolated browser before treating this as an application defect.
- No production build, backend suite, authenticated workflow mutation, paid scan, payment, provider evaluation or deployment was performed. The running development server was left intact.
- Visual completion will require controlled buyer/seller/admin test sessions and fixtures for every state. Existing tests mainly validate business/presentation helpers; they do not prove browser layout, accessible dialogs, media playback, mobile navigation or full interaction coverage.

## Acceptance standard

- Every route and control family above has explicit evidence, including empty/error/loading states and protected role-specific screens.
- Distinct compositions serve shopping, negotiation, operations and reading. No generic card grid is reused simply to fill space.
- No decorative graphic is presented as real evidence. No fabricated savings, users, endorsements, progress, live activity or product photography.
- All actions remain connected to their existing behavior. Filters work with zero and many results; selection remains visible and recoverable.
- Keyboard navigation, focus trapping/restoration, field labels, screen-reader status and contrast are verified; reduced motion and light/dark themes remain usable.
- Layouts checked at 360, 390, 768, 1280 and 1440px; no accidental horizontal page clipping. Legal tables may scroll within labelled containers.
- Media has a real local asset, poster, fallback and playback controls. It does not delay reading, signup or purchase approval.
- Run lint, typecheck, meaningful frontend tests and an isolated production build. Exercise success, no-deal, withdrawal, payment failure, expired auth and network recovery paths without spending real money.
- Preserve prior work and backend contracts. UI polish must not be described as production/payment/legal readiness without separate evidence.
