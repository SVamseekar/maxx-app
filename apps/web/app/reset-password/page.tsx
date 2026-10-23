"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AuthLink, AuthShell, FormMessage, PasswordField, SubmitButton } from "../components/auth-ui";
import { request } from "../lib/client";
import { passwordChecks } from "../lib/auth-helpers";
import { useQuery } from "../lib/use-query";

export default function ResetPassword() {
  const query = useQuery();
  const token = query?.get("token") ?? "";
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!passwordChecks(password).every(check => check.ok)) { setError("Choose a longer, less guessable password."); return; }
    setBusy(true); setError("");
    try { await request("/api/auth/password/reset", { body: { token, password } }); router.replace("/login?reset=1"); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not reset your password."); setBusy(false); }
  }
  return <AuthShell title="Choose a new password." description="You will be signed out everywhere and asked to sign in with the new password." footer={<AuthLink href="/forgot-password">Request a new link</AuthLink>}>
    {query && !token ? <FormMessage>This reset link is incomplete. Open the link from your email, or request a new one.</FormMessage> : <form onSubmit={submit} aria-busy={busy}>
      {error && <FormMessage>{error}</FormMessage>}
      <PasswordField label="New password" value={password} onChange={setPassword} meter autoComplete="new-password" />
      <SubmitButton busy={busy}>Update password</SubmitButton>
    </form>}
  </AuthShell>;
}
