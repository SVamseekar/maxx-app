"""Product identity and listing rules for what sellers publish before any buyer asks.

A product is identified by its GTIN (the barcode number: UPC-A, EAN-13, GTIN-8 or GTIN-14) when
the seller has one, and otherwise by its exact title. GTINs are checked with GS1's check digit
(weights 3 and 1 from the right, modulo 10) and stored as 14 digits, so a UPC and the EAN-13 it
pads to are the same product. A passing check digit proves the number is well-formed, not that the
product is genuine; the seller certifies that.

Titles are screened for the prohibited categories in `rules.PROHIBITED` before anything is
published. The screen is a keyword list, so it is a first line, not the last: an administrator can
take down any listing, and every take-down releases every buyer's hold.
"""

from __future__ import annotations

import re

CATEGORIES = {
    "audio": "Audio and headphones",
    "computing": "Computers and accessories",
    "phones": "Phones and accessories",
    "cameras": "Cameras",
    "gaming": "Gaming",
    "home": "Home and kitchen",
    "appliances": "Small appliances",
    "sports": "Sports and outdoors",
    "toys": "Toys and games",
    "beauty": "Beauty and personal care (sealed)",
    "fashion": "Clothing, shoes and accessories",
    "books": "Books and media",
    "office": "Office and stationery",
    "tools": "Tools and DIY",
    "other": "Other new goods",
}

# Words that mean a listing falls in a prohibited category (rules.PROHIBITED). Whole words only.
BLOCKED_WORDS = {
    "replica": "counterfeit goods",
    "counterfeit": "counterfeit goods",
    "fake": "counterfeit goods",
    "knockoff": "counterfeit goods",
    "gun": "weapons",
    "pistol": "weapons",
    "rifle": "weapons",
    "ammo": "weapons",
    "ammunition": "weapons",
    "firearm": "weapons",
    "silencer": "weapons",
    "suppressor": "weapons",
    "taser": "weapons",
    "explosive": "weapons",
    "cannabis": "drugs",
    "marijuana": "drugs",
    "cbd": "drugs",
    "thc": "drugs",
    "kratom": "drugs",
    "vape": "drugs",
    "prescription": "prescription medicines",
    "viagra": "prescription medicines",
    "ozempic": "prescription medicines",
    "bitcoin": "digital value",
    "crypto": "digital value",
    "nft": "digital value",
    "voucher": "gift cards and vouchers",
    "giftcard": "gift cards and vouchers",
    "lottery": "gambling",
    "casino": "gambling",
    "refurbished": "used goods",
    "renewed": "used goods",
    "used": "used goods",
    "preowned": "used goods",
    "openbox": "used goods",
    "ticket": "tickets and travel",
    "tickets": "tickets and travel",
    "skimmer": "hacking tools",
    "jammer": "hacking tools",
}
BLOCKED_PHRASES = {
    "gift card": "gift cards and vouchers",
    "open box": "used goods",
    "pre owned": "used goods",
    "pre-owned": "used goods",
    "like new": "used goods",
}


def prohibited(title: str) -> str | None:
    """The prohibited category a title falls in, or None."""
    text = title.casefold()
    for phrase, reason in BLOCKED_PHRASES.items():
        if phrase in text:
            return reason
    for word in re.findall(r"[a-z0-9]+", text):
        if word in BLOCKED_WORDS:
            return BLOCKED_WORDS[word]
    return None


def gtin14(value: str) -> str | None:
    """A valid GTIN as 14 digits, or None if it is malformed or its check digit is wrong."""
    digits = re.sub(r"[\s-]", "", value or "")
    if not digits.isdigit() or len(digits) not in {8, 12, 13, 14}:
        return None
    padded = digits.zfill(14)
    body, check = padded[:-1], int(padded[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(body))
    return padded if (10 - total % 10) % 10 == check else None


def product_key(title: str, gtin: str | None) -> str:
    """How listings and buyer Blocs for the same product find each other."""
    if gtin:
        return f"gtin:{gtin}"
    return re.sub(r"\s+", " ", title).strip().casefold()
