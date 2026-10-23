import { SITE } from "../lib/site";
import type { Doc } from "./types";

export const sellerTerms: Doc = {
  slug: "seller-terms",
  title: "Seller Agreement",
  audience: "Businesses and individuals who sell through Maxx",
  summary: "What you promise, what Maxx does, how you are paid, and what happens if an order goes wrong. You are the seller of record. Maxx does not ship or handle goods.",
  sections: [
    { id: "role", title: "Who does what", body: [
      "You sell goods to buyers in a Bloc. You are the seller of record and the trader for consumer-law purposes. Maxx provides the place where buyers gather, the automated negotiation, payment collection through PayPal, order coordination and your payout.",
      { list: [
        "You are responsible for the goods, their listing, stock, packaging, shipping and customs, delivery, returns, refunds, warranties, product safety, customer service and tax.",
        "Maxx is not responsible for any of those things, and does not hold, inspect, ship, store or insure goods.",
        "Maxx is responsible for running the Bloc fairly, charging buyers only the allocated price, refunding buyers when you do not meet the commitments here, and paying you what you are owed.",
      ] },
    ] },
    { id: "eligibility", title: "Becoming a seller", body: [
      "You apply with your trader details: legal and trading name, whether you are an individual or a company, address, phone, support email, website if you have one, and a trade register number if you are a company in the EU. You confirm a payout PayPal email by entering a code we send to it. We may review and approve applications, ask for evidence, reject them, or suspend sellers.",
      { list: [
        "You must be able to enter a contract and be in a country Maxx supports for sellers.",
        "Everything you submit must be accurate. Keep it up to date. Changing your payout email pauses your offers and payouts until the new address is confirmed, and a cooling-off period may apply before it is paid.",
        "We publish your trader details to buyers who buy from you, as marketplace law requires (for example EU Digital Services Act article 30 and US INFORM Consumers Act).",
      ] },
    ] },
    { id: "self-cert", title: "What you certify", body: [
      { list: [
        "You sell only new, unused, genuine, lawful goods you are authorised to sell, and none of the Prohibited and restricted items.",
        "You will comply with consumer, product-safety, advertising, tax, customs and sanctions law that applies to you and to the buyers you ship to.",
        "You will honour the price allocated to you and the units allocated, up to your stock.",
      ] },
    ] },
    { id: "offers", title: "Standing offers and your agent", body: [
      "You publish a standing offer for a product: units you can supply, a floor price you will never go below, an opening price and a negotiating style (firm, balanced or eager). An automated agent negotiates for you within those limits in every Bloc for that product. It can never offer below your floor or beyond your stock, and you can pause an offer at any time. An offer you have already made in a running negotiation cannot be withdrawn.",
      "An allocation is a binding sale at the allocated price. Prices are delivered prices: you pay for shipping to the buyer. Maxx does not add shipping or tax on top for the buyer.",
    ] },
    { id: "fees", title: "Fees and payouts", body: [
      { list: [
        `Maxx’s fee is ${SITE.feePercent}% of the sale price of each order, taken from your payout. There are no listing or monthly fees. Buyers pay no fee.`,
        "You are paid after you mark an order shipped with a carrier and tracking number. Maxx pays you by PayPal Payouts to your confirmed payout email. Orders you never ship are refunded to the buyer and you are not paid.",
        "If a buyer is refunded after you were paid, you owe that amount back. Maxx deducts it from your next payouts, and may ask you to pay it if you stop selling.",
        "If a problem is opened before you have been paid for an order, the payout waits until it is resolved. We may withhold payouts that relate to a breach of this agreement or to suspected fraud.",
        "PayPal may charge its own fees under your PayPal account terms. You are responsible for your taxes. Maxx may be required to report your sales to tax authorities.",
      ] },
    ] },
    { id: "ship", title: "Shipping and delivery", body: [
      { list: [
        "You commit to ship within a set number of days (1 to 14) from the day the buyer gives an address. You must ship with a tracked service and enter the carrier and tracking number.",
        "You see the buyer’s name, address and phone number only for orders you must ship. Use them only to deliver and support that order, never for marketing, and delete them when no longer needed.",
        "If you do not ship in time (plus a 2 day grace period) the order is cancelled, the buyer is refunded in full and you receive a strike. Three strikes suspend your account.",
        "You must tell buyers promptly about delays. In the US the FTC’s Mail, Internet or Telephone Order Merchandise Rule requires shipping as promised or notifying and offering a refund.",
      ] },
    ] },
    { id: "returns", title: "Returns, refunds and problems", body: [
      { list: [
        "Publish a return policy that allows returns for at least 14 days and complies with the law where your buyers live. In the EU and UK consumers can generally withdraw from distance purchases within 14 days of delivery and have legal guarantee rights. You handle these, including the cost of returns where the law requires.",
        "When a buyer opens a problem report you must respond within 24 hours. If you do not, the buyer is refunded and you receive a strike.",
        "You can agree to a refund in one click. If you and the buyer disagree, Maxx reviews the evidence and decides. Our decision does not remove rights either of you has under law.",
      ] },
    ] },
    { id: "data", title: "Buyer data", body: [
      "For buyer data you receive, you act as an independent controller under data protection law. Keep it secure, use it only to fulfil the order and meet legal duties, and do not share or sell it. A breach involving buyer data must be reported to us without delay.",
    ] },
    { id: "suspend", title: "Suspension and ending", body: [
      "We may suspend or close your seller account for breach of this agreement, repeated missed commitments, complaints, suspected fraud or legal reasons. We will explain why, and you can appeal. You can stop selling at any time: pause your offers, finish your open orders, then close your account. We keep trader records for the period the law requires.",
    ] },
    { id: "liability", title: "Liability and indemnity", body: [
      "You are liable for the goods and for your actions as a seller, and you will cover Maxx for claims, fines and losses that arise from them, including claims by buyers or authorities. Maxx’s liability to you is limited as set out in the Terms of Service. Nothing here limits liability that cannot be limited by law.",
    ] },
    { id: "changes", title: "Changes and contact", body: [
      `We may update this agreement with at least 30 days’ notice. If you do not agree you can stop selling. Version ${SITE.version}. Questions: ${SITE.sellerEmail}.`,
    ] },
  ],
};

export const prohibited: Doc = {
  slug: "prohibited",
  title: "Prohibited and restricted items",
  audience: "Sellers, and buyers who want to report a listing",
  summary: "What may not be sold through Maxx. It follows the main marketplaces and PayPal’s own acceptable-use limits.",
  sections: [
    { id: "never", title: "Never allowed", body: [
      { list: [
        "Counterfeit, replica or unauthorised branded goods.",
        "Weapons, ammunition, explosives and weapon parts.",
        "Illegal drugs, drug paraphernalia and controlled substances.",
        "Prescription medicines, regulated medical devices and telemedicine.",
        "Cryptocurrency, digital value, gift cards, vouchers and prepaid cards.",
        "Gambling, lotteries and games with an entry fee and a prize.",
        "Adult content and services.",
        "Stolen goods, recalled or unsafe products, and hazardous materials.",
        "Used, refurbished or open-box goods. Maxx supports new goods only.",
        "Tickets, travel and anything delivered later than the stated shipping time.",
        "Personal data, hacking tools, and anything that breaks sanctions or export law.",
      ] },
    ] },
    { id: "why", title: "Why this list", body: [
      "Maxx moves money through PayPal, which restricts some categories in its Acceptable Use Policy, such as gambling, cryptocurrency and digital value, and prescription items. Marketplace law also requires us to act against illegal goods. We may remove an offer or suspend a seller for breaking these rules, and we may cancel and refund related orders.",
    ] },
    { id: "report", title: "Reporting", body: [
      `If you see something that should not be sold, report it using Report content and appeal a decision, or write to ${SITE.supportEmail}. We act on credible reports quickly.`,
    ] },
  ],
};

export const refunds: Doc = {
  slug: "refunds",
  title: "Cancellations, refunds and problem reports",
  audience: "Buyers and sellers",
  summary: "When you get your money back, how long it takes, and how disputes are decided.",
  sections: [
    { id: "no-charge", title: "When you are never charged", body: [
      { list: [
        "You leave a Bloc before the negotiation starts: your hold is released at once.",
        "The Bloc ends with no deal, or your maximum is below the clearing price: your hold is released and nothing is charged.",
        "You win, but PayPal could not take the payment: no order is created.",
      ] },
      "A released hold normally disappears from your PayPal account within minutes, but your bank may show it as pending for a few days.",
    ] },
    { id: "full", title: "When you are refunded in full", body: [
      { table: { head: ["Situation", "What happens"], rows: [
        ["You cancel before the seller ships", "Full refund to your PayPal payment method"],
        ["You do not give an address within the deadline (7 days)", "Order cancelled, full refund"],
        ["The seller does not ship in time (their commitment plus 2 days)", "Order cancelled, full refund; the seller gets a strike"],
        ["The seller does not answer a problem report within 24 hours", "Full refund; the seller gets a strike"],
        ["The seller agrees to refund", "Full refund"],
        ["Maxx decides in your favour after a dispute", "Full refund"],
      ] } },
      "Refunds are sent to the original PayPal payment method. PayPal usually shows them within a few days. Maxx never offers store credit instead of money when you are entitled to a refund.",
    ] },
    { id: "problem", title: "Reporting a problem", body: [
      "After the seller marks an order shipped you can open a problem report from the order within 60 days of the order: item not received, not as described, a return request, or something else. Describe what happened. The seller has 24 hours to reply. You can add messages, or withdraw the report if it is fixed.",
      { list: [
        "While a problem is open, the seller’s payout is held if it has not yet been paid.",
        "Evidence helps: photos, tracking pages, packaging and the listing.",
        "Your report is recorded straight away and the seller is told at once. We aim to decide a dispute within 7 days of the seller’s reply.",
      ] },
    ] },
    { id: "returns", title: "Returns", body: [
      "Returns are handled by the seller under the return policy shown on their trader details, which allows at least 14 days and follows the consumer law where you live. In the EU and UK, buying from a trader online generally gives you a 14-day right to withdraw and a legal guarantee for faulty goods. These rights are in addition to the steps above, and nothing here removes them.",
    ] },
    { id: "pyusd", title: "Checkout paid in PYUSD", body: [
      "A blockchain transfer cannot be reversed by Maxx. If a PYUSD checkout needs to be refunded, we would send PYUSD back to the sending wallet only after confirming it is yours. In the prototype, checkout purchases are demonstrations and no goods are shipped.",
    ] },
    { id: "escalate", title: "If you are not satisfied", body: [
      `Write to ${SITE.supportEmail} and ask for a human review. See Report content and appeal a decision for the full complaint process. You also keep your rights under PayPal’s terms and with your bank or card issuer.`,
    ] },
  ],
};

export const payments: Doc = {
  slug: "payments",
  title: "Payments, PayPal and PYUSD",
  audience: "Buyers and sellers",
  summary: "How holds, charges, refunds and payouts work, who touches your money, and what the prototype simulates.",
  sections: [
    { id: "paypal", title: "PayPal does the payments", body: [
      "Card and PayPal payments are processed by PayPal. You approve each hold in PayPal’s own window. Maxx never sees your card number or PayPal password, only the identifiers PayPal gives us for the order.",
    ] },
    { id: "flow", title: "The life of a payment", body: [
      { list: [
        "Hold. When you join a Bloc, PayPal authorizes up to your maximum. This reserves the money. It is not a charge.",
        "Charge. If you win, Maxx captures only your allocated price from the hold. The rest is released automatically.",
        "Release. If you do not win, or the Bloc fails, the hold is voided.",
        "Order. For a real seller, the money you paid is held by Maxx until the seller ships.",
        "Payout. When the seller marks the order shipped, Maxx pays them by PayPal Payouts, minus Maxx’s fee. Orders not shipped in time are refunded instead.",
        "Refund. Refunds return the full amount to your PayPal payment method.",
      ] },
      "Every PayPal request Maxx makes carries a unique request id, so a retry can never charge twice. Each step is recorded in an audit log, and the books for each Bloc are reconciled so that every dollar captured is accounted for as a seller payout, the Maxx fee, money held until shipping, or a refund.",
    ] },
    { id: "limits", title: "Limits that protect you", body: [
      { list: [
        "A single hold is capped, and so is the total you can have on hold at once, to limit the damage if someone gets into your account.",
        "Large holds and large checkouts ask you to confirm your identity again.",
        "Maxx can pause all new holds, charges and payouts at once if something looks wrong. Holds already in place stay safe while paused.",
        "Sellers are paid to a payout address they have confirmed. A newly confirmed address may wait before it is paid.",
      ] },
    ] },
    { id: "fees", title: "Fees", body: [
      `Buyers pay no Maxx fee. Maxx charges sellers ${SITE.feePercent}% of each sale, taken from the seller’s payout. PayPal’s own fees and currency conversion follow PayPal’s terms for the account concerned.`,
    ] },
    { id: "agent", title: "Agent checkout", body: [
      "The checkout agent builds an order from an offer you were shown. A guard compares the order amount with the offer and your typed approval, and refuses any difference. The agent holds no credentials and cannot spend by itself.",
    ] },
    { id: "pyusd", title: "PYUSD", body: [
      "PYUSD is a US dollar stablecoin issued by Paxos. It is not a PayPal payment method here: Maxx treats it as a blockchain transfer you make from your own wallet. Maxx shows an address and an exact amount with a short order tag in its last digits, reads the transaction from the blockchain, and accepts it only if the token, recipient, amount and age all match and the transaction has not paid another order. Maxx holds no wallet keys. Transfers cannot be reversed. Make sure you send the exact amount on the network shown.",
    ] },
    { id: "prototype", title: "What this prototype simulates", body: [
      "Until Maxx is launched, payments run in a simulator or in PayPal’s sandbox. No real money moves, and sandbox or simulated payouts are not real payouts. A banner on screen always says which mode you are in. Live PayPal is not enabled.",
      "A production launch needs PayPal’s marketplace programme approval, seller onboarding with identity checks, and a review of payment-services rules in each country.",
    ] },
  ],
};

export const consumerRights: Doc = {
  slug: "consumer-rights",
  title: "Your rights as a buyer",
  audience: "Buyers",
  summary: "A plain summary of the rights consumers usually have when they buy online, and how Maxx fits with them. It is information, not legal advice.",
  sections: [
    { id: "who", title: "Who sells to you", body: [
      "When you win a Bloc you are buying from the seller shown on your order, not from Maxx. After you buy, you can see the seller’s name, address, contact details and return policy on your order. In the EU these are called trader details and sellers must provide them.",
    ] },
    { id: "eu", title: "In the EU and UK", body: [
      { list: [
        "You usually have 14 days after delivery to withdraw from a distance purchase from a trader, without giving a reason. The seller must refund you, including standard delivery costs.",
        "Faulty goods are covered by a legal guarantee (at least two years in the EU) in addition to any commercial warranty.",
        "Goods must match their description and be delivered within the time agreed, or 30 days if none was agreed.",
        "Some goods are excluded from withdrawal, such as made-to-order or sealed hygiene items once opened. The seller must say so.",
      ] },
    ] },
    { id: "us", title: "In the US", body: [
      { list: [
        "Sellers must ship within the time they promised, or within 30 days if they gave no time, and tell you about delays and offer a refund (FTC Mail, Internet or Telephone Order Merchandise Rule).",
        "Return rights are set by the seller’s policy, and some states add rules. Maxx requires every seller to allow returns for at least 14 days.",
        "You can dispute a charge with your card issuer or bank if you cannot resolve a problem.",
      ] },
    ] },
    { id: "maxx", title: "What Maxx adds", body: [
      { list: [
        "You are only charged the winning price, never above your maximum.",
        "Your money is held until the seller ships; if they do not, you are refunded.",
        "A problem report with a 24-hour seller response time, and a decision by Maxx if you disagree.",
      ] },
      "These protections are on top of your legal rights, never instead of them.",
    ] },
    { id: "contact", title: "Help", body: [
      `If something is wrong, open a problem report from your order. For anything else write to ${SITE.supportEmail}. Government consumer agencies can also help, such as your national consumer authority, or the Federal Trade Commission in the US.`,
    ] },
  ],
};
