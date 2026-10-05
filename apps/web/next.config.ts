import { loadEnvConfig } from "@next/env";
import path from "node:path";
import type { NextConfig } from "next";

// One root .env for the monorepo; API_BASE_URL stays server-only.
loadEnvConfig(path.resolve(process.cwd(), "../.."));
const config: NextConfig = { poweredByHeader: false };
export default config;
