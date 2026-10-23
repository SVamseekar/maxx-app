"""A clearly labelled in-process stand-in for PayPal, used when no sandbox keys are configured.

It models the parts of PayPal that Maxx depends on, with the same rules: an order is authorized
after the buyer approves it, an authorization can be captured once up to its amount (a partial
capture with `final_capture` releases the rest), voids are idempotent, and every write honours its
request id. State lives in the `simulator_objects` table so it survives restarts. Nothing here talks
to the network or moves real money, and ids start with `SIM-` so they can never be mistaken for
PayPal's.
"""

from __future__ import annotations

import json
import secrets
import time
from decimal import Decimal

from sqlalchemy import delete, select

from maxx import schema, storage
from maxx.money.paypal import PayPalError, money


def _id(kind: str) -> str:
    return f"SIM-{kind}-{secrets.token_hex(6).upper()}"


def _payout_outcome(receiver: str) -> str:
    """Like PayPal's sandbox, a payout to an address with no account stays unclaimed; these
    reserved test domains let tests and demos see the failure paths."""
    domain = receiver.rpartition("@")[2].lower()
    if domain == "unclaimed.example":
        return "UNCLAIMED"
    if domain == "fails.example":
        return "FAILED"
    return "SUCCESS"


class SimulatedPayPal:
    simulated = True

    def _engine(self):
        return storage.get_store().engine

    def _read(self, key: str) -> dict | None:
        with self._engine().connect() as db:
            row = db.execute(
                select(schema.simulator_objects.c.document).where(
                    schema.simulator_objects.c.key == key
                )
            ).first()
        return json.loads(row[0]) if row else None

    def _write(self, key: str, document: dict) -> None:
        with self._engine().begin() as db:
            db.execute(
                delete(schema.simulator_objects).where(schema.simulator_objects.c.key == key)
            )
            db.execute(
                schema.simulator_objects.insert().values(key=key, document=json.dumps(document))
            )

    def _once(self, request_id: str, make):
        """Same request id, same answer: the idempotency contract of PayPal-Request-Id."""
        key = f"idem:{request_id}"
        cached = self._read(key)
        if cached is not None:
            return cached
        result = make()
        self._write(key, result)
        return result

    async def create_order(
        self,
        amount: Decimal,
        reference: str,
        request_id: str,
        intent: str = "AUTHORIZE",
        description: str = "Maxx group buy",
        currency: str | None = None,
        mock: str | None = None,
    ) -> dict:
        def make():
            order = {
                "id": _id("ORD"),
                "status": "CREATED",
                "intent": intent,
                "amount": money(amount),
                "reference": reference,
                "mock": mock or "",
            }
            self._write(order["id"], order)
            return {"id": order["id"], "status": "CREATED"}

        return self._once(request_id, make)

    def approve(self, order_id: str) -> dict:
        """The buyer's click on the simulated PayPal approval sheet."""
        order = self._read(order_id)
        if not order or order["status"] not in {"CREATED", "APPROVED"}:
            raise PayPalError(
                "This simulated order cannot be approved.", 422, "ORDER_NOT_APPROVABLE"
            )
        order["status"] = "APPROVED"
        self._write(order_id, order)
        return {"id": order_id, "status": "APPROVED"}

    async def get_order(self, order_id: str) -> dict:
        order = self._read(order_id)
        if not order:
            raise PayPalError("Order not found.", 404, "INVALID_RESOURCE_ID")
        return {"id": order_id, "status": order["status"]}

    async def authorize_order(self, order_id: str, request_id: str, mock: str | None = None):
        def make():
            order = self._read(order_id)
            if not order:
                raise PayPalError("Order not found.", 404, "INVALID_RESOURCE_ID")
            if order["status"] != "APPROVED":
                raise PayPalError(
                    "The buyer has not approved this order.", 422, "ORDER_NOT_APPROVED"
                )
            if order["mock"] == "authorize_declined":
                raise PayPalError("The payment method was declined.", 422, "INSTRUMENT_DECLINED")
            authorization = {
                "id": _id("AUTH"),
                "order_id": order_id,
                "amount": order["amount"],
                "status": "CREATED",
                "captured": "0.00",
                "mock": order["mock"],
                "expires": int(time.time()) + 29 * 86400,
            }
            self._write(authorization["id"], authorization)
            order["status"] = "AUTHORIZED"
            self._write(order_id, order)
            return {"authorization_id": authorization["id"], "status": "CREATED"}

        return self._once(request_id, make)

    async def capture_order(self, order_id: str, request_id: str) -> dict:
        def make():
            order = self._read(order_id)
            if not order or order["status"] != "APPROVED":
                raise PayPalError(
                    "The buyer has not approved this order.", 422, "ORDER_NOT_APPROVED"
                )
            capture = {"id": _id("CAP"), "amount": order["amount"]}
            self._write(capture["id"], capture)
            order["status"] = "COMPLETED"
            self._write(order_id, order)
            return {"capture_id": capture["id"], "status": "COMPLETED"}

        return self._once(request_id, make)

    async def capture_authorization(
        self,
        authorization_id: str,
        amount: Decimal,
        request_id: str,
        final_capture: bool = True,
        currency: str | None = None,
        mock: str | None = None,
    ) -> dict:
        def make():
            auth = self._read(authorization_id)
            if not auth:
                raise PayPalError("Authorization not found.", 404, "INVALID_RESOURCE_ID")
            if auth["status"] == "VOIDED":
                raise PayPalError("This hold was released.", 422, "AUTHORIZATION_VOIDED")
            if auth["status"] == "CAPTURED":
                raise PayPalError(
                    "This hold was already captured.", 422, "AUTHORIZATION_ALREADY_CAPTURED"
                )
            if auth["expires"] < time.time():
                raise PayPalError("This hold expired.", 422, "AUTHORIZATION_EXPIRED")
            if auth["mock"] == "capture_declined" or mock == "capture_declined":
                raise PayPalError("The payment method was declined.", 422, "INSTRUMENT_DECLINED")
            # Real PayPal allows a small overage; the simulator is stricter to keep tests honest.
            if Decimal(money(amount)) > Decimal(auth["amount"]):
                raise PayPalError(
                    "Capture exceeds the authorization.", 422, "CAPTURE_AMOUNT_EXCEEDED"
                )
            capture = {
                "id": _id("CAP"),
                "authorization_id": authorization_id,
                "amount": money(amount),
            }
            self._write(capture["id"], capture)
            auth["captured"] = money(Decimal(auth["captured"]) + Decimal(money(amount)))
            auth["status"] = "CAPTURED" if final_capture else "PARTIALLY_CAPTURED"
            self._write(authorization_id, auth)
            return {"capture_id": capture["id"], "status": "COMPLETED"}

        return self._once(request_id, make)

    async def refund_capture(
        self, capture_id: str, amount: Decimal, request_id: str, note: str = ""
    ) -> dict:
        def make():
            capture = self._read(capture_id)
            if not capture:
                raise PayPalError("Capture not found.", 404, "INVALID_RESOURCE_ID")
            refunded = Decimal(capture.get("refunded", "0.00"))
            if refunded + Decimal(money(amount)) > Decimal(capture["amount"]):
                raise PayPalError("Refund exceeds the capture.", 422, "REFUND_AMOUNT_EXCEEDED")
            capture["refunded"] = money(refunded + Decimal(money(amount)))
            self._write(capture_id, capture)
            return {"refund_id": _id("REF"), "status": "COMPLETED"}

        return self._once(request_id, make)

    async def get_authorization(self, authorization_id: str) -> str:
        auth = self._read(authorization_id)
        if not auth:
            raise PayPalError("Authorization not found.", 404, "INVALID_RESOURCE_ID")
        return {"CAPTURED": "CAPTURED", "VOIDED": "VOIDED"}.get(auth["status"], "CREATED")

    async def get_capture(self, capture_id: str) -> str:
        if not self._read(capture_id):
            raise PayPalError("Capture not found.", 404, "INVALID_RESOURCE_ID")
        refunded = Decimal((self._read(capture_id) or {}).get("refunded", "0"))
        return "REFUNDED" if refunded > 0 else "COMPLETED"

    async def void_authorization(self, authorization_id: str, request_id: str) -> None:
        def make():
            auth = self._read(authorization_id)
            if not auth:
                raise PayPalError("Authorization not found.", 404, "INVALID_RESOURCE_ID")
            if auth["status"] in {"CAPTURED"}:
                raise PayPalError(
                    "A captured hold cannot be voided.", 422, "AUTHORIZATION_ALREADY_CAPTURED"
                )
            auth["status"] = "VOIDED"
            self._write(authorization_id, auth)
            return {"ok": True}

        self._once(request_id, make)

    async def create_payout(
        self, sender_batch_id: str, items: list[dict], subject: str = "Your Maxx payout"
    ) -> dict:
        def make():
            batch = {
                "id": _id("PAYOUT"),
                "items": [
                    {
                        "payout_item_id": _id("ITEM"),
                        "sender_item_id": i["sender_item_id"],
                        "receiver": i["receiver"],
                        "amount": money(i["amount"]),
                        "status": _payout_outcome(i["receiver"]),
                    }
                    for i in items
                ],
            }
            self._write(batch["id"], batch)
            return {"batch_id": batch["id"], "status": "SUCCESS"}

        # PayPal rejects a reused sender_batch_id within 30 days; replaying our own is a no-op.
        return self._once(f"payout:{sender_batch_id}", make)

    async def get_payout_batch(self, payout_batch_id: str) -> list[dict]:
        batch = self._read(payout_batch_id)
        if not batch:
            raise PayPalError("Payout batch not found.", 404, "INVALID_RESOURCE_ID")
        return [
            {
                "payout_item_id": item.get("payout_item_id", ""),
                "sender_item_id": item.get("sender_item_id", ""),
                "status": item.get("status", "SUCCESS"),
                "error": "RECEIVER_UNREGISTERED" if item.get("status") == "UNCLAIMED" else "",
            }
            for item in batch["items"]
        ]

    async def add_tracking(
        self, order_id: str, capture_id: str, number: str, carrier: str, request_id: str
    ) -> None:
        def make():
            if not self._read(capture_id):
                raise PayPalError("Capture not found.", 404, "INVALID_RESOURCE_ID")
            self._write(f"track:{order_id}:{number}", {"carrier": carrier, "capture": capture_id})
            return {"ok": True}

        self._once(request_id, make)

    async def create_subscription(
        self, plan_id: str, request_id: str, return_url: str, cancel_url: str
    ) -> dict:
        return self._once(
            f"sub:{request_id}",
            lambda: {"id": _id("SUB"), "status": "APPROVAL_PENDING", "approve_url": ""},
        )

    async def cancel_subscription(self, subscription_id: str, reason: str) -> None:
        return None

    async def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        from maxx.money.webhooks import verify_simulated

        return verify_simulated(headers, body)


_simulator = SimulatedPayPal()


def get_simulator() -> SimulatedPayPal:
    return _simulator
