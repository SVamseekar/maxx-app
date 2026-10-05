import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Maxx · Foundation", description: "Maxx local application foundation health check",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
