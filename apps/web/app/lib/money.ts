"use client";
import { useEffect, useState } from "react";
import { useServerReady } from "../components/server-wake";
import { request } from "./client";

export type MoneyConfig = {
  mode: "off" | "simulator" | "sandbox";
  enabled: boolean;
  simulated: boolean;
  currency: string;
  client_id: string;
  sdk_url: string;
  platform_fee_percent: string;
  negative_testing: boolean;
  crypto: { enabled: boolean; asset: string; chain: string; address: string; simulated: boolean };
};

export type Payouts = { seller: string; method: string; units: number; gross: string; fee: string; net: string; status: string; simulated: boolean };
export type Ledger = {
  currency: string; holds: number; held_total: string; captured_count: number; captured_total: string;
  voided_count: number; voided_total: string; failed_count: number; platform_fee: string; seller_payouts: string; held_for_shipping: string;
  payouts: Payouts[]; reconciled: boolean; settlement: "WAITING" | "NOT_NEEDED" | "RUNNING" | "PARTIAL" | "DONE"; simulated: boolean;
};

export type Receipt = {
  id: string; kind: "hold" | "checkout"; bloc_id: string | null; title: string; method: "paypal" | "pyusd"; status: string;
  held: string; paid: string | null; saved: string | null; currency: string; simulated: boolean; error: string; at: number;
  paypal: { order: string; authorization: string | null; capture: string | null; pyusd_tx: string | null };
};

export type Offer = {
  title: string; merchant: string; url: string; qty: number; unit_price: string; shipping: string; total: string; currency: string;
  evidence: string; saves: string | null; expires: number; proposal_token: string;
  plan: { tool: string; when: string; amount?: string }[]; tools: string[];
};

let cached: Promise<MoneyConfig> | null = null;
/** What the server can do with money. Fetched once per page load. */
export function loadMoneyConfig(): Promise<MoneyConfig> {
  cached ??= request<MoneyConfig>("/api/money/config").catch(error => { cached = null; throw error; });
  return cached;
}

const OFF: MoneyConfig = { mode: "off", enabled: false, simulated: false, currency: "USD", client_id: "", sdk_url: "", platform_fee_percent: "5", negative_testing: false, crypto: { enabled: false, asset: "PYUSD", chain: "", address: "", simulated: false } };

/** `null` while loading, then the configuration (the "off" shape if the service cannot be reached). */
export function useMoneyConfig(): MoneyConfig | null {
  const [config, setConfig] = useState<MoneyConfig | null>(null);
  const ready = useServerReady();
  useEffect(() => { if (!ready) return; let live = true; loadMoneyConfig().then(value => { if (live) setConfig(value); }, () => { if (live) setConfig(OFF); }); return () => { live = false; }; }, [ready]);
  return config;
}

export { moneyLabel, shortId } from "./money-format";
