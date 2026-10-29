"""Scan contracts, image validation and deterministic money arithmetic."""

import io
import warnings
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from maxx.guardrails import Plain
from maxx.price_search import official_store

MAX_UPLOAD = 8 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 16_000_000


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Item(Contract):
    title: str | None = Field(default=None, max_length=300)
    brand: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    variant: str | None = Field(default=None, max_length=80)
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    merchant: str | None = Field(default=None, max_length=120)
    qty: int = Field(default=1, ge=1, le=1000)
    confidence: float = Field(default=0, ge=0, le=1)
    visible_text: str = Field(default="", max_length=4000)


# Constraints sit on the str branch only: on `str | None` itself, an explicit null raises TypeError.
Name = Annotated[Annotated[str, Plain, Field(max_length=80)] | None, Field(default=None)]


class VisionItem(Item):
    """What the vision model may return: USD or nothing, and names with no links or instructions.
    visible_text is the screenshot's own words, so it is checked after the call instead."""

    title: Annotated[str, Plain, Field(max_length=300)] | None = None
    brand: Name
    model: Name
    variant: Name
    currency: Literal["USD"] | None = None
    merchant: Annotated[str, Plain, Field(max_length=120)] | None = None


class Identity(Contract):
    """The normaliser's whole answer. It cannot touch price, currency, merchant or anything else."""

    brand: Name
    model: Name
    variant: Name


class PriceRow(Contract):
    title: str = Field(max_length=200)
    url: HttpUrl
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    shipping: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    same_item: bool = False
    in_stock: bool = False
    evidence: str = Field(default="", max_length=300)


class Score(Contract):
    value: int | None
    best: Decimal | None
    price_gap: Decimal
    ownership_penalty: int
    bloc_bonus: int = 0
    low_confidence: bool


class Move(Contract):
    primary: Literal["CHEAPER", "WAIT", "SKIP", "JOIN_BLOC"]
    headline: Annotated[str, Plain, Field(max_length=120)]
    explanation: Annotated[str, Plain, Field(max_length=400)]


class CallRecord(Contract):
    request_id: str | None = None
    provider: str
    purpose: str
    model: str | None = None
    status: str
    tokens: dict[str, object] | None = None
    cost_usd: Decimal | None = None
    latency_ms: int
    cost_status: str = "unmeasured"
    rate_date: str | None = None
    guard: list[str] | None = None


class ScanError(Contract):
    code: str
    message: str
    request_id: str


class ScanResult(Contract):
    request_id: str
    mode: Literal["live", "fixture"]
    item: Item
    rows: list[PriceRow]
    score: Score
    recommendation: Move
    warnings: list[str]
    latency_ms: int
    calls: list[CallRecord]
    open_bloc_id: str | None = None


def validate_image(data: bytes, mime: str) -> str:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError("Choose a non-empty screenshot up to 8 MB.")
    formats = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
    if mime not in formats.values():
        raise ValueError("Use PNG, JPG or WebP.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                actual = formats.get(image.format)
                if actual != mime or image.width * image.height > 16_000_000:
                    raise ValueError("Image type mismatch or image exceeds 16 megapixels.")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except Exception as exc:
        raise ValueError(
            "Cannot read this image. Use a valid PNG, JPG or WebP under 16 megapixels."
        ) from exc
    return mime


def trusted_rows(rows: list[PriceRow]) -> list[PriceRow]:
    """Offers for this item that are in stock with known shipping: the only ones scored."""
    return [r for r in rows if r.same_item and r.in_stock and r.shipping is not None]


def official_only(rows: list[PriceRow], brand: str | None) -> bool:
    """True when the maker's own store is the single store that confirms an offer."""
    trusted = trusted_rows(rows)
    return len(trusted) == 1 and official_store(str(trusted[0].url), brand)


def money_score(
    price: Decimal | None,
    rows: list[PriceRow],
    owns: bool,
    open_bloc_target: Decimal | None = None,
    brand: str | None = None,
) -> Score:
    trusted = trusted_rows(rows)
    best = min((r.price + r.shipping for r in trusted), default=None)
    bonus = (
        15 if price is not None and open_bloc_target is not None and open_bloc_target < price else 0
    )
    gap = Decimal(0)
    value = None
    if price is not None and best is not None:
        gap = max(Decimal(0), min((price - best) / price, Decimal(".4"))) / Decimal(".4")
        value = int(
            (max(Decimal(0), 100 - 70 * gap - 15 * owns - bonus)).quantize(
                Decimal(1), rounding=ROUND_HALF_EVEN
            )
        )
    return Score(
        value=value,
        best=best,
        price_gap=gap,
        ownership_penalty=15 * owns,
        bloc_bonus=bonus,
        # Two stores must agree, or the maker's own store must confirm the offer.
        low_confidence=len(trusted) < 2 and not official_only(rows, brand),
    )


# What each scored move means for the shopper, in words, for the model that writes the verdict.
# It is told the direction because it may not see numbers: "CHEAPER" once came back as "This
# option costs less than others tracked" when the shopper's own price was the higher one.
MEANINGS = {
    "CHEAPER": "Another store sells the same item for less than the price in the shopper's "
    "screenshot, including known shipping. The shopper should check that listing first.",
    "WAIT": "No cheaper offer for the same item was found. The price in the shopper's screenshot "
    "is competitive.",
    "JOIN_BLOC": "An open group deal for this item has a lower target price than the shopper's "
    "screenshot. Joining is optional and their maximum stays their limit.",
}


def template_move(item: Item, score: Score, rows: list[PriceRow] = ()) -> Move:
    if item.price is None or score.best is None or score.low_confidence:
        # No score yet, but lower prices for the same item are still worth saying, with what is
        # unconfirmed. The listings themselves are shown below the verdict.
        below = sorted(
            (r for r in rows if r.same_item and item.price is not None and r.price < item.price),
            key=lambda r: r.price + (r.shipping or 0),
        )
        if below:
            unknown = any(r.shipping is None for r in below)
            low = below[0].price + (below[0].shipping or 0)
            if len(below) == 1:
                basis = "before shipping" if unknown else "delivered"
                found = (
                    f"One store lists this item at ${low:.2f} {basis}, "
                    f"below your ${item.price:.2f}."
                )
            else:
                high = below[-1].price + (below[-1].shipping or 0)
                found = (
                    f"{len(below)} stores list this item for less: ${low:.2f} to ${high:.2f}, "
                    f"against your ${item.price:.2f}."
                    + (" Shipping is not known for all of them." if unknown else "")
                )
            return Move(
                primary="WAIT",
                headline="Seen for less elsewhere.",
                explanation=found
                + " Fewer than two stores confirm stock and shipping, so there is no score yet. "
                "Check the listings below before buying.",
            )
        return Move(
            primary="WAIT",
            headline="Check the details before buying.",
            explanation=(
                "There is not enough comparable price evidence for a confident recommendation."
            ),
        )
    if score.bloc_bonus:
        return Move(
            primary="JOIN_BLOC",
            headline="Explore the matching group deal.",
            explanation=(
                "An open Bloc has a lower reference target. "
                "Your maximum remains your limit; a deal is not guaranteed."
            ),
        )
    if score.best < item.price:
        saving = item.price - score.best
        return Move(
            primary="CHEAPER",
            headline="Check the cheaper listing.",
            explanation=(
                f"You could save ${saving:.2f} including known shipping. "
                "Confirm the price and variant on the source page."
            ),
        )
    return Move(
        primary="WAIT",
        headline="Your price looks competitive.",
        explanation=(
            "No cheaper comparable listing was found. Check delivery and returns before buying."
        ),
    )
