# Active Nebius PRD audit

Reviewed 2026-10-08 against `../nebius-nvidia-hackathon/01-PRD.md` (Approved for build)
and `02-tech-spec.md`. Optional features and PayPal are deferred by user instruction.
Implemented means code plus local evidence; external providers remain **UNVERIFIED**.

| Requirement | Implementation / local evidence | Remaining gap |
|---|---|---|
| A1 / FR-1, FR-2 | Typed PNG/JPG/WebP screenshot extraction, ≤8 MB validation, editable fields, real Nebius image/normalise adapters and labelled hash fixtures | URL/text input absent; authenticated IDs/image support and 40-image benchmark unverified |
| A2 / FR-4 | Deterministic Decimal Money Score; 15-point bonus only for canonical matching OPEN Bloc with future deadline, fresh target evidence and target below seen price; clamped 0–100 | Live evidence quality unverified |
| A3 / FR-5 | Sourced recommendation and numeric guard; JOIN_BLOC primary move links the qualifying Bloc | Other deferred optional moves absent |
| FR-3 / tech §6 | Tavily basic Search (8), conditional Extract (top 3); Postgres six-hour product/variant/quantity/currency/purpose cache; exact expiry/refetch/restart tests. Bloc refresh searches price history/deals; trusted independent delivered-price median, no seller-floor input | Live Search/Extract and historical source quality unverified; target remains unknown when fewer than two trusted rows exist |
| B1 / FR-7 | 50 demo identities, hard variant/brand exclusions, uncertain confirmation, injectable live embedding matcher, Postgres demand signals; catalogue reuse excludes expired OPEN Blocs | Illustrative catalogue not merchant-verified; confidence not calibrated; demand recorded on confirmed catalogue Bloc selection/creation rather than every scan; custom creations do not emit demand signals |
| B2 | Persisted countdown/automatic close while worker runs; HELD committed totals; target sources and deterministic affordability reasoning. Fixtures explicitly label simulated price history | Free-host sleep delays deadline execution until wake; hosted execution unverified |
| B3–B5 / FR-8 | Simulated holds/releases, bounded maximum, deterministic allocations and personal seller/price/savings or failure | BELOW_CLEARING combines price/capacity explanation without computing “$X short”; another client's leave persists correctly but watching room totals stay stale until refresh/reconnect; hash-chain absent/deferred |
| C1 / FR-11, FR-12 | Five-round / 90-second bounded runner, real tools, SSE durable replay, round price table | Table instead of chart/allocation bar; live 813-buyer performance unverified |
| C2–C4 / FR-9, FR-10 | Eight distinct private personas (wholesaler, premium, liquidator, boutique, competitor, patient distributor, seasonal, risk-averse); fixture concession policies differ; all outputs floor/stock-clamped. Deterministic auction/property/privacy checks | Live persona effectiveness unmeasured; sellers and stock remain simulated even with live models |
| C5 / FR-14 | Failure seed floors exceed maxima, all releases; withdrawal/reclear; reset restores 800 buyers across three scenarios and eight sellers each | Live models may legitimately return no deal; success not promised |
| D1 | Resettable one-tap judge identity, seeded success/failure/withdrawal, sample scans | Demo-only identity; hosted cold start unverified |
| D2 / FR-15 | Under-the-hood modes, IDs, safe tokens/status/latency and per-call Decimal cost estimates from explicit dated rates. Metadata stored in Postgres, no prompts/images/private seller data | Current rates and actual live costs unverified; missing usage/rates show unmeasured, never assumed free |
| Durable application state | Single Postgres DATABASE_URL; Alembic tables for Bloc documents, demand, cache, queued jobs, append-only event journal and model calls. Snapshot/event/job writes transactional, CAS revisions, atomic claim. Queued work resumes; interrupted RUNNING work fails/releases; provider-mode change fails safely. Actual Postgres restart/replay probe passed | One API instance/worker required; hosted backup/restore, disconnect/restart and SSE unverified |
| Upload storage | Synchronous RAM-only processing; no retained image files or image DB rows. Public bundled samples are synthetic. Paid disk removed | Provider retention policy unverified; future retained uploads need private object storage and ≤7-day deletion; not implemented or required for this flow |
| Goals / evaluations | Separate fixture/live commands: 5 images/25 fields, 60 matching cases, 200 random auctions (188 partial), 3 streamed fixture negotiations | Representative 40 screenshots, 50 multi-round quality/savings trials, live latency/cost unmeasured |
| Hosting | Docker API/web, Postgres Compose volume, migration-before-start; Render free web/API blueprint with external Postgres and no application disk. Auto deploy off, no publication | Docker execution and hosted checks unverified. Free allowances/sleep do not guarantee always-on timing; always-on compute and provider usage can cost money |
| Optional/P1/P2 | PayPal, production auth, seller dashboard/discovery, counter/cancel, streak/share cards and hash-chain deferred | Not claimed complete |

PRD summary says uniform price; C3 and the specified algorithm assign the accepted
seller's price to each buyer. Implementation follows C3. This remains a spec
inconsistency, not a uniform-price guarantee.

Evidence: `nebius-core-verification.md`; test categories: `test-audit.md`;
persistence/deployment design: `storage-and-deployment.md`. All operator actions,
variables, commands and expected results are solely in `operator-actions.md`.

8 October checkpoint review: 64 backend and 7 frontend tests, all static checks and
production build passed. Actual local Postgres probe and three-scenario fixture
HTTP/SSE evaluation passed again. Terminal snapshots and both SSE cursor forms
survived an API process restart. Confirmed expired-Bloc reuse and closing-reserve
defects were fixed with failing-before/passing-after regression tests. No other
outstanding material correctness/privacy/persistence defect was found in the
reviewed core paths; the cross-client leave UI gap is recorded above. Review scope,
inventory and limitations: `checkpoint-review.md`.
