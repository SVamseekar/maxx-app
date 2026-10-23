"""Shared helpers for seller and fulfilment tests."""

import re
import time

from maxx.auth import mail

KEY = "demo headphones · black"
ADDRESS = {
    "label": "Home",
    "name": "Bea Buyer",
    "line1": "22 Market Road",
    "line2": "",
    "city": "Leeds",
    "region": "",
    "postal": "LS1 1AA",
    "country": "GB",
    "phone": "+44 113 496 0000",
}


def application(payout="pay@shop.example", name="Shop Ltd", **changes):
    body = {
        "business_name": name,
        "legal_name": "Shop Limited",
        "business_type": "company",
        "country": "GB",
        "address_line1": "1 High Street",
        "address_city": "London",
        "address_region": "",
        "address_postal": "N1 1AA",
        "phone": "+44 20 7946 0000",
        "support_email": "help@shop.example",
        "website": "https://shop.example",
        "trade_register_no": "12345678",
        "payout_email": payout,
        "ship_within_days": 3,
        "ships_to": ["GB", "US"],
        "return_days": 30,
        "return_policy": "Return unused items in original packaging within 30 days for a refund.",
        "accept_terms": True,
        "certify_accurate": True,
        "certify_lawful": True,
        "certify_authorised": True,
    }
    return {**body, **changes}


def apply(client, payout="pay@shop.example", name="Shop Ltd", **changes):
    return client.post("/seller/apply", json=application(payout, name, **changes))


def code_sent_to(address):
    sent = [m for m in mail.outbox if m["to"] == address and "confirmation code" in m["subject"]]
    assert sent, "no code was emailed"
    return re.search(r"code is (\d{6})", sent[-1]["text"]).group(1)


def onboard(client, payout="pay@shop.example", **changes):
    assert apply(client, payout, **changes).status_code == 201
    done = client.post("/seller/payout-verify", json={"code": code_sent_to(payout)})
    assert done.status_code == 200, done.text
    return done.json()


def offer(client, **changes):
    body = {
        "product_key": KEY,
        "stock": 50,
        "floor": "100.00",
        "opening_price": "130.00",
        "strategy": "eager",
    }
    return client.post("/seller/offers", json={**body, **changes})


def wait_settled(client, bloc="demo-success"):
    for _ in range(400):
        books = client.get(f"/money/blocs/{bloc}/ledger").json()
        if books["settlement"] in {"DONE", "PARTIAL"}:
            return books
        time.sleep(0.02)
    raise AssertionError("settlement did not finish")


def buy(buyer, bloc="demo-success", price="150"):
    """Place and authorise a hold, joining the Bloc. Returns the order id."""
    order = buyer.post(f"/money/blocs/{bloc}/hold", json={"max_price": price}).json()
    buyer.post(f"/money/holds/{order['order_id']}/simulate-approve")
    assert buyer.post(f"/money/holds/{order['order_id']}/authorize").status_code == 200
    return order["order_id"]
