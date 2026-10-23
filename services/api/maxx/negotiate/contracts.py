"""Typed auction/state contracts. Seller private fields never enter public views."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from maxx.scan import PriceRow

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Status = Literal["FORMING", "OPEN", "NEGOTIATING", "SETTLED", "FAILED"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Member(Contract):
    id: str
    user_id: str
    max_price: Money
    joined_order: int = Field(ge=0)
    status: Literal["HELD", "LEFT", "WIN", "BELOW_CLEARING", "RELEASED"] = "HELD"
    seller_id: str | None = None
    final_price: Money | None = None


class Offer(Contract):
    seller_id: str
    price: Money
    max_qty: int = Field(ge=0, le=100000)


class Allocation(Contract):
    member_id: str
    seller_id: str
    price: Money


class Clearing(Contract):
    allocations: list[Allocation] = Field(default_factory=list)
    unserved: list[str] = Field(default_factory=list)


class Seller(Contract):
    id: str
    floor: Money
    opening_price: Money
    stock: int = Field(ge=0, le=100000)
    style: str = "Prefer volume without selling below your floor."
    withdraw_round: int | None = None
    # Set for verified sellers who joined through onboarding; None for the simulated ones.
    account_id: str | None = None
    # Per-round price concession for a real seller's auto-negotiating agent, as a fraction.
    concession: Decimal | None = Field(default=None, gt=0, lt=Decimal("0.5"))


class Event(Contract):
    id: int
    type: str
    data: dict = Field(default_factory=dict)


class BlocView(Contract):
    generation: int = Field(default=0, ge=0)
    id: str
    title: str
    product_key: str
    typical_price: Money
    target_price: Money | None
    closes_at: int = 0
    committed_total: Decimal = Decimal(0)
    target_reason: str = "No trusted price history yet."
    market_mode: Literal["fixture", "live", "unavailable"] = "unavailable"
    market_checked_at: int | None = None
    market_expires_at: int = 0
    market_rows: list[PriceRow] = Field(default_factory=list)
    status: Status = "FORMING"
    mode: Literal["fixture", "live"] = "fixture"
    scenario: Literal["success", "failure", "flaky"] = "success"
    revision: int = 0
    members: list[Member] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    round: int = 0
    outcome: Clearing | None = None
    failure_reason: str | None = None
    calls: list[dict] = Field(default_factory=list)
    viewer_is_owner: bool = False


class Bloc(BlocView):
    sellers: list[Seller] = Field(default_factory=list)
    owner_id: str | None = None

    def public_base(self) -> dict:
        """The redacted view as plain JSON data, shown to someone who is not in this Bloc.
        Seller private fields and account ids never appear: members are opaque ids."""
        value = self.model_dump(mode="json", exclude={"sellers", "owner_id"})
        for member in value["members"]:
            member["user_id"] = member["id"]
        value["viewer_is_owner"] = False
        active = [m for m in self.members if m.status == "HELD"]
        value["committed_total"] = str(sum((m.max_price for m in active), Decimal(0)))
        if self.target_price is not None:
            eligible = sum(m.max_price >= self.target_price for m in active)
            value["target_reason"] = (
                f"Median of trusted independent delivered USD prices: ${self.target_price:.2f}. "
                f"{eligible} of {len(active)} active buyers can afford this target. "
                "A reference target, not a guaranteed negotiated price."
            )
        return value

    def viewer_positions(self, viewer_id: str | None) -> list[int]:
        if not viewer_id:
            return []
        return [i for i, m in enumerate(self.members) if m.user_id == viewer_id]

    def public(self, viewer_id: str | None = None) -> BlocView:
        """Redacted view. Account ids never leave the server: the viewer's own membership is
        marked "me" and everyone else is shown by their opaque membership id."""
        value = self.public_base()
        for i in self.viewer_positions(viewer_id):
            value["members"][i]["user_id"] = "me"
        value["viewer_is_owner"] = bool(viewer_id and self.owner_id == viewer_id)
        return BlocView.model_validate(value)
