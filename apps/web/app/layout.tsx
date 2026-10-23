import type { Metadata } from "next";
import { headers } from "next/headers";
import { connection } from "next/server";
import "./globals.css";
import "./motion.css";
import "@fontsource-variable/manrope";
import { AppHeader, MotionProvider } from "./components/ui";
import { ConfirmProvider } from "./components/confirm-provider";
import { AuthProvider } from "./components/auth";
import { ReauthProvider } from "./components/reauth";
import VerifyBanner from "./components/verify-banner";
import SiteFooter from "./components/site-footer";
import "./auth.css";
import "./money.css";
import "./site.css";
import "./design.css";
import "./interactions.css";
import "./editorial-v2.css";
import "./premium.css";
import "./mobile.css";
export const metadata: Metadata = {
  title: "Maxx · Your smartest move", description: "Check a shopping screenshot, compare prices and get your Money Score.",
  openGraph: { title: "Maxx · Your smartest move", description: "Check a shopping screenshot, compare prices and get your Money Score.", type: "website", siteName: "Maxx" },
  twitter: { card: "summary", title: "Maxx · Your smartest move", description: "Check a shopping screenshot, compare prices and get your Money Score." },
};
const THEME_SCRIPT = `(function(){try{var r=document.documentElement;r.dataset.theme=localStorage.getItem('maxx-theme')==='light'?'light':'dark';r.dataset.motion=localStorage.getItem('maxx-motion')==='paused'||window.matchMedia('(prefers-reduced-motion: reduce)').matches?'reduced':'full'}catch(e){}})();`;
export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // The Content-Security-Policy carries a per-request nonce (see proxy.ts), so pages render per request.
  await connection();
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return <html lang="en" suppressHydrationWarning><head><script nonce={nonce} suppressHydrationWarning dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} /></head><body><MotionProvider><AuthProvider><ReauthProvider><ConfirmProvider><a className="skip-link" href="#main-content">Skip to content</a><AppHeader /><VerifyBanner />{children}<SiteFooter /></ConfirmProvider></ReauthProvider></AuthProvider></MotionProvider></body></html>;
}
