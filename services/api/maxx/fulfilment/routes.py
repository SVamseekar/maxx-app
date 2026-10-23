"""Buyer side of fulfilment: delivery addresses, orders, problems."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from maxx.auth import ratelimit
from maxx.auth.deps import CurrentUser, same_origin
from maxx.fulfilment import service, store
from maxx.sellers import store as sellers

router = APIRouter(dependencies=[Depends(same_origin)])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UseAddress(Strict):
    address_id: str = Field(max_length=36)


class Problem(Strict):
    kind: str = Field(max_length=20)
    message: str = Field(min_length=10, max_length=2000)


class Message(Strict):
    body: str = Field(min_length=2, max_length=2000)


@router.get("/addresses")
def my_addresses(user: CurrentUser):
    return store.list_addresses(user.id)


@router.post("/addresses", status_code=201)
def add_address(body: store.Address, user: CurrentUser):
    ratelimit.hit(f"address:{user.id}", 20, 3600)
    if len(store.list_addresses(user.id)) >= 10:
        raise HTTPException(409, "You can keep up to 10 addresses. Delete one first.")
    return store.summarize(store.add_address(user.id, body))


@router.post("/addresses/{address_id}/delete")
def delete_address(address_id: str, user: CurrentUser):
    if not store.delete_address(user.id, address_id):
        raise HTTPException(404, "Address not found.")
    return {"status": "deleted"}


def _order_view(order: dict) -> dict:
    seller = sellers.by_code(order["seller_code"])
    case = store.open_case_for(order["id"])
    cases = store.cases_for_orders([order["id"]])
    return {
        "id": order["id"],
        "bloc_id": order["bloc_id"],
        "title": order["title"],
        "amount": str(order["amount"]),
        "currency": order["currency"],
        "status": order["status"],
        "ship_by": order["ship_by"],
        "carrier": order["carrier"],
        "tracking": order["tracking"],
        "shipped_at": order["shipped_at"],
        "created_at": order["created_at"],
        "has_address": bool(order["address_blob"]),
        "seller": {
            "code": order["seller_code"],
            "name": seller["business_name"] if seller else "Seller",
        },
        "open_case_id": case["id"] if case else None,
        "cases": [
            {
                "id": c["id"],
                "kind": c["kind"],
                "status": c["status"],
                "opened_at": c["opened_at"],
                "respond_by": c["respond_by"],
                "resolution": c["resolution"],
                "messages": [
                    {"actor": e["actor"], "body": e["body"], "at": e["created_at"]}
                    for e in store.events_for(c["id"])
                ],
            }
            for c in cases
        ],
    }


def _mine(user, order_id: str) -> dict:
    order = store.get_order(order_id)
    if not order or order["buyer_id"] != user.id:
        raise HTTPException(404, "Order not found.")
    return order


@router.get("/orders")
def my_orders(user: CurrentUser):
    return [_order_view(o) for o in store.orders_where(buyer_id=user.id)]


@router.get("/orders/{order_id}")
def one_order(order_id: str, user: CurrentUser):
    return _order_view(_mine(user, order_id))


@router.post("/orders/{order_id}/address")
def choose_address(order_id: str, body: UseAddress, user: CurrentUser):
    try:
        return _order_view(service.set_address(user.id, order_id, body.address_id))
    except LookupError:
        raise HTTPException(404, "Order or address not found.") from None
    except service.Refused as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, user: CurrentUser):
    ratelimit.hit(f"order-act:{user.id}", 30, 3600)
    try:
        return _order_view(await service.cancel_by_buyer(user.id, order_id))
    except LookupError:
        raise HTTPException(404, "Order not found.") from None
    except service.Refused as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/orders/{order_id}/delivered")
def delivered(order_id: str, user: CurrentUser):
    try:
        return _order_view(service.confirm_delivery(user.id, order_id))
    except LookupError:
        raise HTTPException(404, "Order not found.") from None
    except service.Refused as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/orders/{order_id}/problem", status_code=201)
def report_problem(order_id: str, body: Problem, user: CurrentUser):
    ratelimit.hit(f"case-open:{user.id}", 10, 3600)
    try:
        case = service.open_case(user.id, order_id, body.kind, body.message)
    except LookupError:
        raise HTTPException(404, "Order not found.") from None
    except service.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    return {"case_id": case["id"], "respond_by": case["respond_by"]}


@router.post("/cases/{case_id}/message")
def message_case(case_id: str, body: Message, user: CurrentUser):
    ratelimit.hit(f"case-msg:{user.id}", 60, 3600)
    try:
        service.post_message(user.id, case_id, body.body)
    except LookupError:
        raise HTTPException(404, "Case not found.") from None
    except service.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    return {"status": "sent"}


@router.post("/cases/{case_id}/withdraw")
async def withdraw(case_id: str, user: CurrentUser):
    try:
        await service.withdraw_case(user.id, case_id)
    except LookupError:
        raise HTTPException(404, "Case not found.") from None
    except service.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    return {"status": "withdrawn"}


@router.get("/sellers/{code}")
def seller_info(code: str, user: CurrentUser):
    """Trader details for a seller you bought from (EU Digital Services Act art. 30)."""
    if not any(o["seller_code"] == code for o in store.orders_where(buyer_id=user.id)):
        raise HTTPException(404, "Seller not found.")
    seller = sellers.by_code(code)
    if not seller:
        raise HTTPException(404, "Seller not found.")
    return sellers.public_profile(seller)
