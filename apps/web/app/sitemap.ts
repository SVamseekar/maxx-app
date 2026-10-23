import type { MetadataRoute } from "next";
import { DOCS } from "./legal/docs";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = (process.env.PUBLIC_BASE_URL ?? "http://localhost:3001").replace(/\/$/, "");
  const pages = ["", "/blocs", "/scan", "/how-it-works", "/features", "/trust", "/pricing", "/faq", "/about", "/contact", "/for-sellers", "/legal"];
  return [...pages.map(path => ({ url: base + path })), ...DOCS.map(doc => ({ url: `${base}/legal/${doc.slug}` }))];
}
