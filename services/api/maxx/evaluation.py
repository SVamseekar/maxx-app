"""Evaluation metrics with explicit denominators and independently checked invariants."""

from collections import Counter


def matching_metrics(expected, results):
    automatic = [
        (truth, key)
        for truth, (key, uncertain) in zip(expected, results, strict=True)
        if not uncertain
    ]
    correct = sum(truth is not None and truth == key for truth, key in automatic)
    return {
        "automatic": len(automatic),
        "correct": correct,
        "precision": correct / len(automatic) if automatic else None,
        "confirmation_required": sum(uncertain for _, uncertain in results),
    }


def invariant_violations(members, sellers, result):
    buyers = {m.id: m for m in members}
    sources = {s.id: s for s in sellers}
    violations = []
    counts = Counter(a.seller_id for a in result.allocations)
    ids = [a.member_id for a in result.allocations]
    if len(set(ids)) != len(ids):
        violations.append("duplicate_allocation")
    for allocation in result.allocations:
        if allocation.member_id not in buyers or allocation.seller_id not in sources:
            violations.append("unknown_identity")
            continue
        if allocation.price > buyers[allocation.member_id].max_price:
            violations.append("above_maximum")
        if allocation.price < sources[allocation.seller_id].floor:
            violations.append("below_floor")
    if any(counts[s.id] > s.stock for s in sellers):
        violations.append("over_capacity")
    if set(ids) & set(result.unserved) or set(ids) | set(result.unserved) != set(buyers):
        violations.append("allocation_conservation")
    return violations
