import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";
import { wakeDue } from "./app/lib/server-wake";

let lastWake = 0;

/**
 * Starts a sleeping API on the first page request, before the page reaches the browser. The request
 * only has to arrive for the host to start the instance; the page's banner reports when it is ready.
 */
function wakeApi(event: NextFetchEvent) {
  const now = Date.now();
  if (!wakeDue(now, lastWake)) return;
  lastWake = now;
  const base = (process.env.API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  event.waitUntil(fetch(`${base}/health/ready`, { cache: "no-store", signal: AbortSignal.timeout(5000) }).then(() => undefined, () => undefined));
}

const PROTECTED = /^\/(account|my-blocs|receipts|sell|orders|admin)(\/|$)/;

/** Content-Security-Policy with a fresh nonce per request. Only our own scripts may run. */
function policy(nonce: string): string {
  const dev = process.env.NODE_ENV === "development";
  const turnstile = process.env.TURNSTILE_SITE_KEY ? " https://challenges.cloudflare.com" : "";
  // The PayPal JS SDK (sandbox only; live payments are not supported) loads a script, opens its
  // approval window in a frame and calls its own API. Nothing else is allowed.
  const paypal = process.env.PAYPAL_MODE === "sandbox" ? "https://www.sandbox.paypal.com https://api-m.sandbox.paypal.com" : "";
  return [
    "default-src 'self'",
    // 'strict-dynamic' lets nonce-approved scripts load their own chunks; host lists are ignored by modern browsers.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${paypal ? " https://www.sandbox.paypal.com" : ""}${dev ? " 'unsafe-eval'" : ""}`,
    // Development injects <style> tags through its dev server, which cannot carry a nonce.
    dev ? "style-src 'self' 'unsafe-inline'" : `style-src 'self' 'nonce-${nonce}'`,
    // React renders style="" attributes (layout, animation); script injection is the real risk, not inline styles.
    "style-src-attr 'unsafe-inline'",
    `img-src 'self' data: blob: https://*.googleusercontent.com https://avatars.githubusercontent.com${paypal ? " https://www.sandbox.paypal.com" : ""}`,
    "font-src 'self'",
    `connect-src 'self'${turnstile}${paypal ? " " + paypal : ""}`,
    `frame-src ${[turnstile.trim(), paypal && "https://www.sandbox.paypal.com"].filter(Boolean).join(" ") || "'none'"}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "manifest-src 'self'",
    ...(dev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

/**
 * 1. Optimistic gate: a missing session cookie sends the visitor to sign in before the page
 *    renders. The cookie is validated by the API on every real request, so a stale or forged cookie
 *    reaches the page but never any data.
 * 2. A strict Content-Security-Policy on every page.
 * 3. A wake request for the API, sent in the background.
 */
export function proxy(request: NextRequest, event: NextFetchEvent) {
  wakeApi(event);
  const { pathname, search } = request.nextUrl;
  const signedIn = request.cookies.has("maxx_session") || request.cookies.has("__Host-maxx_session");
  if (PROTECTED.test(pathname) && !signedIn) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  const nonce = btoa(crypto.randomUUID());
  const csp = policy(nonce);
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("content-security-policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("content-security-policy", csp);
  return response;
}

export const config = {
  matcher: [{
    source: "/((?!api|_next/static|_next/image|favicon.ico|artwork|samples|\\.well-known|robots.txt|sitemap.xml).*)",
    missing: [{ type: "header", key: "next-router-prefetch" }, { type: "header", key: "purpose", value: "prefetch" }],
  }],
};
