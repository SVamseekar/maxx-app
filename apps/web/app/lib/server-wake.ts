/**
 * Free hosting stops the API after 15 idle minutes and starts it again on the next request, which
 * takes about a minute. Pages wake it as early as possible and say so while it starts.
 */
export const WAKE_BANNER_DELAY_MS = 2_000;
export const WAKE_POLL_MS = 3_000;
export const WAKE_GIVE_UP_MS = 180_000;
/** Page requests send at most one wake request per instance in this window. */
export const WAKE_GAP_MS = 60_000;

export type WakeState = "checking" | "waking" | "ready" | "stuck";

/** What the page shows after a health check that took `elapsedMs` since the page began checking. */
export function nextWakeState(healthy: boolean, elapsedMs: number): WakeState {
  if (healthy) return "ready";
  if (elapsedMs >= WAKE_GIVE_UP_MS) return "stuck";
  return elapsedMs >= WAKE_BANNER_DELAY_MS ? "waking" : "checking";
}

/** Whether a page request should send a wake request, given when the last one went out. */
export function wakeDue(now: number, lastWake: number): boolean {
  return now - lastWake >= WAKE_GAP_MS;
}
