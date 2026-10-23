"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { AuthShell } from "../components/auth-ui";
import { useAuth } from "../components/auth";
import { request } from "../lib/client";
import { useQuery } from "../lib/use-query";

export default function VerifyEmail() {
  const query = useQuery();
  const { refresh } = useAuth();
  const [state, setState] = useState<"working" | "done" | "failed">("working");
  const [message, setMessage] = useState("");
  const attempted = useRef(false);
  useEffect(() => {
    if (!query || attempted.current) return;
    attempted.current = true;
    const token = query.get("token");
    if (!token) { setState("failed"); setMessage("This confirmation link is incomplete."); return; }
    request("/api/auth/email/verify", { body: { token } }).then(() => { setState("done"); void refresh(); })
      .catch(cause => { setState("failed"); setMessage(cause instanceof Error ? cause.message : "Could not confirm your email."); });
  }, [query, refresh]);
  return <AuthShell title={state === "done" ? "Email confirmed." : state === "failed" ? "That link did not work." : "Confirming your email…"}>
    <div className="auth-success" role="status" aria-live="polite">
      {state === "working" && <Loader2 className="spin" size={26} aria-hidden="true" />}
      {state === "done" && <><CheckCircle2 size={26} aria-hidden="true" /><p>Thanks. Your address is verified and your account is fully set up.</p><Link className="button primary" href="/blocs">Browse Blocs</Link></>}
      {state === "failed" && <><XCircle size={26} aria-hidden="true" /><p>{message} Links work once and expire after 48 hours.</p><Link className="button" href="/account">Resend from your account</Link></>}
    </div>
  </AuthShell>;
}
