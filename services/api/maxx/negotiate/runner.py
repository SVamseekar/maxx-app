"""Bounded negotiation orchestration; durable, sanitized events and terminal releases."""

import asyncio
from decimal import Decimal

from maxx import audit
from maxx.config import settings
from maxx.negotiate.adapters import (
    Adapter,
    Plan,
    guard_ai_bid,
    reserve_ceiling,
    rules_bid,
    safe_offer,
    seller_context,
)
from maxx.negotiate.blocs import emit, transition
from maxx.negotiate.contracts import Bloc, Clearing
from maxx.negotiate.engine import clear
from maxx.negotiate.store import BlocStore


def terminal_failure(bloc: Bloc, reason: str):
    for member in bloc.members:
        if member.status == "HELD":
            member.status = "RELEASED"
            emit(bloc, "commitment_released", member_id=member.id, reason="failed", simulated=True)
    bloc.outcome = Clearing(unserved=[m.id for m in bloc.members if m.status == "RELEASED"])
    bloc.failure_reason = reason
    transition(bloc, "FAILED")
    emit(bloc, "failed", reason=reason, simulated=True)


async def run_negotiation(
    store: BlocStore,
    id: str,
    adapter: Adapter,
    round_delay: float | None = None,
    deadline: float | None = None,
):
    bloc = store.get(id)
    if bloc.status != "NEGOTIATING":
        return
    delay = (
        settings.fixture_round_delay
        if round_delay is None and adapter.mode == "fixture"
        else (round_delay or 0)
    )
    feedback = {}
    withdrawn = set()
    last_price: dict[str, Decimal] = {}
    previous = {"served": 0, "unserved": sum(m.status == "HELD" for m in bloc.members)}

    def persist():
        bloc.calls = list(adapter.calls)
        store.save(bloc)

    async def retry(kind, function):
        for attempt in range(2):
            try:
                return await asyncio.wait_for(function(), timeout=settings.provider_timeout)
            except Exception as exc:
                if attempt:
                    raise RuntimeError("Provider failed after one retry.") from exc
                emit(bloc, "provider_retry", role=kind, attempt=2)
                persist()

    try:
        async with asyncio.timeout(deadline or settings.negotiation_timeout):
            members = [m for m in bloc.members if m.status == "HELD"]
            if not members:
                raise RuntimeError("No active members.")
            demand = [
                (str(price), sum(m.max_price >= price for m in members))
                for price in sorted({m.max_price for m in members})
            ]
            ceiling = reserve_ceiling(members)
            latest = Clearing()
            offers = []
            for round in range(1, 6):
                bloc.round = round
                emit(bloc, "round_start", round=round, mode=adapter.mode)
                persist()
                context = {
                    "round": round,
                    "product": bloc.title,
                    "demand": demand,
                    "reserve_ceiling": str(ceiling),
                    "previous_result": previous,
                    "seller_ids": [s.id for s in bloc.sellers if s.id not in withdrawn],
                }
                plan = Plan.model_validate(
                    await retry("negotiator", lambda context=context: adapter.negotiator(context))
                )
                reserve = min(plan.reserve or ceiling, ceiling)
                emit(bloc, "reserve_set", round=round, price=str(reserve))
                for seller_id in plan.messages:
                    if seller_id in context["seller_ids"]:
                        emit(
                            bloc,
                            "negotiator_message",
                            round=round,
                            to=seller_id,
                            text="Please improve your offer.",
                        )
                persist()
                if plan.close:
                    # close() clears the current offers; never request another seller round.
                    latest = clear(
                        members,
                        [o for o in offers if o is not None and o.price <= reserve and o.max_qty],
                    )
                    break

                async def bid_for(
                    seller, current_round=round, current_feedback=feedback, current_plan=plan
                ):
                    try:
                        if seller.account_id and seller.agent == "rules":
                            # A real seller who chose fixed rules never has a model bid for them.
                            offer, clamped = safe_offer(seller, rules_bid(seller, current_round))
                        else:
                            private = seller_context(
                                seller,
                                bloc.title,
                                current_round,
                                demand,
                                current_feedback.get(seller.id, {}),
                                current_plan.messages.get(seller.id),
                                last_price.get(seller.id),
                            )
                            bid = await retry("seller", lambda: adapter.seller(private))
                            if seller.account_id:
                                offer, applied = guard_ai_bid(
                                    seller, bid, last_price.get(seller.id)
                                )
                                clamped = bool(applied)
                                if applied:
                                    # Which limit applied (a floor, stock) would reveal the
                                    # seller's private numbers, so the room only sees "clamped";
                                    # the detail goes to the audit log.
                                    audit.record(
                                        f"seller:{seller.id}",
                                        "agent.limited",
                                        bloc.id,
                                        f"round {current_round}: {', '.join(applied)}",
                                    )
                            else:
                                offer, clamped = safe_offer(seller, bid)
                        if offer is not None:
                            last_price[seller.id] = offer.price
                        if offer is None:
                            withdrawn.add(seller.id)
                            emit(bloc, "seller_withdrew", round=current_round, seller=seller.id)
                        else:
                            emit(
                                bloc,
                                "seller_offer",
                                round=current_round,
                                seller=seller.id,
                                price=str(offer.price),
                                qty=offer.max_qty,
                                clamped=clamped,
                                message="Offer submitted. Private seller details stay private.",
                            )
                        persist()
                        return offer
                    except Exception:
                        withdrawn.add(seller.id)
                        emit(bloc, "seller_unavailable", round=current_round, seller=seller.id)
                        persist()
                        return None

                offers = await asyncio.gather(
                    *(bid_for(s) for s in bloc.sellers if s.id not in withdrawn)
                )
                valid = [o for o in offers if o is not None and o.price <= reserve and o.max_qty]
                latest = clear(members, valid)
                average = (
                    sum(a.price for a in latest.allocations) / len(latest.allocations)
                    if latest.allocations
                    else None
                )
                previous = {
                    "served": len(latest.allocations),
                    "unserved": len(latest.unserved),
                    "avg_price": str(average.quantize(Decimal(".01"))) if average else None,
                }
                emit(bloc, "tentative_allocation", round=round, **previous)
                feedback = {}
                submitted = [o for o in offers if o is not None]
                for offer in submitted:
                    feedback[offer.seller_id] = {
                        "your_rank_bucket": "cheapest"
                        if valid and offer.price == min(o.price for o in valid)
                        else "not_cheapest",
                        "units_you_would_win": sum(
                            a.seller_id == offer.seller_id for a in latest.allocations
                        ),
                        "group_units_unserved_at_your_price": sum(
                            m.id in latest.unserved and m.max_price >= offer.price for m in members
                        ),
                    }
                persist()
                if delay:
                    await asyncio.sleep(delay)
                if round == 5 or not (set(context["seller_ids"]) - withdrawn):
                    break
            if not latest.allocations:
                terminal_failure(bloc, "No qualifying deal. All simulated commitments released.")
            else:
                bloc.outcome = latest
                by_member = {a.member_id: a for a in latest.allocations}
                for member in members:
                    allocation = by_member.get(member.id)
                    if allocation:
                        member.status = "WIN"
                        member.final_price = allocation.price
                        member.seller_id = allocation.seller_id
                        emit(
                            bloc,
                            "member_allocated",
                            member_id=member.id,
                            seller=allocation.seller_id,
                            price=str(allocation.price),
                            simulated=True,
                        )
                    else:
                        member.status = "BELOW_CLEARING"
                        emit(
                            bloc,
                            "commitment_released",
                            member_id=member.id,
                            reason="not_allocated",
                            simulated=True,
                        )
                transition(bloc, "SETTLED")
                emit(
                    bloc,
                    "cleared",
                    allocations=[a.model_dump(mode="json") for a in latest.allocations],
                    below_clearing=len(latest.unserved),
                    simulated=True,
                )
            persist()
    except (asyncio.CancelledError, Exception) as exc:
        if bloc.status == "NEGOTIATING":
            reason = (
                "Negotiation timed out. All simulated commitments released."
                if isinstance(exc, TimeoutError)
                else (
                    "Negotiation interrupted or provider failed. "
                    "All simulated commitments released."
                )
            )
            terminal_failure(bloc, reason)
            persist()
        if isinstance(exc, asyncio.CancelledError):
            raise
