"""The AI spending cap: a database ledger that holds each paid call's worst-case cost before the
call and settles it to the measured cost after.

Every limit that applies to a call (the total, today, the anonymous pool, one address, one person,
Tavily credits) is a row in `ai_budget`. A hold is one conditional UPDATE per row in a single
transaction: `spent + reserved + amount <= cap`. PostgreSQL re-checks that condition after waiting
for a concurrent writer's row lock, so two requests near a cap can never both pass. A hold that is
never settled (a crash) expires as spent: a hard cap must not leak real spend.
"""

import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, select, update

from maxx import audit, schema, storage
from maxx.config import settings
from maxx.providers import BudgetExceeded

MICROS = Decimal(1000000)
PAUSED = "Live AI is paused: an operator switched it off. The rest of Maxx keeps working."


@dataclass(frozen=True)
class Payer:
    kind: str  # user | anonymous | system
    key: str = ""  # user id, a keyed hash of the address, or what the system is doing
    premium: bool = False
    owner: str = ""  # for a negotiation: the person who created the Bloc


@dataclass
class Scope:
    payer: Payer
    max_calls: int
    calls: int = 0


_scope: ContextVar[Scope | None] = ContextVar("ai_payer", default=None)


@contextmanager
def payer_scope(payer: Payer, max_calls: int):
    """Charge every paid call inside this block to `payer`, and allow at most `max_calls`."""
    token = _scope.set(Scope(payer, max_calls))
    try:
        yield _scope.get()
    finally:
        _scope.reset(token)


def negotiation_worst_ok(owner: str = "", now: float | None = None):
    """Refuse to start a live negotiation that today's budget could not finish."""
    if _paused():
        raise BudgetExceeded(PAUSED)
    need = Decimal(settings.ai_negotiation_worst_usd)
    if remaining_for(Payer("system", "negotiation:check", owner=owner), now) < need:
        raise BudgetExceeded(
            "Live AI is paused: not enough of today's AI budget is left to run a negotiation. "
            "It resets at 00:00 UTC."
        )


def payer_for(user, address: str) -> Payer:
    """The signed-in person, or the anonymous pool keyed by a hash of the client address."""
    if user:
        from maxx.money import subscriptions

        return Payer("user", user.id, premium=subscriptions.is_premium(user.id))
    from maxx.secrets import keyed_hash

    return Payer("anonymous", keyed_hash(address, "ai-budget-address"))


def current() -> Scope:
    """The payer of the call being made. Every entry point that can reach a paid provider opens a
    payer_scope; a call outside one is refused rather than charged to nobody."""
    scope = _scope.get()
    if scope is None:
        raise BudgetExceeded("Live AI is paused: this call has no payer, so it was not made.")
    return scope


@dataclass(frozen=True)
class Hold:
    id: str
    buckets: tuple[tuple[str, str], ...]
    amount: int


def micros(usd: Decimal) -> int:
    return int((Decimal(usd) * MICROS).to_integral_value(rounding="ROUND_CEILING"))


def _usd(value: str) -> int:
    return micros(Decimal(value))


def _day(now: float) -> str:
    return datetime.fromtimestamp(now, UTC).date().isoformat()


def _limits(payer: Payer, now: float) -> list[tuple[str, str, int, str]]:
    day = _day(now)
    total = ("total", "all", _usd(settings.ai_budget_usd), "the total AI budget is used up.")
    if payer.key.startswith("verify:"):
        # An operator's live check: its own small cap, outside the day kept for people.
        return [
            total,
            (
                payer.key,
                "all",
                _usd(settings.ai_verify_budget_usd),
                "the live check's budget is used up.",
            ),
        ]
    limits = [
        total,
        (
            "day",
            day,
            _usd(settings.ai_daily_budget_usd),
            "today's AI budget is used up. It resets at 00:00 UTC.",
        ),
    ]
    negotiation_share = _usd(settings.ai_negotiation_daily_budget_usd)
    today = "today's AI budget is used up. It resets at 00:00 UTC."
    if payer.kind in {"user", "anonymous"}:
        # People's own calls can never eat the part of the day kept for negotiations.
        people = max(0, _usd(settings.ai_daily_budget_usd) - negotiation_share)
        limits.append(("people_day", day, people, today))
    elif payer.key.startswith(("negotiation:", "market:")):
        limits.append(
            (
                "negotiation_day",
                day,
                negotiation_share,
                "today's AI budget for negotiations is used up. It resets at 00:00 UTC.",
            )
        )
        if payer.owner:
            # One person's Blocs cannot use up the share every other Bloc relies on.
            limits.append(
                (
                    "owner_negotiation_day:" + payer.owner,
                    day,
                    _usd(settings.ai_owner_negotiation_daily_budget_usd),
                    "today's AI allowance for negotiations of Blocs you started is used up. It "
                    "resets at 00:00 UTC.",
                )
            )
    if payer.kind == "anonymous":
        visitors = (
            "today's allowance for visitors who are not signed in is used up. Sign in to keep "
            "going, or try again after 00:00 UTC."
        )
        limits += [
            ("anon_day", day, _usd(settings.ai_anonymous_daily_budget_usd), visitors),
            ("ip_day:" + payer.key, day, _usd(settings.ai_address_daily_budget_usd), visitors),
        ]
    elif payer.kind == "user":
        cap = (
            settings.ai_premium_user_daily_budget_usd
            if payer.premium
            else settings.ai_user_daily_budget_usd
        )
        limits.append(
            (
                "user_day:" + payer.key,
                day,
                _usd(cap),
                "your AI allowance for today is used up. It resets at 00:00 UTC.",
            )
        )
    return limits


def _paused() -> bool:
    return settings.ai_paused or audit.flag("ai_paused") == "1"


def _gate(scope: Scope):
    """Checks that hold for every paid call, whatever the entry point."""
    if _paused():
        raise BudgetExceeded(PAUSED)
    if scope.payer.kind == "anonymous" and not settings.ai_anonymous_live:
        raise BudgetExceeded("Live AI is paused: sign in to use live AI.")
    _count_call(scope)


def _count_call(scope: Scope):
    scope.calls += 1
    if scope.calls > scope.max_calls:
        raise BudgetExceeded(
            f"Live AI is paused: this request reached its limit of {scope.max_calls} model calls."
        )


def _hold(request_id, role, limits, amount, now) -> Hold:
    """Hold `amount` in every limit at once, or in none."""
    sweep(now)
    limits = sorted(limits)  # one lock order everywhere, so concurrent holds cannot deadlock
    table = schema.ai_budget
    engine = storage.get_store().engine
    with engine.begin() as db:
        for scope, period, _cap, _message in limits:
            exists = db.execute(
                select(table.c.scope).where(table.c.scope == scope, table.c.period == period)
            ).first()
            if not exists:
                _insert_ignore(db, scope, period)
        for scope, period, cap, message in limits:
            done = db.execute(
                update(table)
                .where(
                    table.c.scope == scope,
                    table.c.period == period,
                    table.c.spent_micros + table.c.reserved_micros + amount <= cap,
                )
                .values(reserved_micros=table.c.reserved_micros + amount)
            )
            if done.rowcount != 1:
                raise BudgetExceeded("Live AI is paused: " + message)  # rolls back every hold
        hold = Hold(str(uuid.uuid4()), tuple((s, p) for s, p, _c, _m in limits), amount)
        db.execute(
            schema.ai_reservations.insert().values(
                id=hold.id,
                request_id=str(request_id)[:100],
                role=role[:30],
                buckets=json.dumps(hold.buckets),
                amount_micros=amount,
                status="held",
                created_at=int(now),
                expires_at=int(now + settings.provider_timeout + 60),
            )
        )
    return hold


def _insert_ignore(db, scope, period):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = sqlite_insert if db.dialect.name == "sqlite" else pg_insert
    db.execute(
        insert(schema.ai_budget)
        .values(scope=scope, period=period, spent_micros=0, reserved_micros=0)
        .on_conflict_do_nothing()
    )


def reserve(request_id, role: str, usd: Decimal, now: float | None = None) -> Hold:
    """Hold a model call's worst-case cost against every limit for the current payer."""
    now = time.time() if now is None else now
    scope = current()
    _gate(scope)
    return _hold(request_id, role, _limits(scope.payer, now), micros(usd), now)


def reserve_credits(request_id, credits: int, now: float | None = None) -> Hold:
    """Hold Tavily credits (counted as whole credits, not dollars) against the month and day."""
    now = time.time() if now is None else now
    scope = current()
    _gate(scope)
    month = _day(now)[:7]
    limits = [
        (
            "tavily_month",
            month,
            settings.tavily_monthly_credits * int(MICROS),
            "this month's web search credits are used up.",
        ),
        (
            "tavily_day",
            _day(now),
            settings.tavily_daily_credits * int(MICROS),
            "today's web search allowance is used up. It resets at 00:00 UTC.",
        ),
    ]
    return _hold(request_id, "search", limits, credits * int(MICROS), now)


def _release(db, hold_id, buckets, amount, actual, status) -> bool:
    done = db.execute(
        update(schema.ai_reservations)
        .where(schema.ai_reservations.c.id == hold_id, schema.ai_reservations.c.status == "held")
        .values(status=status, actual_micros=actual)
    )
    if done.rowcount != 1:
        return False  # already settled or expired
    table = schema.ai_budget
    for scope, period in sorted(tuple(b) for b in buckets):
        db.execute(
            update(table)
            .where(table.c.scope == scope, table.c.period == period)
            .values(
                reserved_micros=table.c.reserved_micros - amount,
                spent_micros=table.c.spent_micros + actual,
            )
        )
    return True


def settle(hold: Hold, actual_usd: Decimal | None, now: float | None = None):
    """Replace a hold with the measured cost, in the periods it was held in. Unknown cost (no
    usage in the reply) is charged in full."""
    actual = hold.amount if actual_usd is None else micros(actual_usd)
    with storage.get_store().engine.begin() as db:
        _release(db, hold.id, hold.buckets, hold.amount, actual, "settled")


def sweep(now: float | None = None):
    """Expire holds whose call never settled, counting them as spent."""
    now = time.time() if now is None else now
    table = schema.ai_reservations
    with storage.get_store().engine.begin() as db:
        stale = db.execute(
            select(table.c.id, table.c.buckets, table.c.amount_micros).where(
                and_(table.c.status == "held", table.c.expires_at < int(now))
            )
        ).all()
        for hold_id, buckets, amount in stale:
            _release(db, hold_id, json.loads(buckets), amount, amount, "expired")


def _bucket(db, scope, period, cap) -> dict:
    row = db.execute(
        select(schema.ai_budget.c.spent_micros, schema.ai_budget.c.reserved_micros).where(
            schema.ai_budget.c.scope == scope, schema.ai_budget.c.period == period
        )
    ).first()
    spent, reserved = row if row else (0, 0)

    def usd(value):
        return str((Decimal(value) / MICROS).quantize(Decimal(".000001")))

    return {
        "cap_usd": usd(cap),
        "spent_usd": usd(spent),
        "reserved_usd": usd(reserved),
        "remaining_usd": usd(max(0, cap - spent - reserved)),
    }


def paused() -> bool:
    return _paused()


def status(now: float | None = None) -> dict:
    """The operator's view: every shared limit, for today and this month."""
    now = time.time() if now is None else now
    sweep(now)
    day = _day(now)
    with storage.get_store().engine.connect() as db:
        view = {
            name: _bucket(db, scope, period, cap)
            for name, scope, period, cap in [
                ("total", "total", "all", _usd(settings.ai_budget_usd)),
                ("day", "day", day, _usd(settings.ai_daily_budget_usd)),
                ("anonymous_day", "anon_day", day, _usd(settings.ai_anonymous_daily_budget_usd)),
                (
                    "negotiation_day",
                    "negotiation_day",
                    day,
                    _usd(settings.ai_negotiation_daily_budget_usd),
                ),
            ]
        }
        for name, scope, period, credits in [
            ("tavily_month", "tavily_month", day[:7], settings.tavily_monthly_credits),
            ("tavily_day", "tavily_day", day, settings.tavily_daily_credits),
        ]:
            dollars = _bucket(db, scope, period, credits * int(MICROS))
            view[name] = {k.replace("_usd", "_credits"): v for k, v in dollars.items()}
    view["paused"] = _paused()
    return view


def remaining_for(payer: Payer, now: float | None = None) -> Decimal:
    """What `payer` may still spend today: the tightest of the limits that apply to them."""
    now = time.time() if now is None else now
    with storage.get_store().engine.connect() as db:
        return min(
            Decimal(_bucket(db, scope, period, cap)["remaining_usd"])
            for scope, period, cap, _message in _limits(payer, now)
        )
