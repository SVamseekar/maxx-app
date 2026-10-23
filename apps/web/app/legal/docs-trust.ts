import { SITE } from "../lib/site";
import type { Doc } from "./types";

export const ai: Doc = {
  slug: "ai",
  title: "AI agents and automated decisions",
  audience: "Everyone who uses Maxx",
  summary: "Where Maxx uses AI and automation, what it can and cannot decide, and how to get a human to look at a result.",
  sections: [
    { id: "disclosure", title: "You are dealing with software agents", body: [
      "The negotiation in every Bloc is carried out by software agents: a negotiator that acts for the group, and one agent for each seller. The chat in the negotiation room is their conversation. When a message is from an agent, it is labelled as one. People are not typing those messages.",
      "The checkout agent that suggests a cheaper offer is also automated.",
    ] },
    { id: "where", title: "Where AI is used", body: [
      { table: { head: ["Feature", "What does the work"], rows: [
        ["Reading a screenshot", "An AI vision model, in live mode. In demo mode a fixed sample is replayed and labelled as such"],
        ["Finding comparable prices", "A search provider, with checks that reject prices not visible in the source"],
        ["Matching a product to its exact model", "A matching model, with your confirmation when it is not sure"],
        ["Group negotiator and seller agents", "AI language models in live mode. In demo mode, simple scripted policies, labelled “simulated offers”"],
        ["Deciding who gets which unit at which price", "A fixed deterministic procedure, never an AI model"],
        ["Checkout agent", "Rule-based. It does not use a language model"],
      ] } },
    ] },
    { id: "limits", title: "What agents cannot do", body: [
      { list: [
        "They cannot make you pay more than your maximum. The limit is enforced in code on the server and again before PayPal is asked to capture.",
        "They cannot make a seller sell below its floor price or beyond its stock. Whatever an agent says, the number is clamped to those limits.",
        "They cannot see who you are. The group negotiator receives the demand curve, not names or account details.",
        "They cannot spend money. Charges happen only through the payment steps you approve.",
        "They cannot see another seller’s private terms. Each seller agent sees only its own floor and stock, the demand, and how its offer ranked.",
      ] },
    ] },
    { id: "mistakes", title: "AI can be wrong", body: [
      "Language models can misread a screenshot or misjudge a negotiation. That is why a human always makes the decisions that matter: you confirm the product, you set your maximum, you approve any checkout total, and the price you pay is bounded by what you chose. Check a product’s details before you rely on a match.",
    ] },
    { id: "review", title: "A human can review a result", body: [
      `If you think a result was wrong or unfair, open a problem report on the order or write to ${SITE.supportEmail} and ask for a human review. A person at Maxx will look at the evidence and can reverse the outcome by refunding you. This does not affect your legal rights.`,
    ] },
    { id: "data", title: "Data sent to AI providers", body: [
      "In live mode, a screenshot you scan is sent to the vision provider and product details to the search provider. Negotiation prompts contain the group’s demand curve and the seller’s own private terms, not personal data about buyers. Providers are listed on the Service providers page. In demo mode nothing is sent to AI providers.",
    ] },
  ],
};

export const security: Doc = {
  slug: "security",
  title: "Security and responsible disclosure",
  audience: "Users and security researchers",
  summary: "How Maxx protects accounts and money, and how to report a vulnerability safely.",
  sections: [
    { id: "controls", title: "How Maxx protects you", body: [
      { list: [
        "Sign-in: passkeys, authenticator apps, emailed one-time links, and Google, Apple, Microsoft or GitHub. Passwords are hashed with scrypt and checked against known breaches without being sent anywhere.",
        "Sessions are in HttpOnly, SameSite cookies with idle and absolute limits. Sensitive changes ask you to confirm your identity again.",
        "Requests that change anything must come from Maxx itself, and the page’s Content-Security-Policy only allows Maxx’s own scripts.",
        "Authenticator secrets and delivery addresses are encrypted at rest. Seller private terms never leave the server.",
        "Money: Maxx never sees card details. Every payment call is idempotent, limits cap what can be held, payments can be paused instantly, and every money decision is written to an audit log.",
        "Seller payouts go only to an email address the seller has confirmed, and a changed address waits before being paid.",
      ] },
    ] },
    { id: "report", title: "Report a vulnerability", body: [
      `Email ${SITE.securityEmail} with what you found, how to reproduce it, and its impact. We will acknowledge within 3 business days and keep you updated. See the security.txt file at /.well-known/security.txt.`,
      "Please give us reasonable time to fix an issue before you make it public, and do not access, change or delete other people’s data.",
    ] },
    { id: "scope", title: "Scope and safe harbour", body: [
      { list: [
        "In scope: the Maxx web app and API, including account, payment, seller and order features.",
        "Out of scope: social engineering of staff or users, physical attacks, denial of service, spam, and the sandbox or systems of PayPal, Nebius, Tavily and other providers. Report those to the provider.",
        "Test only with accounts you own, and do not run automated scanners that generate heavy traffic.",
      ] },
      "If you act in good faith and within this policy, we will not take legal action against you and will work with you to fix the issue. We do not currently run a paid bounty, but we are glad to credit you.",
    ] },
    { id: "you", title: "What you can do", body: [
      { list: [
        "Add a passkey or an authenticator app from Account settings.",
        "Use a unique password from a password manager.",
        "Check Account settings for sign-in activity you do not recognise, and sign out other devices.",
        "Never share a sign-in code. Maxx staff never ask for one.",
      ] },
    ] },
  ],
};

export const accessibility: Doc = {
  slug: "accessibility",
  title: "Accessibility statement",
  audience: "Everyone, including people who use assistive technology",
  summary: "Our goal is that everyone can use Maxx. This is what we aim for, what we have done, and where we fall short.",
  sections: [
    { id: "goal", title: "Our goal", body: [
      "Maxx aims to meet the Web Content Accessibility Guidelines (WCAG) 2.2 at level AA. This matters for the European Accessibility Act, the Americans with Disabilities Act, and most of all for the people who use it.",
    ] },
    { id: "done", title: "What we have done", body: [
      { list: [
        "Every page works with a keyboard, with visible focus, and has a “Skip to content” link.",
        "Pages use headings, landmarks and labelled form fields. Dialogs trap focus and return it when closed.",
        "Many status changes (such as a scan finishing, a payment settling or a message arriving) are announced to screen readers through live regions.",
        "Light and dark themes, and text that scales. Layouts adapt from phone to desktop without sideways scrolling.",
        "Motion respects your device’s reduced-motion setting, and a pause button turns animation off at any time.",
        "Nothing relies on colour alone to convey meaning.",
      ] },
    ] },
    { id: "gaps", title: "Known limitations", body: [
      { list: [
        "Maxx has not yet had a formal audit by an external accessibility specialist or testing with a range of assistive technologies. Treat the claims above as our intent and our own checks.",
        "The negotiation chat updates live and can be busy for screen reader users. A saved conversation can be read in full after a Bloc ends.",
        "The PayPal approval window is provided by PayPal and follows PayPal’s own accessibility.",
        "Charts such as the group demand curve have a text equivalent, but it is less detailed than the chart.",
      ] },
    ] },
    { id: "feedback", title: "Tell us", body: [
      `If something does not work for you, write to ${SITE.supportEmail} with the page and what happened. We will reply within 5 business days and tell you how we will fix it or how else you can get what you need. If you are not satisfied you can contact the enforcement body in your country.`,
    ] },
  ],
};

export const imprint: Doc = {
  slug: "imprint",
  title: "Legal notice and contacts",
  audience: "Everyone",
  summary: "Who operates Maxx and how to reach us, including the contact points required of online marketplaces.",
  sections: [
    { id: "operator", title: "Operator", body: [
      { table: { head: ["", ""], rows: [
        ["Operator", SITE.entity],
        ["Address", SITE.address],
        ["Governing law and courts", SITE.jurisdiction],
        ["General", SITE.email],
        ["Support and complaints", SITE.supportEmail],
        ["Privacy and data requests", SITE.privacyEmail],
        ["Sellers", SITE.sellerEmail],
        ["Security", SITE.securityEmail],
        ["Legal and authorities", SITE.legalEmail],
      ] } },
      "Maxx is currently a prototype. The details above are placeholders until an operating entity exists, and must be completed before any public launch.",
    ] },
    { id: "dsa", title: "Contact points for authorities and users", body: [
      `For authorities (EU Digital Services Act article 11) and for users (article 12): ${SITE.legalEmail}. You can write in English. We answer without undue delay.`,
    ] },
    { id: "role", title: "Our role", body: [
      "Maxx is an online marketplace as defined in marketplace law: it lets buyers conclude distance contracts with sellers. The seller named on your order, not Maxx, is the other party to your purchase. Sellers’ identity and contact details are shown to buyers after a purchase.",
    ] },
  ],
};

export const noticeAndAction: Doc = {
  slug: "notice-and-action",
  title: "Report content and appeal a decision",
  audience: "Buyers, sellers and anyone who sees something wrong",
  summary: "How to report illegal or prohibited content, what we do with it, and how to challenge a decision we made.",
  sections: [
    { id: "report", title: "Report illegal or prohibited content", body: [
      `Write to ${SITE.legalEmail} (or ${SITE.supportEmail}) with: a clear explanation of why the content is illegal or prohibited, where it is (an offer, a seller code or an order), your name and email unless the report concerns a serious crime against children, and a statement that you believe the report is accurate and complete. We confirm that we received it.`,
      "We assess every report diligently and without bias, and tell you the decision and the reason. We may remove an offer, suspend a seller, cancel and refund orders, or take no action.",
    ] },
    { id: "decisions", title: "Decisions about your account or offers", body: [
      "If we restrict, suspend or close your account, remove an offer, withhold a payout or cancel an order because of a violation, we tell you what we decided and why, which facts and rules we relied on, whether automation was used, and how to challenge it.",
    ] },
    { id: "appeal", title: "How to appeal", body: [
      { list: [
        `Write to ${SITE.supportEmail} within six months of the decision, with your account email and what you think is wrong.`,
        "A person who was not involved in the original decision reviews it. We reply within 14 days. If we need more time we say so and why.",
        "If we agree, we reverse the decision and, where money is involved, correct it.",
        "If we do not, we explain and tell you about other routes: your national consumer or marketplace regulator, a certified out-of-court dispute settlement body if one is available to you, or the courts.",
      ] },
    ] },
    { id: "abuse", title: "Misuse", body: [
      "Please do not file reports you know are false, or file many reports to harass a seller. Repeated unfounded reports can lead us to ignore a sender’s reports for a time.",
    ] },
  ],
};

export const subprocessors: Doc = {
  slug: "subprocessors",
  title: "Service providers",
  audience: "Everyone, especially people who care where data goes",
  summary: "The companies that help Maxx run, what each one receives, and when.",
  sections: [
    { id: "list", title: "Who receives what", body: [
      { table: { head: ["Provider", "What it does", "What it receives", "When"], rows: [
        ["PayPal", "Payments, refunds, seller payouts, subscriptions", "Order amounts, payer identity as PayPal sees it, seller payout email", "Whenever payments are on"],
        ["Nebius", "AI models for screenshots, matching and negotiation", "Screenshots you scan; negotiation prompts without buyer identity", "Live mode only"],
        ["Tavily", "Searching for comparable prices", "Product details from a scan", "Live mode only"],
        ["Email provider (SMTP)", "Sign-in links, codes and alerts", "Your email address and message", "Always"],
        ["Cloud hosting and database", "Runs the service and stores data", "Everything described in the Privacy Policy, encrypted where stated", "Always"],
        ["Cloudflare Turnstile", "Bot check on forms", "Browser signals and your network address", "If enabled"],
        ["Google, Apple, Microsoft, GitHub", "Sign-in, if you choose it", "What the provider releases to Maxx: an id, email and name", "If you use them"],
        ["Have I Been Pwned", "Check a new password against breaches", "The first five characters of a password hash only", "When you set a password"],
        ["An Ethereum node provider", "Reads blockchain data to confirm PYUSD payments", "A transaction hash", "If PYUSD is enabled"],
      ] } },
      "We choose providers carefully, sign data processing agreements where the law requires them, and tell you here before adding a provider that receives personal data.",
    ] },
  ],
};
