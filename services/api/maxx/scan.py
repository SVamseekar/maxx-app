"""Scan contracts, image validation and deterministic money arithmetic."""

import io
import warnings
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from maxx.guardrails import Plain

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


Name = Annotated[str | None, Plain, Field(default=None, max_length=80)]


class VisionItem(Item):
    """What the vision model may return: USD or nothing, and names with no links or instructions.
    visible_text is the screenshot's own words, so it is checked after the call instead."""

    title: Annotated[str | None, Plain, Field(default=None, max_length=300)]
    brand: Name
    model: Name
    variant: Name
    currency: Literal["USD"] | None = None
    merchant: Annotated[str | None, Plain, Field(default=None, max_length=120)]


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


def money_score(
    price: Decimal | None, rows: list[PriceRow], owns: bool, open_bloc_target: Decimal | None = None
) -> Score:
    trusted = [r for r in rows if r.same_item and r.in_stock and r.shipping is not None]
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
        low_confidence=len(trusted) < 2,
    )


def template_move(item: Item, score: Score) -> Move:
    if item.price is None or score.best is None or score.low_confidence:
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
