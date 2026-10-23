# Security

Reviewed 13 October 2026. This is what the app does to protect people and their accounts, what was
checked, and what remains the operator's job. Nothing here is a claim of a third-party audit.

## Threats this design answers

| Threat | Defence |
|---|---|
| Guessing, stuffing or phishing a password | Passkeys (phishing-proof), two-step verification, breached-password screening, per-account and per-address throttles, optional Turnstile after repeated failures |
| Taking over an account by pre-registering its email | Verify-first sign-up: nothing is created or chosen until the mailbox owner opens an emailed link; no password exists to inherit |
| Learning who has an account | Sign-up, sign-in, reset and email-link responses are identical whether or not the address is registered; unknown addresses take the same time as wrong passwords |
| Stolen session cookie | `HttpOnly`, `SameSite=Lax`, `Secure` + `__Host-` prefix over https; ids stored only as SHA-256; absolute 30-day cap and 14-day idle timeout; new id on every sign-in and privilege change |
| Cross-site request forgery | Fetch Metadata (`Sec-Fetch-Site`) check, `Origin`/`Referer` allow-list, `SameSite` cookies, JSON-only bodies |
| Script injection | Strict nonce-based Content-Security-Policy with `strict-dynamic`; no inline script; framework escapes output; provider-supplied links are rendered only when plain http(s) |
| Clickjacking, MIME sniffing, referrer leaks | `X-Frame-Options`, CSP `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`, COOP/CORP, HSTS over https |
| A hijacked session changing the sign-in method | Re-authentication (passkey, authenticator code, password or emailed code) is required for passkey, two-step, password, provider, device and deletion changes |
| Silent compromise | Security activity trail, email alerts for new devices, password and two-step changes, recovery-code use and passkey changes |
| Database leak | Passwords salted scrypt; session, reset and sign-in tokens, recovery codes and trusted-browser tokens stored as digests; authenticator seeds AES-256-GCM encrypted with a per-purpose key |
| Replay of a one-time code | TOTP time step is claimed atomically and can never be reused; recovery codes burn on use; challenges and email links are single use |
| Abuse and floods | Global per-address budget, hourly scan allowance, per-address and per-Bloc live-stream caps, request-size and content-type limits |
| Insecure production configuration | The API refuses to start in `ENVIRONMENT=production` without https, a real `SECRET_KEY`, SMTP mail, a non-default database password and explicit `ALLOWED_HOSTS`; API docs are off |

## Controls in detail

- **Passwords.** Salted scrypt (32 MiB per hash). Minimum 10 characters, up to 128, spaces and any
  characters allowed, no composition rules or forced rotation (the direction of NIST SP 800-63B).
  New passwords are screened against Have I Been Pwned using k-anonymity: only the first five
  characters of the SHA-1 leave the server, with response padding. If the service is unreachable
  the check is skipped, never blocking people.
- **Sign-up and sign-in.** Email link first, then a passkey or password. Email-link sign-in for
  people without a password. OAuth (Google, Apple, Microsoft, GitHub) with PKCE, a browser-bound
  state, nonce and verified ID-token signatures; see `docs/accounts.md`.
- **Two-step verification.** RFC 6238 TOTP (SHA-1, 6 digits, 30 s, one window of drift), a
  per-account replay high-water mark, five wrong codes burns the pending sign-in, ten single-use
  recovery codes, and optional 30-day "trust this browser" tokens that are revoked on password
  change, reset, two-step changes and "sign out everywhere".
- **Passkeys.** WebAuthn with discoverable credentials, user verification required, attestation
  `none`, signature counter checked (cloned authenticators are refused), challenges single use and
  bound to the account. A passkey satisfies two-step on its own.
- **Freshness.** Sensitive actions need a check within `REAUTH_MINUTES` (default 10). The browser
  shows a dialog and retries the action automatically.
- **Headers.** API: nosniff, frame deny, `no-referrer`, `Cross-Origin-Resource-Policy`, `no-store`
  on account and Bloc data, HSTS over https, a CSP of `default-src 'none'`. Web: a per-request
  nonce CSP (scripts, styles, images from `self`, `data:`, `blob:` and provider avatar hosts,
  `form-action 'self'`, `frame-ancestors 'none'`), Permissions-Policy (passkeys for our origin only),
  COOP/CORP, HSTS. Pages are rendered per request because the nonce changes each time.
- **Network edge.** Allowed `Host` names, a 64 KiB body cap (8 MiB for screenshots), a JSON-only
  content-type allow-list, a 600 requests/minute per-address budget, and no CORS at all.
- **Data minimisation.** Account ids never reach other buyers (your own membership is `me`); the
  activity trail keeps only the network (IPv4 /24, IPv6 /48), never a full address; deleting an
  account removes sessions, links, passkeys, recovery codes, trusted browsers and events, and
  anonymises past Blocs.
- **Supply chain.** `make audit` runs `npm audit` and `pip-audit` over locked versions. Both were
  clean at the review date (a vulnerable `cryptography` 47.0.0 was upgraded to 50.0.2 first).

## How it was checked

- Backend: 177 tests, including a software passkey authenticator that builds real attestations and
  assertions, a simulated identity provider that signs real RS256 ID tokens, and deliberate
  mutation checks (removing the signature, nonce, user-verification or account-binding checks makes
  tests fail).
- Frontend: lint, strict types, 30 unit tests, a production build with zero CSP violations across
  every page, and axe (WCAG 2.1 AA) with no violations on 42 page states in both themes at 1440 and
  360 px, including the two-step setup and re-authentication dialog.
- Browser journeys against the real Next.js → FastAPI → Postgres stack with a virtual
  authenticator: email-link sign-up, passkey creation, passkey sign-in, password, authenticator
  enrolment with recovery codes, second-step sign-in, wrong code refused, trusted browser, stale-
  session re-authentication, account deletion.

## What is still yours to do

1. Set the production environment (see `.env.example`): `ENVIRONMENT=production`, an https
   `PUBLIC_BASE_URL`, `SECRET_KEY` (32+ random characters, kept secret and backed up: losing it
   makes stored authenticator seeds unreadable), SMTP credentials, `ALLOWED_HOSTS`, a strong
   database password, OAuth client secrets.
2. Terminate TLS in front of both services and set `X-Forwarded-For` at that proxy. Keep the API
   private (only the web service should reach it) and keep `TRUST_PROXY_HEADERS=true` only then.
3. Put the web app on its own registrable domain: passkeys bind to the host.
4. Set the `security.txt` contact and a real `Expires`.
5. Run `make audit` in CI and on a schedule; rotate secrets if a key is ever exposed.
6. Back up the database and test restores (`docs/storage-and-deployment.md`).
7. Consider Turnstile (`TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET`) before public launch.

## Payments (see [payments](payments.md))

- Maxx never sees a card or PayPal login: PayPal's own window collects approval. The PayPal client
  secret stays in the API; the browser only gets the public client id.
- Money moves only from a cleared Bloc, and a capture is the minimum of the member's maximum, the
  ledger row and the winning price. Every PayPal write carries a deterministic request id.
- The webhook endpoint is the one write route without an origin check, because PayPal is not a
  browser. It is authenticated by PayPal's signature (HMAC in simulator mode), rate limited,
  size limited, de-duplicated by event id, and cannot raise a capture above its hold. The Next.js
  proxy does not forward it.
- Agent checkout offers are HMAC-signed, bound to the account, expire, and are checked by a guard
  against the typed total and a per-plan limit. Payment rows can only be read or acted on by their
  owner; the group ledger shows aggregates only.
- PYUSD proof is read-only: exact token, recipient, amount and confirmation depth, and one
  transaction can pay one order. No wallet key is ever held.
- The Content-Security-Policy admits PayPal's sandbox origin only when the web app runs with
  `PAYPAL_MODE=sandbox`.
- Money limits, a fresh-identity requirement above set amounts, an emergency brake that pauses all
  payments, an append-only audit log, webhook replay refusal, remote reconciliation and secret
  redaction in logs are described in [payments](payments.md).
- Delivery addresses are encrypted at rest (AES-GCM with a purpose-bound key), readable only by the
  buyer and the seller of that order, and wiped 90 days after an order finishes. Seller payout
  addresses must be confirmed by code, changes need a fresh identity check and can wait out a
  cooling-off period before being paid. See [marketplace](marketplace.md).
- `GET /me/export` (fresh identity check) returns everything held about an account; closing an
  account voids holds and erases commerce data, and is blocked while an order or problem is open.

## Sellers, tracking and notifications (see [marketplace](marketplace.md))

- Two more provider webhooks skip the origin check: `POST /webhooks/identity` (Stripe signature,
  5-minute tolerance) and `POST /webhooks/tracking` (EasyPost HMAC; refused when tracking is off).
  Both are rate limited and size limited, and neither body is trusted: the identity session or
  tracker is re-read from the provider with the server's key before anything changes.
- A seller is paid from carrier evidence, not their word: the tracking number must match the
  carrier's format and check digit, cannot be reused across orders, and new sellers are paid only
  on delivery. Returned, unscanned, failed or wrong-country parcels hold the payout for a person.
- A seller's AI agent cannot spend past its limits: every bid is clamped at the execution boundary
  (floor, opening price, no increase, at most 15% of the opening price per round, stock). The room
  sees only that a bid was clamped, never which limit, so floors and stock stay private.
- Identity results, sanctions matches, tax ids (encrypted; last four shown) and names are fixed
  once screened: a seller cannot edit their legal name afterwards. Possible sanctions matches are
  decided by a person, never automatically.
- Notification emails carry only fixed sentences, link-free product titles and links to this
  site's own pages; text written by another person is never emailed. Reads and preferences are
  scoped to the signed-in account, and money, deadline and account emails cannot be switched off.
- The judge's seller tour runs only with the PayPal simulator. Its Blocs are unlisted and refuse
  real buyers; demo sellers sell only in their own tour and real sellers never join one.

## Known limits (honest list)

- Rate limits and lockouts are per process, which fits the single-worker API; a multi-worker
  deployment needs a shared store such as Redis.
- Eight wrong passwords lock that email for 15 minutes, so someone can briefly lock out an address
  they know. A passkey or an emailed link still works.
- A provider sign-in on an account with two-step verification still asks for the Maxx code (unless the
  browser is trusted), and a provider cannot attach itself by email to an account protected by
  two-step or a passkey: that account must link it from settings. Accounts *without* two-step rely
  on the provider's own checks.
- SHA-1 TOTP is what authenticator apps universally support; passkeys are the stronger option and
  are offered first.
- With `PAYPAL_MODE=off` or `simulator`, nothing here holds real money. With `sandbox`, only PayPal
  test money moves. Real payments would add seller onboarding, a chargeback and dispute process and
  fraud controls that are out of scope; live PayPal URLs are refused at start-up.
- Email is a recovery channel: anyone who controls a mailbox can use emailed links. Encourage
  passkeys and two-step on the mailbox itself.
- No external penetration test or formal audit has been done.
- Stripe Identity, EasyPost and PayPal Payouts have been exercised only through their simulators
  and mock transports here; the EasyPost signature header format in particular needs checking on
  the first real delivery.

## Research behind the choices

[NIST SP 800-63B-4 password and authenticator guidance](https://www.sakimura.org/en/2025/10/7710/),
[OWASP ASVS 5.0](https://cornucopia.owasp.org/taxonomy/asvs-5.0/07-session-management/05-defenses-against-session-abuse),
[RFC 9700 OAuth 2.0 Security BCP](https://datatracker.ietf.org/doc/rfc9700/),
[Fetch Metadata](https://web.dev/articles/fetch-metadata),
[Have I Been Pwned range API](https://troyhunt.com/enhancing-pwned-passwords-privacy-with-padding),
[TOTP replay protection](https://oneuptime.com/blog/post/2026-08-29-how-to-block-reuse-of-a-totp-code-during-its-30-second-validity-window/view),
[Cloudflare Turnstile server-side validation](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/index.md),
[Next.js Content Security Policy](https://nextjs.org/docs/app/guides/content-security-policy),
[nOAuth](https://workos.com/blog/noauth-microsoft-azure-ad-vulnerability).
