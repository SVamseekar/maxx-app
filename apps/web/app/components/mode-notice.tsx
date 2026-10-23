"use client";
import { FlaskConical } from "lucide-react";
import { moneyLabel, useMoneyConfig } from "../lib/money";

/** Says plainly whether any real money can move on this server. */
export function ModeNotice() {
  const config = useMoneyConfig();
  return <p className="mode-notice"><FlaskConical size={13} aria-hidden="true" /> {moneyLabel(config)}</p>;
}
