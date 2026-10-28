"""Catalogue candidates with hard variant exclusions and explicit uncertainty."""

import math
import re
from difflib import SequenceMatcher

import httpx2 as httpx
from pydantic import Field

from maxx.config import settings
from maxx.providers import ProviderError, request
from maxx.scan import Contract, Item


def words(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


class Product(Contract):
    product_key: str
    title: str
    brand: str
    model: str
    variant: str


# Curated identity catalogue, not a price feed; each colour/storage is a separate SKU.
MODELS = [
    ("Aurora", "Q5"),  # made-up brand of the demo's sample screenshot (no third-party mark)
    ("Sony", "WH-1000XM5"),
    ("Sony", "WH-1000XM4"),
    ("Sony", "WF-1000XM5"),
    ("Bose", "QuietComfort Ultra"),
    ("Bose", "QuietComfort"),
    ("Apple", "AirPods Max"),
    ("Beats", "Studio Pro"),
    ("Beats", "Solo 4"),
    ("JBL", "Tune 770NC"),
    ("JBL", "Live 770NC"),
    ("Sennheiser", "Momentum 4"),
    ("Sennheiser", "Accentum"),
    ("Anker", "Soundcore Q45"),
    ("Anker", "Soundcore Q30"),
    ("Marshall", "Major IV"),
    ("Marshall", "Major V"),
    ("Google", "Pixel Buds Pro"),
    ("Samsung", "Galaxy Buds2 Pro"),
    ("Samsung", "Galaxy Buds3 Pro"),
    ("Nothing", "Ear"),
    ("OnePlus", "Buds Pro 2"),
    ("Jabra", "Elite 8 Active"),
    ("Jabra", "Elite 10"),
    ("Skullcandy", "Crusher Evo"),
    ("Skullcandy", "Hesh ANC"),
]
CATALOG = [
    Product(
        product_key=f"{brand.lower()}-{words(model)}-{variant.lower()}",
        title=f"{brand} {model} {variant}",
        brand=brand,
        model=model,
        variant=variant,
    )
    for brand, model in MODELS
    for variant in ("Black", "Silver")
]


class Candidate(Product):
    confidence: float = Field(ge=0, le=1)
    reason: str


class MatchResult(Contract):
    mode: str = "fixture"
    method: str = "catalogue rules"
    confidence: float = 0
    requires_confirmation: bool = True
    candidates: list[Candidate] = Field(default_factory=list)
    calls: list[dict] = Field(default_factory=list)


def match_item(item: Item, similarities: list[float] | None = None) -> MatchResult:
    text = words(item.title or "")
    candidates = []
    title_tokens = re.findall(r"[a-z0-9]+", (item.title or "").casefold())
    title_brands = {words(p.brand) for p in CATALOG if p.brand.casefold() in title_tokens}

    # Reject known explicit variant contradictions even when embeddings prefer that SKU.
    variant = words(item.variant or "")
    colours = [
        v.lower()
        for v in ("Black", "Silver", "White", "Blue", "Red")
        if v.lower() in (item.title or "").lower().split()
    ]
    for i, product in enumerate(CATALOG):
        if variant and variant != words(product.variant):
            continue
        if colours and product.variant.lower() not in colours:
            continue
        if title_brands and words(product.brand) not in title_brands:
            continue
        if item.brand and words(item.brand) != words(product.brand):
            continue
        if item.model and words(item.model) != words(product.model):
            continue
        exact = text == words(product.title) or (
            words(item.model or "") == words(product.model)
            and variant == words(product.variant)
            and words(product.brand) in text
            and words(product.model) in text
            and words(product.variant) in text
        )
        score = (
            0.99
            if exact
            else min(
                0.79,
                max(
                    SequenceMatcher(None, text, words(product.title)).ratio(),
                    similarities[i] if similarities else 0,
                ),
            )
        )
        if score >= 0.35:
            candidates.append(
                Candidate(
                    **product.model_dump(),
                    confidence=round(score, 4),
                    reason="Exact model and variant"
                    if exact
                    else "Confirm exact model and variant",
                )
            )
    candidates.sort(key=lambda c: (-c.confidence, c.product_key))
    # Similarity alone cannot prove a variant. Equal candidates always need confirmation.
    confidence = candidates[0].confidence if candidates else 0
    uncertain = confidence < 0.8 or (len(candidates) > 1 and candidates[1].confidence == confidence)
    return MatchResult(
        confidence=confidence, requires_confirmation=uncertain, candidates=candidates[:3]
    )


class FixtureMatcher:
    async def match(self, item: Item):
        return match_item(item)


class NebiusMatcher:
    def __init__(self, client=None):
        self.client = client

    async def match(self, item: Item):
        if not settings.nebius_api_key:
            raise ProviderError("Live matching requires NEBIUS_API_KEY and MODEL_EMBED.")
        calls = []

        async def embed(client):
            return await request(
                client,
                "catalogue-match",
                calls,
                "nebius",
                "embed",
                settings.nebius_base_url.rstrip("/") + "/embeddings",
                {
                    "model": settings.model_embed,
                    "input": [item.title or ""] + [p.title for p in CATALOG],
                },
            )

        if self.client:
            data = await embed(self.client)
        else:
            async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
                data = await embed(client)
        try:
            rows = sorted(data["data"], key=lambda r: r["index"])
            vectors = [r["embedding"] for r in rows]
            if (
                len(vectors) != 51
                or not vectors[0]
                or any(len(v) != len(vectors[0]) for v in vectors)
            ):
                raise ValueError("Invalid dimensions")

            def cosine(v):
                numerator = sum(a * b for a, b in zip(vectors[0], v, strict=True))
                denominator = math.sqrt(sum(a * a for a in vectors[0]) * sum(a * a for a in v))
                value = numerator / denominator if denominator else 0
                if not math.isfinite(value):
                    raise ValueError("Non-finite embedding")
                return value

            result = match_item(item, [cosine(v) for v in vectors[1:]])
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise ProviderError("Invalid embedding response.") from exc
        result.mode, result.method, result.calls = (
            "live",
            "Nebius embeddings + variant rules",
            calls,
        )
        return result


def get_matcher():
    if settings.match_mode == "fixture":
        return FixtureMatcher()
    if settings.match_mode == "live":
        return NebiusMatcher()
    raise ProviderError("MATCH_MODE must be fixture or live.")
