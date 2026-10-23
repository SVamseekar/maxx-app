import { loadEnvConfig } from "@next/env";
import path from "node:path";
import type { NextConfig } from "next";

// One root .env for the monorepo; API_BASE_URL stays server-only.
loadEnvConfig(path.resolve(process.cwd(), "../.."));
const secure = (process.env.PUBLIC_BASE_URL ?? "").startsWith("https://");
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Passkeys are allowed for our own origin only; hardware and location features stay off.
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), publickey-credentials-get=(self), publickey-credentials-create=(self)" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  ...(secure ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }] : []),
];
const config: NextConfig = {
  distDir: process.env.MAXX_BUILD_DIR || ".next",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};
export default config;
