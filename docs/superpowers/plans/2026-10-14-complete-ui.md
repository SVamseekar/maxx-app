# Complete Maxx UI Implementation Plan

**Goal:** Execute the approved full-interface audit with a product-specific visual identity and every page/control covered.
**Architecture:** Keep backend contracts, auth, payment guards and existing state helpers intact. Replace the ornamental theme with a coherent token/control layer, rebuild the public entry, and improve domain-specific navigation/filtering across buying and operations.
**Tech Stack:** Installed Next.js, React, TypeScript, Motion, self-hosted Manrope, native HTML controls and dialog.
**Spec:** ../../design/2026-10-14-full-ui-audit/audit.md
**Execution:** User explicitly requested immediate implementation in this session. Preserve existing uncommitted work. No publication or real payments.

## Review focus
- Unknown product imagery must use a truthful fallback.
- Filters must expose empty/reset states and never change monetary calculations.
- Confirmation dialogs must retain keyboard focus, Escape and explicit destructive consent.
- All pages must work with reduced motion and narrow screens.
- Authenticated views require controlled browser fixtures if no test-role sessions exist.

## Tasks
- [x] Shared foundation: tokens, responsive header, controls, accessible confirmation provider, recovery routes. Files: components/ui.tsx, components/confirm-provider.tsx, components/filter-toolbar.tsx, components/product-identity.tsx, layout.tsx, design.css, template.tsx, error.tsx, loading.tsx, not-found.tsx. Validate lint/typecheck and keyboard interaction.
- [x] Product entry: rewrite page.tsx and live-bloc.tsx; add a controlled demo video component and real local recorded demo. Remove decorative chart and clearly label demo data. Verify anonymous desktop/mobile rendering and media fallback.
- [x] Buying: unify Bloc filters and product identity, add history/order/receipt filters, refine room/verdict/demand and payment surfaces. Preserve state/price tests. Test zero matches and reset.
- [x] Accounts and operations: section navigation, auth artwork, consistent confirmations, seller/admin filters and tab keyboard behavior. Use isolated browser response fixtures for role-specific visual checks; never fabricate live server evidence.
- [x] Content: redesign shared marketing, FAQ search, policy directory, policy contents navigation, judge/transparency. Verify every route and all 15 policy slugs.
- [x] Validation: lint, typecheck, frontend tests, isolated production build, browser coverage across themes and motion states, screenshots and final coverage report. Record material limitations honestly.
