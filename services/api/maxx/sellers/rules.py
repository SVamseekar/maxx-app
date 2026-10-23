"""The seller agreement in one place, so the API, the form and the legal pages never disagree."""

TERMS_VERSION = "2026-10-13"

# Short statements a seller must accept. The full text lives on /legal/seller-terms.
TERMS = [
    "I am the seller of record. I am responsible for my products, their descriptions, "
    "shipping, delivery, returns, refunds, warranties, customer service and taxes. Maxx does "
    "not ship, inspect, store or insure any goods.",
    "I will ship each order within the time I commit to, with tracking, and I understand I am "
    "paid after I mark an order shipped. Orders I do not ship in time are refunded to the buyer "
    "and count against my account.",
    "I will not be paid, and Maxx will never sell for me, below my floor price.",
    "I will honour the return and refund promise I publish, and at least the rights the law "
    "gives buyers where they live.",
    "I will answer a buyer's problem report within the response time, or the buyer is "
    "refunded and the amount is deducted from my payouts.",
    "Maxx keeps its fee from each sale and may deduct refunds I owe from later payouts.",
    "I sell only new, unused, genuine, lawful goods that I am authorised to sell, and none of "
    "the prohibited items.",
    "Everything I submitted is accurate, I will keep it up to date, and Maxx may suspend my "
    "account if it is not.",
]

# Categories a seller may not offer. Mirrors what PayPal and the main marketplaces refuse.
PROHIBITED = [
    "Counterfeit, replica or unauthorised branded goods",
    "Weapons, ammunition, explosives and weapon parts",
    "Illegal drugs, drug paraphernalia and controlled substances",
    "Prescription medicines, medical devices that need a licence, and telemedicine",
    "Cryptocurrency, digital value, gift cards, vouchers and prepaid cards",
    "Gambling, lotteries and games with an entry fee and a prize",
    "Adult content and services",
    "Stolen goods, recalled or unsafe products, hazardous materials",
    "Used, refurbished or open-box goods (Maxx supports new goods only)",
    "Tickets, travel and anything delivered later than the stated shipping time",
    "Personal data, hacking tools and anything that breaks sanctions or export law",
]

COUNTRIES = {
    "US",
    "CA",
    "GB",
    "IE",
    "DE",
    "FR",
    "ES",
    "IT",
    "NL",
    "BE",
    "AT",
    "PT",
    "SE",
    "DK",
    "FI",
    "NO",
    "PL",
    "CZ",
    "AU",
    "NZ",
    "IN",
    "SG",
    "JP",
    "AE",
}
EU = {"DE", "FR", "ES", "IT", "NL", "BE", "AT", "PT", "SE", "DK", "FI", "PL", "CZ", "IE"}
MIN_RETURN_DAYS = 14
