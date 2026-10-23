# UI implementation and validation — 2026-10-14

## Implemented

Shared graphite, paper and sage visual system across public, buying, account, seller, operator, authentication and policy routes. Responsive navigation, light/dark themes, consistent form states, searchable collections, animated filter selection, native confirmation dialogs, page recovery states and section navigation.

Three original illustrative images were generated using the built-in image tool. Final asset paths and exact prompts are in artwork-prompts.md. Images appear in discovery, screenshot scanning, the buying explanation, seller content and the about page. They are labelled illustration, not merchant inventory photography.

The buying journey has keyboard-operable tabs, a price-limit slider, staged offer animation and a drawn outcome confirmation. Pricing includes a working fee calculator; trust and how-it-works include an interactive hold/charge/release explanation. Existing scan and negotiation animations remain tied to their actual states. Motion can be paused and follows the device preference.

The homepage video is a 14-second recording of the running prototype, with native playback controls, an original screenshot poster and descriptive English captions. Playback pauses offscreen. No autoplay or audio. Simulated offers and payments are explicitly labelled. Video assets are local; no third-party embed.

## Evidence

- ESLint: passed after excluding isolated generated build output.
- TypeScript: passed.
- Frontend tests: 38 passed, 0 failed.
- Production build: passed, all 48 generated entries completed. Built with MAXX_BUILD_DIR=.next-ui-review, keeping the development server separate.
- Production browser: no console or page errors during home rendering, journey interaction, theme changes and motion pause. Verified reduced state.
- 21 public route instances tested at 360px with reduced motion: HTTP 200, no document overflow, no page errors. Includes all public marketing/auth routes, scan, groups, demo room, judge and transparency.
- All 15 policy documents: HTTP 200, expected title, no desktop overflow. Unknown route returns 404.
- Six protected routes reviewed with browser-only synthetic API responses at 390px: account, my-blocs, orders, receipts, seller and admin. All loaded their real components with no page errors or horizontal overflow. No fixture calls reached the backend. Seller's four tabs were checked.
- Search and reset checked on groups, FAQ, personal groups, orders, receipts, seller demand and admin sellers.
- Keyboard journey navigation, mobile-menu Escape, native confirmation Escape and focus restoration verified.
- Fee calculator at $200: $10 platform fee, $190 payout before processor fees. No-deal explanation releases the illustrative $180 hold.
- Video metadata and playback verified: 14 seconds, playable.
- Desktop, mobile and light-theme captures saved in this directory. Additional protected-screen captures are in /private/tmp/maxx-*-mobile.png. The fixture browser script is retained beside this report.

## Local runtime

Frontend: http://127.0.0.1:3001. Backend: http://127.0.0.1:8000. Local PostgreSQL: 55432. Applied the repository's pending local Alembic migration to fix the missing bloc status index columns and restarted the backend successfully. No database reset.

## Limits

This is a UI implementation and browser review, not live-commerce certification. Protected browser checks use fixtures and do not prove authentication, delivery, payout or dispute lifecycle correctness. No real payment, email, paid model call, deployment or publication was triggered. The app remains a labelled prototype. Shared styles cover all routes; not every possible error or authorization state was manually exercised.

## Control-motion refinement

Added interactions.css after the existing design layer. Primary controls lift 2px on mouse hover and compress to 98% on press with an 85ms response; icon controls compress to 92%. Directional action icons move toward their destination. Filter/tab targets remain steady while their existing selection indicators move. Focus rings, search focus-within, range-thumb feedback, account chevrons, native dialog entry/exit and server-confirmed success feedback now share timing rules. Hover enlargement applies only to fine pointers with hover support.

SubmitButton keeps its original dimensions while replacing the visual label with a centered spinner. The accessible label remains, with aria-busy and an in-progress description; duplicate submission stays disabled. There is no simulated success state. Reduced-motion and the in-app pause switch remove transforms and transitions.

Validation: lint, TypeScript, 38 tests and an isolated production build passed. Browser checked primary hover (-2px), press (scale .98 / +1px), paused motion (no transform), and delayed mocked login response (440x44 button before/during, busy then idle). Rechecked all six protected routes and seller tabs at 390px with motion enabled: no overflow or page errors; Escape closed the confirmation and restored focus. Browser fixtures intercepted requests; no real login or payment mutation was performed.
