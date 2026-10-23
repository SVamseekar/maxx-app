/** Pure account helpers shared by the sign-in screens. No React, no network. */

export type AccountUser = {
  id: string; email: string; email_verified: boolean; display_name: string; avatar_url: string | null;
  has_password: boolean; providers: string[]; is_admin: boolean; created_at: number;
  totp_enabled: boolean; passkeys: number; needs_credential: boolean;
};

/** Only same-site relative paths are followed after sign-in; anything else becomes the fallback. */
export function safeNext(value: string | null | undefined, fallback = "/"): string {
  if (!value || value.length > 300 || !value.startsWith("/")) return fallback;
  if (value.startsWith("//") || value.includes("\\") || [...value].some(char => char.charCodeAt(0) < 32)) return fallback;
  return value;
}

export const loginPath = (next: string) => `/login?next=${encodeURIComponent(safeNext(next))}`;

const OAUTH_ERRORS: Record<string, string> = {
  oauth_unavailable: "That sign-in method is not set up on this server yet. Use your email instead.",
  oauth_denied: "Sign-in was cancelled. You can try again or use your email.",
  oauth_state: "That sign-in link expired or came from a different browser. Please start again.",
  oauth_failed: "The provider could not complete sign-in. Please try again.",
  oauth_no_email: "The provider did not share a verified email address, so we could not create your account. Use your email instead.",
  oauth_taken: "That account is already linked to a different Maxx account.",
  signin_required: "Sign in first, then link another method.",
  reauth_required: "Confirm it's you first, then link the provider again.",
  oauth_link_required: "An account with this email already exists and is protected by two-step verification or a passkey. Sign in with your own method first, then link this provider in your account settings.",
};
export const oauthErrorMessage = (code: string | null | undefined): string | null => (code ? OAUTH_ERRORS[code] ?? "Something went wrong signing in. Please try again." : null);

export type PasswordCheck = { id: string; label: string; ok: boolean };
/** Live guidance only. The server is the authority on what is accepted. */
export function passwordChecks(password: string, email = ""): PasswordCheck[] {
  const local = email.split("@")[0]?.toLowerCase() ?? "";
  return [
    { id: "length", label: "At least 10 characters", ok: password.length >= 10 },
    { id: "variety", label: "Not a single repeated character", ok: new Set(password).size >= 4 },
    { id: "email", label: "Different from your email name", ok: !(local.length >= 4 && password.toLowerCase() === local) },
  ];
}

/** 0 to 4. Length counts most; variety and a passphrase-style spread add a little. */
export function passwordStrength(password: string): number {
  if (password.length < 10) return password.length ? 1 : 0;
  let score = 2;
  if (password.length >= 14) score++;
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(rx => rx.test(password)).length;
  if (classes >= 3 || password.includes(" ") || password.length >= 20) score++;
  return Math.min(4, score);
}
export const STRENGTH_LABELS = ["", "Too short", "Okay", "Good", "Strong"];

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts.at(-1)![0] : "")).toUpperCase();
}

/** Friendly "Chrome on macOS" from a User-Agent. Best effort; unknown agents stay generic. */
export function describeAgent(agent: string): string {
  const browser = /Edg\//.test(agent) ? "Edge" : /OPR\/|Opera/.test(agent) ? "Opera" : /Firefox\//.test(agent) ? "Firefox" : /Chrome\//.test(agent) ? "Chrome" : /Safari\//.test(agent) ? "Safari" : "";
  const system = /iPhone|iPad/.test(agent) ? "iOS" : /Android/.test(agent) ? "Android" : /Mac OS X/.test(agent) ? "macOS" : /Windows/.test(agent) ? "Windows" : /Linux/.test(agent) ? "Linux" : "";
  if (browser && system) return `${browser} on ${system}`;
  return browser || system || "Unknown device";
}

export function relativeTime(seconds: number, now = Date.now() / 1000): string {
  const delta = Math.max(0, now - seconds);
  if (delta < 60) return "just now";
  if (delta < 3600) return `${Math.floor(delta / 60)} min ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)} h ago`;
  return `${Math.floor(delta / 86400)} d ago`;
}
