import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Maxx · Your smartest move", description: "Check a shopping screenshot, compare prices and get your Money Score.",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
