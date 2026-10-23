import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  // Public explanatory pages are indexable. Anything personal or transactional is not.
  return { rules: [{ userAgent: "*", allow: ["/", "/legal"], disallow: ["/api/", "/account", "/my-blocs", "/receipts", "/orders", "/sell", "/admin", "/login", "/signup", "/reset-password", "/verify-email", "/signin-link", "/complete-signup"] }], sitemap: `${process.env.PUBLIC_BASE_URL ?? "http://localhost:3001"}/sitemap.xml` };
}
