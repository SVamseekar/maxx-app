"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Fingerprint, KeyRound, Loader2, XCircle } from "lucide-react";
import { AuthLink, AuthShell, FormMessage, PasswordField, SubmitButton } from "../components/auth-ui";
import { useAuth } from "../components/auth";
import { useSecure } from "../components/reauth";
import { ApiError, request } from "../lib/client";
import { passkeyErrorMessage, passkeysSupported, createPasskey, type CreationJSON } from "../lib/webauthn";
import { passwordChecks, safeNext, type AccountUser } from "../lib/auth-helpers";
import { useQuery } from "../lib/use-query";

type State = "working" | "choose" | "failed";

/** The emailed link lands here: it confirms the mailbox, signs in, then lets the person choose how. */
export default function CompleteSignup() {
  const query = useQuery();
  const router = useRouter();
  const { setUser, user } = useAuth();
  const secure = useSecure();
  const attempted = useRef(false);
  const [state, setState] = useState<State>("working");
  const [message, setMessage] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [canPasskey, setCanPasskey] = useState(false);
  const target = (() => { try { return safeNext(sessionStorage.getItem("maxx-next"), "/blocs"); } catch { return "/blocs"; } })();

  useEffect(() => {
    if (!query || attempted.current) return;
    attempted.current = true;
    setCanPasskey(passkeysSupported());
    const token = query.get("token");
    if (!token) { setState("failed"); setMessage("This link is incomplete."); return; }
    request<{ user: AccountUser }>("/api/auth/signup/verify", { body: { token } })
      .then(result => { setUser(result.user); setState("choose"); })
      .catch(cause => { setState("failed"); setMessage(cause instanceof Error ? cause.message : "Could not confirm your email."); });
  }, [query, setUser]);

  const finish = () => { router.replace(target); router.refresh(); };
  async function addPasskey() {
    setBusy(true); setError("");
    try {
      await secure(async () => {
        const started = await request<{ options: CreationJSON; challenge_id: string }>("/api/auth/passkeys/register/options", { body: {} });
        const credential = await createPasskey(started.options);
        await request("/api/auth/passkeys/register/verify", { body: { challenge_id: started.challenge_id, credential, name: "This device" } });
      });
      finish();
    } catch (cause) {
      const text = cause instanceof ApiError ? (cause.code === "reauth_cancelled" ? "" : cause.message) : passkeyErrorMessage(cause);
      if (text) setError(text);
      setBusy(false);
    }
  }
  async function savePassword(event: React.FormEvent) {
    event.preventDefault();
    if (!passwordChecks(password, user?.email).every(check => check.ok)) { setError("Choose a longer, less guessable password."); return; }
    setBusy(true); setError("");
    try { await secure(() => request("/api/auth/password/change", { body: { new_password: password } })); finish(); }
    catch (cause) { if (!(cause instanceof ApiError && cause.code === "reauth_cancelled")) setError(cause instanceof Error ? cause.message : "Could not save your password."); setBusy(false); }
  }

  if (state === "working") return <AuthShell title="Confirming your email…"><div className="auth-success" role="status"><Loader2 className="spin" size={26} aria-hidden="true" /></div></AuthShell>;
  if (state === "failed") return <AuthShell title="That link did not work." footer={<AuthLink href="/signup">Start again</AuthLink>}><div className="auth-success"><XCircle size={26} aria-hidden="true" /><p>{message} Links work once and expire after 24 hours.</p></div></AuthShell>;
  return <AuthShell title="You’re in. Secure your account." description="Choose how you will sign back in. You can add more later in your account.">
    <div className="auth-success inline"><CheckCircle2 size={22} aria-hidden="true" /><p>{user?.email} is confirmed.</p></div>
    {error && <FormMessage>{error}</FormMessage>}
    {canPasskey && <div className="choice"><div><h2><Fingerprint size={18} aria-hidden="true" /> Use a passkey</h2><p>Sign in with your fingerprint, face or screen lock. Nothing to remember and it cannot be phished.</p></div><button type="button" className="button primary" disabled={busy} onClick={() => void addPasskey()}>Create a passkey</button></div>}
    <form className="choice stacked" onSubmit={savePassword}><div><h2><KeyRound size={18} aria-hidden="true" /> {canPasskey ? "Or set a password" : "Set a password"}</h2></div><PasswordField label="New password" value={password} onChange={setPassword} meter autoComplete="new-password" email={user?.email} /><SubmitButton busy={busy}>Save password</SubmitButton></form>
    <div className="auth-row"><button type="button" className="quiet-button" onClick={finish}>Skip for now</button><span className="small muted">You can always sign in with an emailed link.</span></div>
  </AuthShell>;
}
