from maxx.evaluation import invariant_violations, matching_metrics
from maxx.negotiate.contracts import Allocation, Clearing, Member, Seller


def test_evaluation_detects_wrong_matches_and_unsafe_allocations():
    assert matching_metrics(["sku", None], [("wrong", False), ("wrong", True)]) == {
        "automatic": 1,
        "correct": 0,
        "precision": 0.0,
        "confirmation_required": 1,
    }
    member = Member(id="a", user_id="a", max_price="10", joined_order=0)
    seller = Seller(id="s", floor="12", opening_price="12", stock=0)
    clearing = Clearing(allocations=[Allocation(member_id="a", seller_id="s", price="11")])
    violations = invariant_violations([member], [seller], clearing)
    assert {"above_maximum", "below_floor", "over_capacity"} <= set(violations)
