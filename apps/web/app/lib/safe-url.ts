/** Links from provider data (price sources) open only when they are plain http(s) URLs. */
export function safeHref(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch { return null; }
}
export function hostOf(value: string): string {
  try { return new URL(value).hostname; } catch { return "source"; }
}

/** Redirect targets from the API are our own paths or an https provider. Anything else is dropped. */
export function safeLocation(location: string): string | null {
  if (location.startsWith("/") && !location.startsWith("//") && !location.includes("\\")) return location;
  try { return new URL(location).protocol === "https:" || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//.test(location) ? location : null; } catch { return null; }
}
