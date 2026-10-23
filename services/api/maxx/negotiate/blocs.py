import time
import uuid
from decimal import Decimal

from maxx.config import settings
from maxx.market import apply_market, fixture_rows
from maxx.negotiate.contracts import Bloc, Event, Member, Seller, Status

TRANSITIONS = {
    "FORMING": {"OPEN"},
    "OPEN": {"NEGOTIATING", "FAILED"},  # FAILED from OPEN: an administrator took a listing down
    "NEGOTIATING": {"SETTLED", "FAILED"},
    "SETTLED": set(),
    "FAILED": set(),
}


def emit(bloc: Bloc, kind: str, **data) -> Event:
    event = Event(id=len(bloc.events) + 1, type=kind, data=data)
    bloc.events.append(event)
    return event


def transition(bloc: Bloc, next_status: Status):
    if next_status not in TRANSITIONS[bloc.status]:
        raise ValueError(f"Cannot move {bloc.status} to {next_status}.")
    bloc.status = next_status
    emit(bloc, "state_changed", status=next_status)


def add_member(bloc: Bloc, user_id: str, max_price: str) -> Member:
    if bloc.status != "OPEN" or (bloc.closes_at and bloc.closes_at <= int(time.time())):
        raise ValueError("Joining is available only while the Bloc is open.")
    price = Member(id="validation", user_id=user_id, max_price=max_price, joined_order=0).max_price
    if not bloc.typical_price / 2 <= price <= bloc.typical_price:
        raise ValueError("Your maximum must be between 50% and 100% of the typical price.")
    existing = next((m for m in bloc.members if m.user_id == user_id and m.status == "HELD"), None)
    if existing:
        if existing.max_price != price:
            raise ValueError("Leave and rejoin to change your maximum.")
        return existing
    if len(bloc.members) >= 2000:
        raise ValueError("This demo Bloc is full.")
    member = Member(
        id=str(uuid.uuid4()), user_id=user_id, max_price=price, joined_order=len(bloc.members)
    )
    bloc.members.append(member)
    emit(bloc, "member_joined", member_id=member.id, max_price=str(price), simulated=True)
    return member


def leave_member(bloc: Bloc, user_id: str):
    if bloc.status != "OPEN":
        raise ValueError("Leaving is available only before negotiation starts.")
    member = next((m for m in bloc.members if m.user_id == user_id and m.status == "HELD"), None)
    if member:
        member.status = "LEFT"
        emit(bloc, "commitment_released", member_id=member.id, reason="left", simulated=True)


def make_bloc(
    id: str,
    title: str,
    typical: Decimal,
    mode="fixture",
    scenario="success",
    personas: int | None = None,
    origin: str = "demand",
) -> Bloc:
    """A new open Bloc. `personas` is how many simulated sellers sit at the table (all eight by
    default when SIMULATED_SELLERS is on, none when it is off)."""
    count = (8 if settings.simulated_sellers else 0) if personas is None else personas
    b = Bloc(
        origin=origin,
        generation=time.time_ns() // 1000,
        closes_at=int(time.time()) + settings.bloc_open_seconds,
        id=id,
        title=title,
        product_key=title.casefold(),
        typical_price=typical,
        target_price=None,
        mode=mode,
        scenario=scenario,
    )
    personas = [
        "Volume wholesaler: prefer more units at modest margin.",
        "Premium retailer: protect margin and concede gradually.",
        "Inventory liquidator: clear stock quickly within your floor.",
        "Small boutique: offer limited quantities, protect service margin.",
        "Competitive reseller: improve offers when you lose allocation.",
        "Patient distributor: make measured concessions over rounds.",
        "Seasonal outlet: prioritize turnover and larger group demand.",
        "Risk-averse seller: retain inventory unless demand justifies the offer.",
    ]
    if mode == "fixture":
        apply_market(b, fixture_rows(title, typical), "fixture", int(time.time()))
    for i in range(min(8, count)):
        b.sellers.append(
            Seller(
                id=chr(65 + i),
                stock=2,
                style=personas[i],
                floor=(
                    typical
                    * (
                        Decimal("1.2")
                        if scenario == "failure"
                        else Decimal(".65") + Decimal(i) / 100
                    )
                ).quantize(Decimal(".01")),
                opening_price=(typical * Decimal(".85")).quantize(Decimal(".01")),
                withdraw_round=2 if scenario == "flaky" and i == 0 else None,
            )
        )
    transition(b, "OPEN")
    return b
