/**
 * Who Maxx is, in one place. Everything a legal page or the footer says about the operator comes
 * from here so it can be set at deploy time. The defaults are deliberately obvious placeholders:
 * the prototype has no company behind it, and we do not invent one.
 */
export const SITE = {
  name: "Maxx",
  tagline: "Buy together. Pay less.",
  updated: "13 October 2026",
  version: "2026-10-13",
  entity: process.env.LEGAL_ENTITY ?? "Maxx (prototype: no legal entity has been formed yet)",
  address: process.env.LEGAL_ADDRESS ?? "Postal address to be published before launch",
  jurisdiction: process.env.LEGAL_JURISDICTION ?? "To be set when the operating entity is formed",
  email: process.env.CONTACT_EMAIL ?? "hello@maxx.example",
  legalEmail: process.env.LEGAL_EMAIL ?? "legal@maxx.example",
  privacyEmail: process.env.PRIVACY_EMAIL ?? "privacy@maxx.example",
  securityEmail: process.env.SECURITY_EMAIL ?? "security@maxx.example",
  supportEmail: process.env.SUPPORT_EMAIL ?? "support@maxx.example",
  sellerEmail: process.env.SELLER_EMAIL ?? "sellers@maxx.example",
  feePercent: process.env.PLATFORM_FEE_PERCENT ?? "5",
} as const;
