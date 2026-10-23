/** Pure helpers for money display. No imports, so they can be tested directly. */

/** Label for the header chip and the room banner, so nobody mistakes test money for real money. */
export function moneyLabel(config: { enabled: boolean; simulated: boolean } | null): string {
  if (!config || !config.enabled) return "No real payments";
  return config.simulated ? "Simulated PayPal · no real money" : "PayPal sandbox · test money";
}

/** Shorten a PayPal or chain id for display while keeping both ends recognisable. */
export const shortId = (value: string | null) => !value ? "—" : value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
