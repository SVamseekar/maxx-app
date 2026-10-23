"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Bell } from "lucide-react";
import { useAuth } from "./auth";
import { request } from "../lib/client";

/** The unread count beside the account menu. Polls gently and refreshes when the tab returns. */
export default function NotificationBell() {
  const { user } = useAuth();
  const pathname = usePathname();
  const [unread, setUnread] = useState(0);
  const load = useCallback(async () => {
    try { setUnread((await request<{ unread: number }>("/api/notifications/unread")).unread); } catch { /* the bell is optional */ }
  }, []);
  useEffect(() => {
    if (!user) return;
    void load();
    const timer = setInterval(() => { if (document.visibilityState === "visible") void load(); }, 60000);
    const back = () => { if (document.visibilityState === "visible") void load(); };
    document.addEventListener("visibilitychange", back);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", back); };
  }, [user?.id, load, pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!user) return null;
  const label = unread ? `Notifications, ${unread} unread` : "Notifications";
  return <Link href="/notifications" className="icon-button notification-bell" aria-label={label} title={label}>
    <Bell size={18} aria-hidden="true" />{unread > 0 && <span className="bell-count" aria-hidden="true">{unread > 99 ? "99+" : unread}</span>}
  </Link>;
}
