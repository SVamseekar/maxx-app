"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Store } from "lucide-react";
import { AppFooter, Badge, PageIntro, Working } from "../components/ui";
import { useAuth } from "../components/auth";
import { loginPath } from "../lib/auth-helpers";
import SellerConsole from "../components/seller-console";

export default function Sell() {
  const { user, status } = useAuth();
  const router = useRouter();
  useEffect(() => { if (status === "ready" && !user) router.replace(loginPath("/sell")); }, [status, user, router]);
  return <main id="main-content">
    <PageIntro title="Sell to a group." description="Verified sellers get demand that is already committed. Set a floor you will never go below, and an agent negotiates for you within it."><Badge><Store size={13} /> Seller console</Badge></PageIntro>
    {!user ? <div className="loading-surface"><Working label="Checking your account" /></div> : <SellerConsole />}
    <AppFooter />
  </main>;
}
