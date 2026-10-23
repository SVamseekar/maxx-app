"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, CheckCheck, Mail } from "lucide-react";
import { AppFooter, ErrorNotice, PageIntro, Working } from "../components/ui";
import { FormMessage } from "../components/auth-ui";
import { useAuth } from "../components/auth";
import { request } from "../lib/client";
import { loginPath, relativeTime } from "../lib/auth-helpers";
import { useAction } from "../lib/use-action";
import { KIND_LABEL, safeLink, type Inbox, type Preferences } from "../lib/notifications";

export default function Notifications() {
  const { user, status } = useAuth();
  const router = useRouter();
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [error, setError] = useState("");
  const save = useAction();
  useEffect(() => { if (status === "ready" && !user) router.replace(loginPath("/notifications")); }, [status, user, router]);
  const load = useCallback(async () => {
    try {
      const [items, settings] = await Promise.all([request<Inbox>("/api/notifications?limit=100"), request<Preferences>("/api/notifications/preferences")]);
      setInbox(items); setPrefs(settings); setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Cannot load your notifications."); }
  }, []);
  useEffect(() => { if (user) void load(); }, [user?.id, load]); // eslint-disable-line react-hooks/exhaustive-deps
  async function markAll() { await request("/api/notifications/read", { body: {} }); await load(); }
  async function open(id: string) { await request("/api/notifications/read", { body: { ids: [id] } }).catch(() => undefined); }
  return <main id="main-content" className="notifications-page">
    <PageIntro title="Notifications." description="Everything that needs your attention about your orders, payments and seller account. Important ones are emailed too.">
      {inbox && inbox.unread > 0 && <button type="button" className="button" onClick={() => void markAll()}><CheckCheck size={15} aria-hidden="true" /> Mark all as read</button>}
    </PageIntro>
    {error && <ErrorNotice message={error} retry={() => void load()} />}
    {!inbox && !error && <div className="loading-surface"><Working label="Loading notifications" /></div>}
    {inbox && inbox.items.length === 0 && <div className="empty-state"><Bell size={28} aria-hidden="true" /><h2>Nothing yet.</h2><p>When you win a Bloc, an order ships, a payout arrives or someone needs a reply, it appears here.</p></div>}
    {inbox && inbox.items.length > 0 && <ol className="notification-list" aria-label="Notifications">{inbox.items.map(item => {
      const link = safeLink(item.link);
      const body = <><span className="notification-kind">{KIND_LABEL[item.kind] ?? "Update"}</span><strong>{item.title}</strong>{item.body && <p>{item.body}</p>}<time dateTime={new Date(item.created_at * 1000).toISOString()}>{relativeTime(item.created_at)}</time></>;
      return <li key={item.id} className={item.read ? "notification" : "notification is-unread"}>{!item.read && <span className="unread-dot" aria-label="Unread" />}{link ? <Link href={link} onClick={() => void open(item.id)}>{body}</Link> : <div>{body}</div>}</li>;
    })}</ol>}
    {prefs && <section className="seller-card notification-prefs" aria-labelledby="prefs-h">
      <h2 id="prefs-h"><Mail size={18} aria-hidden="true" /> Email me about</h2>
      <p className="muted small">You always get emails about money, deadlines, problem reports and decisions on your account, because missing them can cost you. These updates are optional:</p>
      {save.message && <FormMessage tone={save.message.tone}>{save.message.text}</FormMessage>}
      <ul className="pref-list">{Object.entries(prefs.email).map(([kind, on]) => <li key={kind}><label><input type="checkbox" checked={on} disabled={save.busy} onChange={event => void save.run(async () => { setPrefs(await request<Preferences>("/api/notifications/preferences", { body: { email: { [kind]: event.target.checked } } })); return "Saved."; })} /> {KIND_LABEL[kind] ?? kind}</label></li>)}</ul>
    </section>}
    <AppFooter />
  </main>;
}
