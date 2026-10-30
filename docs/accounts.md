# Accounts and sign-in

People create their own accounts with an emailed link followed by a passkey or password, or with
Google, Apple, Microsoft or GitHub. Everything below runs in the existing stack (Next.js →
FastAPI → Postgres); there is no third-party auth service. Security design, threat model and open
risks are in [`security.md`](security.md).

## What exists

| Capability | Where |
|---|---|
| Sign up by emailed link (`/complete-signup`), then choose a passkey or password; sign in with a passkey, password, or emailed link (`/signin-link`) | `/signup`, `/login`, account menu |
| Passkeys, authenticator-app two-step verification with recovery codes, trusted browsers | `/account` |
| Re-confirmation before sensitive changes (dialog), security checkup, security activity and alerts | `/account` |
| Google, Apple, Microsoft and GitHub sign-in (OAuth 2.0 / OpenID Connect, code flow + PKCE), link and unlink | `/login`, `/signup`, `/account` |
| Password reset (single-use, expiring links) | `/forgot-password`, `/reset-password` |
| Profile, password change, linked providers, signed-in devices, delete account | `/account` |
| "My Blocs": everything you created or joined, with your own limit and result | `/my-blocs` |
| Join, leave, create and close Blocs as *you* (no more shared `demo-you`) | Bloc room, `/blocs`, `/judge` |

Browsing Blocs, scanning a screenshot and reading a room stay open to everyone. Creating,
joining, leaving, closing and resetting need an account.

## How it works

- **Sign-up is verify-first.** `/signup` takes only an email (and optional name) and always answers
  "check your inbox", whether or not the address is registered; an existing address gets an
  "already registered" email instead. Opening the emailed link proves the mailbox and signs the
  person in; only then do they pick a passkey or password. Nothing exists to pre-register or
  inherit, and registered addresses cannot be discovered.
- **Sessions.** A random 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` and the
  `__Host-` prefix over https). Only its SHA-256 is stored. Lifetime is absolute (`SESSION_DAYS`,
  30) with an idle timeout (`SESSION_IDLE_DAYS`, 14); every sign-in and privilege change issues a
  new id, and a session id planted before sign-in is ended.
- **Passwords.** Salted scrypt. 10 to 128 characters, no composition rules, screened against
  breach data (see `security.md`). Unknown emails take the same time as wrong passwords and return
  the same message.
- **Two-step verification and passkeys.** See `security.md`. A passkey signs in on its own;
  password and email-link sign-in ask for a code when an authenticator app is set up.
- **One-time links.** Sign-up (24 h), email sign-in (15 min), reset (1 h) tokens are stored as
  digests, work once, and are replaced when a new one is requested. Following a reset link
  revokes every session and trusted browser.
- **OAuth.** Authorization-code flow with PKCE (S256) and a server-side `state` bound to the
  browser by an `HttpOnly` cookie (stops login-CSRF). Each provider has its own exact redirect
  URI and the state is tied to it, so a response meant for one provider is refused at another's
  callback (mix-up defence, RFC 9700). The OpenID providers (Google, Apple, Microsoft) also get a
  `nonce`, and the ID token is only believed after its RS256 signature (against the provider's
  published keys, refetched once on rotation), issuer, audience, expiry and nonce all check out;
  `alg: none`, HMAC-confusion and unknown-key tokens are rejected. Provider tokens are used once
  to read the profile and are never stored. Providers you have not configured are not offered.
- **Which emails are trusted.** Only a *provider-verified* email is ever matched to an existing
  account, so a stranger cannot take over an account by registering its address elsewhere. If the
  matching account was never email-verified, someone else may have registered the address first
  (pre-hijacking), so its unproven password and every existing session are removed before the
  provider identity is attached. Per provider: Google uses `email_verified`; Apple's
  `email_verified` (sent as the string `"true"`) and private-relay addresses are accepted;
  GitHub uses only a verified primary address; **Microsoft** is trusted for personal accounts, and
  for work or school accounts only when the `xms_edov` claim says the domain is verified. This
  closes "nOAuth", where an Entra tenant admin can put any address on an account they control.
  Accounts with two-step verification or a passkey are never linked to a provider by email match:
  sign in with your own method and link it from settings. A provider sign-in on an account with
  two-step verification still asks for the code. An account created with a provider can set a
  password later; a method can be unlinked only while another remains.
- **Same-origin writes.** The API rejects any unsafe request whose `Origin`/`Referer` is not
  `PUBLIC_BASE_URL` (or `EXTRA_ALLOWED_ORIGINS`), on top of `SameSite=Lax`.
- **Rate limits** (in process; the API is a single worker): 10 sign-ups per hour and 60 sign-in
  attempts per 15 minutes per address, 8 failed sign-ins per email per 15 minutes (Turnstile after
  3, when configured), 3 reset or sign-in emails per hour per email, a global per-address budget,
  hourly scan allowances (`SCAN_RATE_*`).
- **Privacy in Blocs.** Account ids never leave the server. In a Bloc, your own membership is
  marked `me`; everyone else appears only by an opaque membership id. The Bloc owner is exposed
  to the viewer as a boolean.
- **Who may close a Bloc.** Its creator or anyone still committed to it. The shared demo reset
  needs a signed-in user, or an administrator when `ADMIN_EMAILS` is set.
- **Account deletion** releases open commitments, replaces the account id in past Blocs with
  `deleted-account`, and removes the login, sessions, links and tokens.

The Next.js `proxy.ts` only does an optimistic redirect for `/account` and `/my-blocs` when no
session cookie exists. Real authorisation happens in the API on every request.

## Set it up

Email + password needs nothing. Migrate the database once: `make migrate` (adds
`0002_accounts`; fresh databases get it automatically).

Register the callback `<PUBLIC_BASE_URL>/api/auth/oauth/<provider>/callback` with each provider,
put the credentials in `.env` and restart `make api`. A provider with missing credentials is
simply not shown.

### Google

1. Google Cloud console → *APIs & Services* → *OAuth consent screen* (External; add yourself as a test user while testing).
2. *Credentials* → *Create credentials* → *OAuth client ID* → *Web application*; add the callback as an *Authorised redirect URI*.
3. `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

### Apple

Needs an Apple Developer Program membership and a **public https domain**; Apple rejects
`localhost`, so it cannot be tried locally.

1. *Certificates, Identifiers & Profiles* → *Identifiers* → register an **App ID** with *Sign in with Apple*, then a **Services ID** (this is `APPLE_CLIENT_ID`).
2. Configure the Services ID: *Sign in with Apple* → your domain and the callback as the return URL.
3. *Keys* → create a key with *Sign in with Apple*; download the `.p8` once. Its id is `APPLE_KEY_ID`, your Team ID (top right of the portal) is `APPLE_TEAM_ID`, and the file's text is `APPLE_PRIVATE_KEY` (newlines may be written `\n`).
4. Maxx signs Apple's short-lived client secret itself, so nothing expires every six months.

Apple returns the result as a cross-site form POST that carries no `SameSite=Lax` cookie. The
API therefore answers it with a tiny page that forwards the parameters to the normal callback from
this origin, where the state cookie is present and every check runs. Apple sends the person's name
only on first authorisation; Maxx stores it then.

### Microsoft

1. Microsoft Entra admin center → *App registrations* → *New registration*. Supported account types: personal + work/school for `common`, or personal only for `consumers`.
2. *Authentication* → *Web* → add the callback as a redirect URI. *Certificates & secrets* → new client secret.
3. `MICROSOFT_CLIENT_ID` (Application ID), `MICROSOFT_CLIENT_SECRET` (the secret *value*), `MICROSOFT_TENANT` (`common`, `consumers`, `organizations` or a tenant id).
4. Personal Microsoft accounts work immediately. For **work or school** accounts to sign in, add the optional ID-token claim `xms_edov` (add `email` and `xms_pdl`, rename `xms_pdl` to `xms_edov` in the manifest and set `acceptMappedClaims`); without it Maxx treats their email as unverified and refuses them, by design.

### GitHub

1. GitHub → *Settings* → *Developer settings* → *OAuth Apps* → *New OAuth App*; set the callback.
2. `GITHUB_CLIENT_ID` and a generated `GITHUB_CLIENT_SECRET`. Accounts without a verified primary email cannot sign in.

Open the app at exactly `PUBLIC_BASE_URL` (for local development `http://localhost:3001`, not
`127.0.0.1`); the state cookie, passkeys and the redirect must share one host.

### Local development without email

`EMAIL_MODE=log` prints every email (with its link) in the API log. To skip email entirely, create
a verified account directly: `make dev-account EMAIL=you@example.com PASSWORD='a long passphrase'`
(refused when `ENVIRONMENT=production`).

### Email

- `EMAIL_MODE=log` (default): messages, including their links, are printed in the API log. Use
  this locally: find the line `EMAIL (log mode) to=… subject=…`.
- `EMAIL_MODE=smtp`: set `SMTP_HOST`, `SMTP_PORT` (STARTTLS, default 587), `SMTP_USER`,
  `SMTP_PASSWORD`, `EMAIL_FROM`. Delivery failures are logged without revealing whether an
  account exists. Hosts that block outbound mail ports (Render's free plan blocks 25, 465 and
  587) can use a relay that listens on 2525; the hosted demo sends through Brevo on 2525.
- Every message goes out as plain text with a matching HTML part rendered from one layout
  (`services/api/maxx/auth/mail_layout.py`); anything a person typed is escaped.

### Administrators

`ADMIN_EMAILS=you@example.com` limits the shared demo reset (`/demo/reset`, used by `/judge`
and `evals/run_negotiations.py --email … --password …`) to those verified addresses.

## Verification

```bash
uv --directory services/api run --locked pytest tests/test_auth.py tests/test_oauth.py tests/test_mfa.py tests/test_passkeys.py -q
npm run test --workspace @maxx/web                                     # redirect safety, password guidance, WebAuthn glue
make audit                                                              # known-vulnerability scan (Python and npm)
```

The OAuth tests run all four providers against a simulator that signs real RS256 ID tokens and
serves a JWKS (forged, expired, wrong-audience, wrong-nonce and wrong-issuer tokens are rejected;
removing the signature or nonce check makes tests fail). The browser journeys (sign up, verify by
emailed link, join, negotiate, My Blocs, reset, change password, delete, and Google, Apple
(form-post relay) and Microsoft sign-in with linking) were run against the real Next.js → FastAPI →
Postgres stack using a local signing provider. On the hosted demo (30 October 2026), sign-up emails
were accepted by a real SMTP relay and session cookies work over HTTPS. **Not verified:** the
real Google, Apple, Microsoft and GitHub consoles; each needs your own credentials.

## Limits to know

- Rate limits and the lockout are per process and per address/email; behind a shared proxy set
  `TRUST_PROXY_HEADERS` only while the API is private. Eight wrong passwords lock *that email*
  for 15 minutes, which also lets someone else briefly lock a known address out.
- No multi-factor sign-in, no passkeys, no email change (create a new account instead), and
  commitments remain simulated: nothing here moves money.
