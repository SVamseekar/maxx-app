"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, XCircle } from "lucide-react";
import { AuthLink, AuthShell } from "../components/auth-ui";
import { useAuth } from "../components/auth";
import MfaStep from "../components/mfa-step";
import { request } from "../lib/client";
import type { AccountUser } from "../lib/auth-helpers";
import { useQuery } from "../lib/use-query";

/** An emailed sign-in link. If two-step verification is on, it asks for the code before signing in. */
export default function SigninLink() {
  const query = useQuery();
  const router = useRouter();
  const { setUser } = useAuth();
  const attempted = useRef(false);
  const [state, setState] = useState<"working" | "mfa" | "failed">("working");
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("");
  const done = (user: AccountUser) => { setUser(user); router.replace("/blocs"); router.refresh(); };
  useEffect(() => {
    if (!query || attempted.current) return;
    attempted.current = true;
    const link = query.get("token");
    if (!link) { setState("failed"); setMessage("This link is incomplete."); return; }
    request<{ user?: AccountUser; mfa_required?: boolean; mfa_token?: string }>("/api/auth/login/link/verify", { body: { token: link } })
      .then(result => { if (result.mfa_required && result.mfa_token) { setToken(result.mfa_token); setState("mfa"); } else if (result.user) done(result.user); })
      .catch(cause => { setState("failed"); setMessage(cause instanceof Error ? cause.message : "Could not sign you in."); });
  }, [query]); // eslint-disable-line react-hooks/exhaustive-deps
  if (state === "mfa") return <AuthShell title="Check it’s you." description="Your account uses two-step verification."><MfaStep token={token} onDone={done} onCancel={() => router.replace("/login")} /></AuthShell>;
  if (state === "failed") return <AuthShell title="That link did not work." footer={<AuthLink href="/login">Back to sign in</AuthLink>}><div className="auth-success"><XCircle size={26} aria-hidden="true" /><p>{message}</p></div></AuthShell>;
  return <AuthShell title="Signing you in…"><div className="auth-success" role="status"><Loader2 className="spin" size={26} aria-hidden="true" /></div></AuthShell>;
}
