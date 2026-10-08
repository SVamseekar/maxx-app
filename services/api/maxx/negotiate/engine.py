"""Pure implementation of the active Nebius tech spec §5, using Decimal money."""

from maxx.negotiate.contracts import Allocation, Clearing, Member, Offer


def clear(members: list[Member], offers: list[Offer]) -> Clearing:
    if len({m.id for m in members}) != len(members):
        raise ValueError("Duplicate member IDs.")
    if len({o.seller_id for o in offers}) != len(offers):
        raise ValueError("Duplicate seller IDs.")
    ms = sorted(
        (m for m in members if m.status == "HELD"),
        key=lambda m: (-m.max_price, m.joined_order, m.id),
    )
    os = sorted(offers, key=lambda o: (o.price, o.seller_id))
    result = Clearing()
    i = 0
    for offer in os:
        qty = offer.max_qty
        while qty and i < len(ms) and ms[i].max_price >= offer.price:
            result.allocations.append(
                Allocation(member_id=ms[i].id, seller_id=offer.seller_id, price=offer.price)
            )
            qty -= 1
            i += 1
    result.unserved = [m.id for m in ms[i:]]
    return result
