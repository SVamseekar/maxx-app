from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from maxx.negotiate.contracts import Member, Offer
from maxx.negotiate.engine import clear


def member(name, price, order=0):
    return Member(id=name, user_id=name, max_price=str(price), joined_order=order)


def offer(name, price, qty):
    return Offer(seller_id=name, price=str(price), max_qty=qty)


def test_priority_capacity_prices_and_deterministic_ties():
    members = [member("low", 80), member("late", 100, 2), member("early", 100, 1)]
    result = clear(members, [offer("B", 90, 1), offer("A", 85, 1)])
    assert [(a.member_id, a.seller_id, a.price) for a in result.allocations] == [
        ("early", "A", Decimal("85")),
        ("late", "B", Decimal("90")),
    ]
    assert result.unserved == ["low"]
    assert result == clear(list(reversed(members)), [offer("A", 85, 1), offer("B", 90, 1)])


def test_no_deal_empty_and_duplicates():
    assert clear([member("a", 50)], [offer("s", 60, 5)]).unserved == ["a"]
    assert clear([], []).allocations == []
    assert clear([member("a", 50)], [offer("s", 1, 0)]).allocations == []
    with pytest.raises(ValueError):
        clear([member("a", 50), member("a", 60)], [])
    with pytest.raises(ValueError):
        clear([], [offer("s", 60, 1), offer("s", 50, 1)])


@settings(max_examples=200, deadline=None, derandomize=True)
@given(
    st.lists(st.integers(1, 50000), max_size=40),
    st.lists(st.tuples(st.integers(1, 50000), st.integers(0, 20)), max_size=8),
)
def test_generated_allocation_invariants(prices, offers):
    ms = [member(str(i), Decimal(p) / 100, i) for i, p in enumerate(prices)]
    os = [offer(str(i), Decimal(p) / 100, q) for i, (p, q) in enumerate(offers)]
    result = clear(ms, os)
    by_member = {m.id: m for m in ms}
    by_seller = {o.seller_id: o for o in os}
    assert len({a.member_id for a in result.allocations}) == len(result.allocations)
    for a in result.allocations:
        assert a.price <= by_member[a.member_id].max_price
        assert a.price == by_seller[a.seller_id].price
    for o in os:
        assert sum(a.seller_id == o.seller_id for a in result.allocations) <= o.max_qty
    assert set(result.unserved) | {a.member_id for a in result.allocations} == set(by_member)
    assert not (set(result.unserved) & {a.member_id for a in result.allocations})
    assert result == clear(list(reversed(ms)), list(reversed(os)))


@settings(max_examples=200, deadline=None, derandomize=True)
@given(
    st.lists(st.integers(1, 50000), max_size=50),
    st.lists(
        st.tuples(
            st.integers(1, 50000), st.integers(1, 50000), st.integers(0, 12), st.integers(0, 30)
        ),
        min_size=1,
        max_size=8,
    ),
)
def test_random_floors_partial_fills_and_priority(prices, seller_inputs):
    from maxx.negotiate.adapters import Bid, safe_offer
    from maxx.negotiate.contracts import Seller

    sellers = [
        Seller(id=str(i), floor=Decimal(f) / 100, opening_price=Decimal(f) / 100, stock=stock)
        for i, (f, p, stock, q) in enumerate(seller_inputs)
    ]
    offers = [
        safe_offer(s, Bid(price=Decimal(p) / 100, max_qty=q))[0]
        for s, (_, p, _, q) in zip(sellers, seller_inputs, strict=True)
    ]
    members = [member(str(i), Decimal(p) / 100, i) for i, p in enumerate(prices)]
    result = clear(members, offers)
    allocated = {a.member_id for a in result.allocations}
    for seller in sellers:
        own = [a for a in result.allocations if a.seller_id == seller.id]
        assert len(own) <= seller.stock
        assert all(a.price >= seller.floor for a in own)
    for a in result.allocations:
        assert a.price <= members[int(a.member_id)].max_price
    # Independent expanded inventory oracle covers partial fills and buyer priority.
    inventory = sorted([(o.price, o.seller_id) for o in offers for _ in range(o.max_qty)])
    expected = []
    for buyer in sorted(members, key=lambda m: (-m.max_price, m.joined_order, m.id)):
        if inventory and inventory[0][0] <= buyer.max_price:
            price, seller = inventory.pop(0)
            expected.append((buyer.id, seller, price))
    assert [(a.member_id, a.seller_id, a.price) for a in result.allocations] == expected
    assert len(allocated) + len(result.unserved) == len(members)
    assert result == clear(list(reversed(members)), list(reversed(offers)))
