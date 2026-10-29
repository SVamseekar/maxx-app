/**
 * The browser's address as the platform proxy saw it. That proxy appends the address it observed
 * last in x-forwarded-for; anything to its left was written by the browser, so only the last entry
 * is trusted.
 */
export function clientAddress(headers: Headers): string | undefined {
  const forwarded = headers.get("x-forwarded-for")?.split(",").pop()?.trim();
  return forwarded || headers.get("x-real-ip")?.trim() || undefined;
}

/**
 * The headers that tell the API who the browser is. Through a public URL (Render) the API's own
 * front end appends this web service's address to x-forwarded-for, so the address is also named in
 * x-maxx-client-ip, which the API trusts only with the shared secret.
 */
export function addressHeaders(headers: Headers, secret: string | undefined): Record<string, string> {
  const address = clientAddress(headers);
  if (!address) return {};
  if (!secret) return { "x-forwarded-for": address };
  return { "x-forwarded-for": address, "x-maxx-client-ip": address, "x-maxx-proxy-secret": secret };
}
