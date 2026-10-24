"""Decimal estimates from explicitly configured per-million-token rates."""

from datetime import date
from decimal import Decimal, InvalidOperation


def calculate_cost(model, usage, rates, embedding=False):
    rate = rates.get(model) if isinstance(rates, dict) else None
    if not isinstance(rate, dict) or not rate or not usage or not rate.get("effective_date"):
        return None
    try:
        date.fromisoformat(rate["effective_date"])
    except (ValueError, TypeError):
        return None
    inputs = usage.get("prompt_tokens", usage.get("input_tokens"))
    outputs = usage.get("completion_tokens", usage.get("output_tokens", 0 if embedding else None))
    if type(inputs) is not int or type(outputs) is not int or inputs < 0 or outputs < 0:
        return None
    try:
        a, b = Decimal(rate["input_usd_per_million"]), Decimal(rate["output_usd_per_million"])
        if not a.is_finite() or not b.is_finite() or a < 0 or b < 0:
            return None
        return ((inputs * a + outputs * b) / Decimal(1000000)).quantize(Decimal(".00000001"))
    except (KeyError, InvalidOperation, TypeError):
        return None


def worst_case_usd(model, chars, images, max_tokens, rates) -> Decimal | None:
    """The most a call can cost: its input at a cautious 3 characters per token, its images at
    the model's per-image token count, and every allowed output token. None when unpriced."""
    rate = rates.get(model) if isinstance(rates, dict) else None
    if not isinstance(rate, dict) or not rate.get("effective_date"):
        return None
    try:
        a, b = Decimal(rate["input_usd_per_million"]), Decimal(rate["output_usd_per_million"])
        per_image = int(rate.get("image_tokens", 0 if not images else 2048))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return None
    if not a.is_finite() or not b.is_finite() or a < 0 or b < 0:
        return None
    inputs = -(-chars // 3) + images * per_image
    return (inputs * a + max_tokens * b) / Decimal(1000000)
