import { SITE } from "../lib/site";
import type { Doc } from "./types";

export const terms: Doc = {
  slug: "terms",
  title: "Terms of Service",
  audience: "Everyone who uses Maxx as a buyer or visitor",
  summary: "The rules for using Maxx to join buying groups, set a maximum price and pay only the winning price. Sellers also accept the Seller Agreement.",
  sections: [
    { id: "what", title: "What Maxx is, and is not", body: [
      "Maxx is a platform that brings buyers of the same product together (a “Bloc”), lets each of them set the most they will pay, and uses automated agents to negotiate one group price with sellers. PayPal holds each buyer’s money until the outcome is known.",
      { list: [
        "Maxx is not the seller. The seller named on your order sells you the goods and is responsible for them.",
        "Maxx does not ship, store, inspect, repair or insure goods. Shipping, delivery, returns, warranties and customer service for the goods are the seller’s responsibility.",
        "Maxx does coordinate the order: it collects your delivery address after you win, tells the seller where to ship, pays the seller after they mark the order shipped, and refunds you if the seller does not ship in time.",
        "Maxx does not guarantee that a Bloc will reach a deal, that a seller will take part, or that any price will be reached.",
      ] },
    ] },
    { id: "eligibility", title: "Eligibility and your account", body: [
      "You must be old enough to enter a binding contract where you live (18 in most places) and able to pay through PayPal. You are responsible for what happens under your account.",
      { list: [
        "Give us accurate information and keep your email address working. We use it for sign-in links, security alerts and order updates.",
        "Keep your sign-in secure. Use a passkey or an authenticator app where you can. Tell us quickly if you think someone else has access.",
        "One person, one account. Do not create accounts to get around limits, bans or Bloc rules.",
      ] },
    ] },
    { id: "joining", title: "Joining a Bloc and your maximum price", body: [
      "When you join, you choose a maximum price between half of the product’s typical price and the typical price. PayPal places a hold (an authorization) for that maximum. A hold is not a charge. It reserves the money until the Bloc finishes.",
      { list: [
        "You can leave a Bloc until its negotiation starts. Leaving releases your hold.",
        "Once the negotiation starts your maximum is locked for that Bloc.",
        "If the group reaches a deal that fits within your maximum, you are charged only the price you were allocated, never more than your maximum. The rest of your hold is released.",
        "If no deal fits, or you are not allocated a unit, your hold is released and you pay nothing.",
        "PayPal holds last up to 29 days. Blocs normally finish far sooner. A hold that PayPal ends early means you cannot be charged for that Bloc.",
        "Where we show a price as “delivered”, it includes the seller’s shipping to your address. Maxx does not add shipping, fees or tax on top of the price you were allocated. Sellers are responsible for any tax they must collect and pay.",
      ] },
    ] },
    { id: "agents", title: "Automated agents", body: [
      "The negotiation is run by software agents. They act within limits you and each seller set: your maximum, and the seller’s floor price and stock. An agent cannot make you pay above your maximum or make a seller sell below its floor. The final allocation is calculated by a fixed, deterministic procedure, not by a language model. You can read the full explanation in AI agents and automated decisions.",
    ] },
    { id: "orders", title: "After you win: address, shipping and delivery", body: [
      { list: [
        "You will be asked for a delivery address. If you do not give one within the time shown on the order (7 days by default), the order is cancelled and you are refunded.",
        "The seller commits to ship within a number of days (1 to 14) and to give a tracking number. If they do not ship in time, you are refunded in full.",
        "You can cancel for a full refund until the seller marks the order shipped.",
        "Once shipped, tell us when it arrives. If you do not, the order is treated as delivered after 14 days unless you have opened a problem report.",
        "If something is wrong, open a problem report from the order within 60 days of the order. The seller must answer within 24 hours or you are refunded. If you and the seller disagree, Maxx decides.",
      ] },
      "Refunds go back to the PayPal payment method you used. See Cancellations, refunds and problem reports for the details.",
    ] },
    { id: "agent-checkout", title: "Checkout agent and PYUSD", body: [
      "The checkout agent can suggest the cheapest offer it can verify. It never spends money by itself: you must type and approve the exact total, and the amount charged must match what you approved. In this prototype, checkout payments go to a Maxx test account and no goods are shipped.",
      "You can choose to pay a checkout with PYUSD, a stablecoin issued by Paxos. You send the exact amount from your own wallet. Maxx only reads the blockchain to confirm the payment and never holds your keys. Blockchain payments cannot be reversed by Maxx.",
    ] },
    { id: "payments", title: "Payments", body: [
      "Payments are handled by PayPal under PayPal’s own terms. Maxx never sees your card number or PayPal password. Read Payments, PayPal and PYUSD for how holds, charges, refunds and seller payouts work.",
    ] },
    { id: "conduct", title: "How you may use Maxx", body: [
      "You agree to follow the Acceptable Use Policy. In short: no fraud, no manipulating a Bloc with fake accounts, no abuse of other people, no attacks on the service, and no use of the service for anything unlawful.",
    ] },
    { id: "content", title: "Your content", body: [
      "You keep ownership of what you give us, such as screenshots and problem reports. You give Maxx a limited licence to use it to run the service: to read a screenshot you scan, to show your messages to the other party in a problem report, and to keep records we are required to keep. Screenshots are processed in memory and are not stored.",
    ] },
    { id: "suspension", title: "Suspension and ending your account", body: [
      "You can close your account from Account settings. We may suspend or close an account that breaks these terms or the Acceptable Use Policy, or to protect people or money. We will tell you why unless the law or an investigation stops us, and you can ask us to review the decision (see Report content and appeal a decision).",
      "You cannot close an account while an order is undelivered or a problem is open. Close it once those finish. Some records must be kept after closure; see the Privacy Policy.",
    ] },
    { id: "liability", title: "Warranties and liability", body: [
      "Maxx is provided as is. We do not promise that it will always be available or free of errors. Nothing in these terms limits liability that cannot be limited by law, such as for death or personal injury caused by negligence, fraud, or consumer rights that cannot be waived.",
      "Subject to that, Maxx is not liable for the goods themselves, for what a seller does or fails to do, for losses we could not reasonably have foreseen, or for indirect or business losses. Where we are liable, our total liability for a claim is limited to the amount you paid in the transaction the claim is about.",
    ] },
    { id: "changes", title: "Changes, law and contact", body: [
      "We may change these terms. For a material change we will give at least 30 days’ notice by email and in the product, and you can close your account before it applies. The current version is always on this page.",
      `Governing law and the courts that hear disputes are stated in the Legal notice. Questions: ${SITE.legalEmail}.`,
    ] },
  ],
};

export const privacy: Doc = {
  slug: "privacy",
  title: "Privacy Policy",
  audience: "Everyone whose data Maxx handles",
  summary: "What Maxx collects, why, who sees it, how long it is kept, and how to see, export or delete it.",
  sections: [
    { id: "who", title: "Who is responsible", body: [
      `${SITE.entity} is the controller of the personal data described here. Contact for privacy questions and requests: ${SITE.privacyEmail}. The Legal notice has the address and any representative or data protection officer.`,
    ] },
    { id: "data", title: "What we collect and why", body: [
      { table: { head: ["Data", "Why", "Basis"], rows: [
        ["Account: email, display name, sign-in methods (password hash, passkey public keys, linked providers, encrypted authenticator secret)", "Create and secure your account", "Contract; security (legitimate interest)"],
        ["Security activity: sign-in events with a shortened network address (the first part only) and browser name", "Detect and alert you to unusual sign-ins", "Legitimate interest"],
        ["Bloc activity: your maximum price, your membership and outcome", "Run the negotiation and settle it", "Contract"],
        ["Payments: PayPal order, authorization, capture and refund ids, amounts, status", "Charge the winning price, refund, reconcile, keep accounting records", "Contract; legal obligation"],
        ["Delivery address and phone (encrypted), only after you win", "Let the seller ship your order", "Contract"],
        ["Orders and problem reports, including messages", "Fulfilment, refunds, disputes", "Contract; legitimate interest"],
        ["Seller details: legal name, business type, address, phone, support email, registration number, payout email, return policy, certifications", "Verify and publish trader details, pay sellers, comply with marketplace law", "Contract; legal obligation"],
        ["Screenshots you scan", "Read the product and price. Processed in memory; not stored by Maxx", "Contract"],
        ["Audit log: money and trust decisions (who, what, when)", "Security, fraud prevention, investigations", "Legitimate interest; legal obligation"],
      ] } },
      "We do not sell personal data. We do not use advertising or analytics trackers, and we do not build advertising profiles.",
    ] },
    { id: "sharing", title: "Who receives it", body: [
      { list: [
        "The seller you bought from receives your name, delivery address and phone number (if you gave one) and your order, so they can ship it. They must use it only for that, and keep it only as long as the law requires.",
        "You can see a seller’s trader details (name, address, contact, return policy) after you buy from them.",
        "Service providers who help us run Maxx, listed on the Service providers page: PayPal for payments and payouts, an email provider, hosting, and, when you use them, the AI and search providers and the sign-in provider you chose.",
        "Authorities, when the law requires, and professional advisers under confidentiality.",
      ] },
      "Other buyers in a Bloc never see who you are: your membership is shown to them only as an anonymous entry.",
    ] },
    { id: "ai", title: "AI and your data", body: [
      "In live mode, screenshots you scan are sent to an AI vision model and product details to a search provider. Negotiation prompts contain the demand curve of the group and each seller’s own private terms, never your identity. See AI agents and automated decisions.",
    ] },
    { id: "retention", title: "How long we keep it", body: [
      { table: { head: ["Data", "Kept for"], rows: [
        ["Delivery address on an order", "Wiped 90 days after the order finishes (delivered, cancelled or refunded), sooner if you close your account"],
        ["Saved addresses", "Until you delete them or close your account"],
        ["Account and security activity", "While your account is open; deleted when you close it"],
        ["Payment, order and refund records", "As long as tax and accounting law requires (commonly 6 to 10 years). They keep an opaque account id, not your profile"],
        ["Seller trader records", "For 6 months after the seller’s account closes, as marketplace law requires, then deleted"],
        ["Problem reports and messages", "While the order record is kept"],
        ["Audit log", "As long as needed for security and investigations, and reviewed at least yearly"],
      ] } },
      "Some of these periods are targets for the production service. The prototype wipes delivery addresses on schedule; the remaining schedules need to be enforced before launch.",
    ] },
    { id: "rights", title: "Your rights", body: [
      "Depending on where you live (for example under the GDPR, UK GDPR, or California law) you can ask to access, correct, delete, export or restrict your data, object to processing, and withdraw consent. You will not be treated worse for using these rights.",
      { list: [
        "Export: Account settings, “Download my data”, gives you a file with your account, security activity, addresses, payments, orders and problem reports.",
        "Delete: Account settings, “Delete my account”. This removes your profile, sign-in methods, saved addresses and the address copies on finished orders. Records we must keep stay, linked only to an opaque id.",
        "Anything else: write to us. We answer within one month.",
        "You can complain to your data protection authority. In the EU you can find yours on the European Data Protection Board’s website.",
      ] },
    ] },
    { id: "security", title: "Security", body: [
      "Passwords are hashed with scrypt and checked against a breach list without sending the password. Authenticator secrets and delivery addresses are encrypted at rest. Sessions are bound to secure cookies and expire. Read Security and responsible disclosure for more.",
    ] },
    { id: "transfers", title: "International transfers", body: [
      "Some providers process data outside your country. Where required we rely on adequacy decisions or standard contractual clauses. The Service providers page names each provider and what it receives.",
    ] },
    { id: "children", title: "Children", body: ["Maxx is not for people under 18, and we do not knowingly collect their data. Tell us if you think we have and we will delete it."] },
    { id: "changes", title: "Changes", body: ["We will tell you about material changes by email and in the product at least 30 days before they apply."] },
  ],
};

export const cookies: Doc = {
  slug: "cookies",
  title: "Cookies and local storage",
  audience: "Everyone who visits Maxx",
  summary: "Maxx uses only the cookies it needs to sign you in and keep you safe. No advertising or analytics cookies.",
  sections: [
    { id: "summary", title: "The short version", body: [
      "Maxx sets cookies that are strictly necessary to run the service and a few settings stored in your browser. Because they are necessary or are choices you made, we do not show a consent banner. We use no advertising, cross-site tracking or analytics cookies.",
    ] },
    { id: "list", title: "What is stored", body: [
      { table: { head: ["Name", "Type", "Purpose", "Lasts"], rows: [
        ["maxx_session (or __Host-maxx_session on HTTPS)", "Cookie, HttpOnly", "Keeps you signed in. Not readable by page scripts", "Until you sign out, or the session expires (idle and absolute limits)"],
        ["Trusted device cookie", "Cookie, HttpOnly", "Remembers a device you chose to trust, so two-step verification is not asked every time", "Up to the trusted-device period you saw when you chose it"],
        ["Sign-in state cookie", "Cookie, HttpOnly", "Protects a sign-in with Google, Apple, Microsoft or GitHub from forgery", "Minutes, removed when sign-in ends"],
        ["maxx-theme", "Local storage", "Remembers light or dark mode", "Until you clear it"],
        ["maxx-motion", "Local storage", "Remembers that you paused animations", "Until you clear it"],
        ["Cloudflare Turnstile", "Third-party, only if enabled", "Bot check on sign-up and sign-in forms", "Set by Cloudflare under its policy"],
      ] } },
    ] },
    { id: "control", title: "Your control", body: [
      "You can block or delete cookies in your browser, but signing in will not work without the session cookie. Clearing local storage resets your theme and motion choices.",
      "When you pay, PayPal’s own window sets its own cookies under PayPal’s policies. Maxx does not control those.",
    ] },
  ],
};

export const acceptableUse: Doc = {
  slug: "acceptable-use",
  title: "Acceptable Use Policy",
  audience: "Everyone who uses Maxx",
  summary: "What you may not do on Maxx, so groups stay fair and people stay safe.",
  sections: [
    { id: "fair", title: "Keep Blocs fair", body: [
      { list: [
        "Do not create or use more than one account to influence a Bloc, or ask others to join only to inflate demand and then leave.",
        "Do not join a Bloc you have no intention of paying for. A hold that you leave before the negotiation starts is free, but repeated abuse may limit your account.",
        "Sellers must not buy their own products, directly or through others, to raise demand or fees.",
        "Do not share or sell accounts.",
      ] },
    ] },
    { id: "safe", title: "Keep people safe", body: [
      { list: [
        "No harassment, threats, hate or discrimination in problem reports or any message.",
        "No fraud, impersonation, money laundering or use of stolen payment methods.",
        "No illegal goods or services. See Prohibited and restricted items.",
        "No sharing other people’s personal data, including the delivery details a seller receives, for anything except fulfilling the order.",
      ] },
    ] },
    { id: "service", title: "Keep the service safe", body: [
      { list: [
        "No attempts to break, probe or overload Maxx, scrape it at scale, or bypass limits and protections, except as the Security page permits for good-faith research.",
        "No use of automated tools to join, leave or place holds in bulk.",
        "No interfering with the negotiation agents, including trying to extract another party’s private terms.",
      ] },
    ] },
    { id: "enforce", title: "What happens if you break the rules", body: [
      "We may warn you, limit features, cancel orders, void holds, suspend or close an account, withhold seller payouts that relate to a violation, and report illegal activity to the authorities. Serious breaches may be actioned immediately. You can appeal; see Report content and appeal a decision.",
    ] },
  ],
};
