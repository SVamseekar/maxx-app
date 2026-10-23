"use client";
import { useEffect, useState } from "react";
import { request } from "../lib/client";

export type Provider = { id: string; name: string; enabled: boolean };
export type AuthConfig = { oauth: Provider[]; captcha: { provider: string; site_key: string } | null; email_mode: "log" | "smtp" };

let cached: Promise<AuthConfig> | null = null;
/** Public sign-in options (providers, human check, mail mode). Fetched once per page load. */
export function useAuthConfig(): AuthConfig | null {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  useEffect(() => {
    cached ??= request<AuthConfig>("/api/auth/providers").catch(() => { cached = null; return { oauth: [], captcha: null, email_mode: "smtp" } as AuthConfig; });
    let live = true;
    void cached.then(value => { if (live) setConfig(value); });
    return () => { live = false; };
  }, []);
  return config;
}
