/**
 * The browser's address as the platform proxy saw it. That proxy appends the address it observed
 * last in x-forwarded-for; anything to its left was written by the browser, so only the last entry
 * is trusted.
 */
export function clientAddress(headers: Headers): string | undefined {
  const forwarded = headers.get("x-forwarded-for")?.split(",").pop()?.trim();
  return forwarded || headers.get("x-real-ip")?.trim() || undefined;
}
