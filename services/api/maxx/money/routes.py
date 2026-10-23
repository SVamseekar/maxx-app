"""HTTP surface for the money layer."""

from __future__ import annotations

import time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from maxx import audit
from maxx.auth import ratelimit
from maxx.auth.deps import CurrentUser, client_ip, ensure_fresh, same_origin
from maxx.config import settings
from maxx.money import chain, checkout, ledger, service, webhooks
from maxx.money.paypal import PayPalError, get_paypal
from maxx.negotiate.contracts import BlocView, Money
from maxx.negotiate.routes import RuntimeDep

router = APIRouter(prefix="/money", dependencies=[Depends(same_origin)])
hooks = APIRouter(prefix="/money")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HoldRequest(Strict):
    max_price: Money
    # Only honoured when PAYPAL_NEGATIVE_TESTING is on: lets the demo show a declined capture.
    test_case: str = Field(default="", max_length=30)


def _require_enabled():
    if not service.enabled():
        raise HTTPException(404, "Payments are not turned on.")


def public_config() -> dict:
    mode = settings.paypal_mode
    return {
        "mode": mode,
        "enabled": mode in {"simulator", "sandbox"},
        "simulated": mode == "simulator",
        "currency": settings.paypal_currency,
        "client_id": settings.paypal_client_id if mode == "sandbox" else "",
        "sdk_url": settings.paypal_sdk_url if mode == "sandbox" else "",
        "platform_fee_percent": settings.platform_fee_percent,
        "negative_testing": settings.paypal_negative_testing,
        "crypto": {
            "enabled": bool(chain.get_chain()),
            "asset": "PYUSD",
            "chain": settings.pyusd_chain,
            "address": chain.deposit_address(),
            "simulated": isinstance(chain.get_chain(), chain.SimulatedChain),
        },
    }


@router.get("/config")
def config():
    return public_config()


@router.post("/blocs/{id}/hold")
async def create_hold(
    id: str, body: HoldRequest, request: Request, user: CurrentUser, runtime: RuntimeDep
):
    _require_enabled()
    if body.max_price > Decimal(settings.hold_reauth_over):
        await ensure_fresh(request)  # large holds need a recent identity check
    ratelimit.hit(f"hold:{user.id}", 30, 600)
    store = runtime.store
    try:
        bloc = store.get(id)
    except KeyError:
        raise HTTPException(404, "Bloc not found.") from None
    test_case = body.test_case if settings.paypal_negative_testing else ""
    if test_case not in {"", "capture_declined", "authorize_declined"}:
        raise HTTPException(422, "Unknown test case.")
    try:
        payment = await service.start_hold(bloc, user.id, body.max_price, test_case)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except PayPalError:
        raise HTTPException(502, "PayPal is unavailable. Try again shortly.") from None
    return {
        "order_id": payment["order_id"],
        "amount": str(payment["max_amount"]),
        "currency": payment["currency"],
        "simulated": bool(payment["simulated"]),
        "status": payment["status"],
    }


@router.post("/holds/{order_id}/simulate-approve")
async def simulate_approve(order_id: str, user: CurrentUser):
    """Stands in for the buyer's approval on PayPal. Exists only in simulator mode."""
    if settings.paypal_mode != "simulator":
        raise HTTPException(404, "Not found.")
    payment = ledger.by_order(order_id)
    if not payment or payment["user_id"] != user.id:
        raise HTTPException(404, "Order not found.")
    get_paypal().approve(order_id)
    ledger.update_payment(payment["id"], status="APPROVED")
    return {"order_id": order_id, "status": "APPROVED"}


@router.post("/holds/{order_id}/authorize", response_model=BlocView)
async def authorize_hold(order_id: str, user: CurrentUser, runtime: RuntimeDep):
    _require_enabled()
    store = runtime.store
    try:
        bloc, _ = await service.authorize_hold(store, user.id, order_id)
    except LookupError:
        raise HTTPException(404, "Order not found.") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except PayPalError:
        raise HTTPException(502, "PayPal is unavailable. Try again shortly.") from None
    return bloc.public(user.id)


@router.post("/holds/{order_id}/cancel")
async def cancel_hold(order_id: str, user: CurrentUser):
    _require_enabled()
    await service.cancel_unfinished(user.id, order_id)
    return {"order_id": order_id, "status": "CANCELLED"}


def _receipt(payment: dict, titles: dict[str, str]) -> dict:
    captured = payment["captured_amount"]
    details = checkout.info(payment) if payment["kind"] == "checkout" else {}
    return {
        "id": payment["id"],
        "kind": payment["kind"],
        "bloc_id": payment["bloc_id"],
        "title": details.get("title") or titles.get(payment["bloc_id"] or "", ""),
        "method": details.get("method", "paypal"),
        "status": payment["status"],
        "held": str(payment["max_amount"]),
        "paid": str(captured) if captured is not None else None,
        "saved": str(Decimal(payment["max_amount"]) - Decimal(captured))
        if captured is not None and payment["kind"] == "hold"
        else None,
        "currency": payment["currency"],
        "simulated": bool(payment["simulated"]),
        "paypal": {
            "order": payment["order_id"],
            "authorization": payment["authorization_id"],
            "capture": payment["capture_id"] if details.get("method") != "pyusd" else None,
            "pyusd_tx": ("0x" + payment["capture_id"])
            if details.get("method") == "pyusd" and payment["capture_id"]
            else None,
        },
        "error": payment["error"],
        "at": payment["updated_at"],
    }


@router.get("/receipts")
def receipts(user: CurrentUser, runtime: RuntimeDep):
    store = runtime.store
    titles = {b.id: b.title for b in store.list()}
    return [_receipt(p, titles) for p in ledger.for_user(user.id)]


@router.get("/blocs/{id}/ledger")
def bloc_ledger(id: str, runtime: RuntimeDep):
    """Aggregate books for a Bloc. No buyer is identifiable here."""
    _require_enabled()
    store = runtime.store
    try:
        bloc = store.get(id)
    except KeyError:
        raise HTTPException(404, "Bloc not found.") from None
    # Read the settlement state first: if it says DONE, the books read after it are complete.
    state = service.settlement_status(id, bloc.generation) or (
        "WAITING" if bloc.status in {"FORMING", "OPEN", "NEGOTIATING"} else "NOT_NEEDED"
    )
    books = service.reconcile(id, bloc.generation)
    books["settlement"] = state
    books["simulated"] = settings.paypal_mode == "simulator"
    return books


def _stale_transmission(value: str | None) -> str:
    """PayPal retries for up to three days; anything older, or in the future, is a replay."""
    if not value:
        return ""
    from datetime import datetime

    try:
        sent = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return "unreadable time"
    now = time.time()
    if now - sent > 3 * 86400:
        return "older than three days"
    if sent - now > 600:
        return "from the future"
    return ""


@hooks.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    """Called by PayPal (not by a browser): authenticated by signature, not by origin or session."""
    if not service.enabled():
        raise HTTPException(404, "Not found.")
    ratelimit.hit(f"webhook:{client_ip(request)}", 600, 60)
    body = await request.body()
    if len(body) > 256_000:
        raise HTTPException(413, "Too large.")
    stale = _stale_transmission(request.headers.get("paypal-transmission-time"))
    if stale:
        audit.record("paypal", "webhook.stale", client_ip(request), stale)
        raise HTTPException(400, "This event is too old or from the future.")
    pp = get_paypal()
    try:
        verified = await pp.verify_webhook(dict(request.headers), body)
    except PayPalError:
        raise HTTPException(503, "Could not verify the event. PayPal will retry.") from None
    if not verified:
        # Only the first few per minute are recorded, so an attacker cannot fill the log.
        if ratelimit.count(f"webhook-bad:{client_ip(request)}", 60) < 5:
            audit.record("paypal", "webhook.rejected", client_ip(request), "bad signature")
        ratelimit.record(f"webhook-bad:{client_ip(request)}")
        raise HTTPException(400, "Signature check failed.")
    try:
        result = webhooks.handle_event(webhooks.parse(body))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"received": True, **result}


# ---- agentic checkout ---------------------------------------------------------------------------

checkout_router = APIRouter(prefix="/checkout", dependencies=[Depends(same_origin)])


@checkout_router.get("/tools")
def checkout_tools():
    """The tool surface the checkout agent may call; same names as PayPal's Agent Toolkit."""
    return {"tools": checkout.TOOLS, "limit": settings.checkout_max_amount}


@checkout_router.post("/propose")
def checkout_propose(body: checkout.ProposeRequest, user: CurrentUser):
    _require_enabled()
    ratelimit.hit(f"checkout:{user.id}", 20, 600)
    try:
        return checkout.propose(user.id, body)
    except checkout.Refused as exc:
        raise HTTPException(409, str(exc)) from None


@checkout_router.post("/confirm")
async def checkout_confirm(body: checkout.ConfirmRequest, request: Request, user: CurrentUser):
    _require_enabled()
    try:
        total = Decimal(body.confirm_total)
    except ArithmeticError:
        total = Decimal(0)
    if total > Decimal(settings.checkout_reauth_over):
        await ensure_fresh(request)
    ratelimit.hit(f"checkout:{user.id}", 20, 600)
    try:
        return await checkout.create_order(
            user.id, body.proposal_token, body.confirm_total, body.method
        )
    except checkout.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    except PayPalError:
        raise HTTPException(502, "PayPal is unavailable. Try again shortly.") from None


@checkout_router.get("/orders/{order_id}")
async def checkout_order(order_id: str, user: CurrentUser):
    _require_enabled()
    try:
        return await checkout.get_order(user.id, order_id)
    except LookupError:
        raise HTTPException(404, "Order not found.") from None


@checkout_router.post("/orders/{order_id}/capture")
async def checkout_capture(order_id: str, user: CurrentUser):
    _require_enabled()
    try:
        return await checkout.capture_order(user.id, order_id)
    except LookupError:
        raise HTTPException(404, "Order not found.") from None
    except checkout.Refused as exc:
        raise HTTPException(409, str(exc)) from None
    except PayPalError:
        raise HTTPException(502, "PayPal is unavailable. Try again shortly.") from None


class VerifyPyusd(checkout.Strict):
    order_id: str = Field(max_length=64)
    tx_hash: str = Field(max_length=80)


class SimulateSend(checkout.Strict):
    order_id: str = Field(max_length=64)


@checkout_router.post("/pyusd/verify")
async def pyusd_verify(body: VerifyPyusd, user: CurrentUser):
    _require_enabled()
    ratelimit.hit(f"pyusd:{user.id}", 30, 600)
    try:
        return await checkout.verify_pyusd(user.id, body.order_id, body.tx_hash.strip())
    except LookupError:
        raise HTTPException(404, "Order not found.") from None
    except checkout.Refused as exc:
        raise HTTPException(409, str(exc)) from None


@checkout_router.post("/pyusd/simulate-send")
async def pyusd_simulate_send(body: SimulateSend, user: CurrentUser):
    """Stands in for sending PYUSD from a wallet. Exists only against the simulated chain."""
    source = chain.get_chain()
    if not isinstance(source, chain.SimulatedChain):
        raise HTTPException(404, "Not found.")
    payment = ledger.by_order(body.order_id)
    details = checkout.info(payment) if payment else {}
    if not payment or payment["user_id"] != user.id or details.get("method") != "pyusd":
        raise HTTPException(404, "Order not found.")
    return {"tx_hash": source.send(chain.deposit_address(), int(details["units"]))}


# ---- Maxx Plus (PayPal Subscriptions) ---------------------------------------------------------

from maxx.money import subscriptions  # noqa: E402

plus_router = APIRouter(prefix="/money/subscription", dependencies=[Depends(same_origin)])


class Subscribe(checkout.Strict):
    plan: str = Field(pattern="^(weekly|yearly)$")


@plus_router.get("")
def subscription_status(user: CurrentUser):
    found = subscriptions.current(user.id)
    return {
        "enabled": service.enabled(),
        "simulated": settings.paypal_mode == "simulator",
        "plans": [{"id": key, **value} for key, value in subscriptions.PLANS.items()],
        "premium": subscriptions.is_premium(user.id),
        "subscription": {"id": found["id"], "plan": found["plan"], "status": found["status"]}
        if found
        else None,
        "checkout_limit": subscriptions.checkout_limit(user.id),
        "benefits": [f"Agent checkout limit raised to ${settings.checkout_premium_max_amount}"],
    }


@plus_router.post("")
async def subscription_start(body: Subscribe, user: CurrentUser):
    _require_enabled()
    ratelimit.hit(f"subscribe:{user.id}", 10, 3600)
    try:
        return await subscriptions.subscribe(user.id, body.plan)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except PayPalError:
        raise HTTPException(502, "PayPal is unavailable. Try again shortly.") from None


@plus_router.post("/simulate-approve")
def subscription_simulate_approve(user: CurrentUser):
    """Stands in for approving the subscription on PayPal; activation still arrives as a webhook."""
    if settings.paypal_mode != "simulator":
        raise HTTPException(404, "Not found.")
    found = subscriptions.current(user.id)
    if not found or found["status"] != "APPROVAL_PENDING":
        raise HTTPException(409, "There is no subscription waiting for approval.")
    subscriptions.deliver_simulated(found["id"], "ACTIVATED")
    return {"status": "ACTIVE"}


@plus_router.post("/cancel")
async def subscription_cancel(user: CurrentUser):
    _require_enabled()
    try:
        await subscriptions.cancel(user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except PayPalError:
        raise HTTPException(502, "PayPal is unavailable. Try again shortly.") from None
    return {"status": "CANCELLED"}
