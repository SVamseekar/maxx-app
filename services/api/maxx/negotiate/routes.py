import asyncio
import hashlib
import json
import logging
import time
import uuid
from decimal import Decimal
from threading import Lock
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import Field

from maxx import budget, hardening, storage
from maxx.auth import ratelimit
from maxx.auth.deps import CodedError, CurrentUser, OptionalUser, client_ip, is_admin, same_origin
from maxx.config import settings
from maxx.market import refresh_market
from maxx.matching import MatchResult, get_matcher
from maxx.negotiate.adapters import FixtureAdapter, NebiusAdapter
from maxx.negotiate.blocs import add_member, leave_member, make_bloc, transition
from maxx.negotiate.contracts import BlocView, Contract, Money
from maxx.negotiate.runner import run_negotiation, terminal_failure
from maxx.negotiate.store import BlocStore, Conflict
from maxx.negotiate.stream import event_frames
from maxx.providers import BudgetExceeded, ProviderError
from maxx.scan import Item

router = APIRouter(dependencies=[Depends(same_origin)])


class CreateBloc(Contract):
    title: str = Field(min_length=3, max_length=300)
    typical_price: Money
    confirmed_variant: bool = False
    product_key: str | None = Field(default=None, max_length=100)
    item: Item | None = None


class Join(Contract):
    max_price: Money


class Runtime:
    def __init__(self, store: BlocStore, mode="fixture", delay=None, adapter_factory=None):
        self.store, self.mode, self.delay = store, mode, delay
        self.adapter_factory = adapter_factory
        self.tasks = {}
        self.lock = asyncio.Lock()

    def seed(self, reset=False):
        seeds = []
        for scenario, count in [("success", 600), ("failure", 100), ("flaky", 100)]:
            id = "demo-" + scenario
            if not reset:
                try:
                    self.store.get(id)
                    continue
                except KeyError:
                    pass
            b = make_bloc(
                id, "Demo headphones · Black", Decimal("200"), mode=self.mode, scenario=scenario
            )
            for seller in b.sellers:
                seller.stock = max(2, count // 4)
            for i in range(count):
                add_member(b, f"seed-{scenario}-{i}", str(200 - (i % 8) * 10))
            seeds.append(b)
        if reset:
            self.store.reset_demo(seeds)
        else:
            for b in seeds:
                try:
                    self.store.create(b)
                except Conflict:
                    pass

    def recover(self):
        for b in self.store.list_by_status(["NEGOTIATING"]):
            if self.store.job_status(b.id) != "QUEUED":
                terminal_failure(
                    b, "API restarted during negotiation. All simulated commitments released."
                )
                self.store.save(b)

    async def start(self, id):
        async with self.lock:
            b = self.store.get(id)
            if b.status in {"NEGOTIATING", "SETTLED", "FAILED"}:
                return b.public()
            if b.status != "OPEN":
                raise ValueError("Bloc is not open.")
            if self.mode == "fixture":
                adapter = self.adapter_factory() if self.adapter_factory else FixtureAdapter()
            elif self.mode == "live":
                budget.negotiation_worst_ok(b.owner_id or "")
                adapter = self.adapter_factory() if self.adapter_factory else NebiusAdapter(id)
                if not self.adapter_factory:
                    await adapter.verify()
            else:
                raise ProviderError("NEGOTIATION_MODE must be fixture or live.")
            if b.origin == "demand":
                # A seller's listing or the demo tour has no comparable-price research to refresh.
                payer = budget.Payer("system", "market:" + id, owner=b.owner_id or "")
                with budget.payer_scope(payer, settings.ai_max_calls_per_scan):
                    await refresh_market(b, self.mode, adapter.calls)
            b.mode = self.mode
            from maxx.sellers import store as seller_store

            seller_store.attach(b)  # verified sellers with a standing offer join the table
            transition(b, "NEGOTIATING")
            self.store.save(b, queue=True)
            self.store.claim_job(id)
            task = asyncio.create_task(self._run(id, adapter))
            self.tasks[id] = task
            task.add_done_callback(lambda done, id=id: self.tasks.pop(id, None))
            return b.public()

    async def _run(self, id, adapter):
        await run_negotiation(self.store, id, adapter, round_delay=self.delay)
        await self.settle(id)

    async def settle(self, id):
        """Capture, void and pay out once a Bloc has finished. tick() retries failures."""
        from maxx.money import service

        if not service.enabled():
            return
        try:
            await service.settle_bloc(self.store, id)
        except Exception:  # noqa: BLE001 - settlement is resumable; never crash the worker
            logging.getLogger(__name__).exception("Settlement for %s failed; will retry.", id)

    async def housekeeping(self):
        """Work that is not tied to one Bloc: email, compliance and the sanctions list."""
        from maxx.compliance import sanctions
        from maxx.notify import service as notify
        from maxx.sellers import lifecycle

        log = logging.getLogger(__name__)
        try:
            await notify.deliver_due()
        except Exception:  # noqa: BLE001 - retried on the next pass
            log.exception("Email delivery pass failed; will retry.")
        if time.time() - getattr(self, "compliance_at", 0) >= 3600:
            self.compliance_at = time.time()
            try:
                age = sanctions.age_seconds()
                if age is None or age > 86400:
                    await sanctions.refresh()
            except Exception:  # noqa: BLE001 - a stale list is reported on the admin page
                log.warning("Sanctions list refresh failed; will retry in an hour.")
            try:
                lifecycle.sweep_compliance()
            except Exception:  # noqa: BLE001
                log.exception("Seller compliance sweep failed; will retry.")

    async def resume_settlements(self):
        from maxx.demo import tour
        from maxx.fulfilment import service as fulfilment
        from maxx.money import service

        if not service.enabled():
            return
        log = logging.getLogger(__name__)
        # Slower housekeeping: orphaned holds, shipping deadlines, payouts, cases, address purges.
        if time.time() - getattr(self, "housekeeping_at", 0) >= 20:
            self.housekeeping_at = time.time()
            try:
                await service.release_orphans(self.store)
                if tour.enabled():
                    tour.act_for_demo_buyers()
                await fulfilment.sweep()
            except Exception:  # noqa: BLE001 - retried on the next pass
                log.exception("Housekeeping failed; will retry.")
        for id in service.pending_bloc_ids(self.store):
            key = "settle-" + id
            if key in self.tasks:
                continue
            try:
                bloc = self.store.get(id)
            except KeyError:
                continue
            if service.needs_settlement(bloc):
                task = asyncio.create_task(self.settle(id))
                self.tasks[key] = task
                task.add_done_callback(lambda done, key=key: self.tasks.pop(key, None))

    async def tick(self):
        import time

        # A task can die while the database is unavailable. Release safely once it returns.
        for b in self.store.list_by_status(["NEGOTIATING"]):
            if b.id not in self.tasks and self.store.job_status(b.id) == "RUNNING":
                terminal_failure(b, "Negotiation worker interrupted. Commitments released.")
                self.store.save(b)

        # Stored queued jobs survive a crash between commit and task creation.
        for id in self.store.queued_jobs():
            if id in self.tasks or not self.store.claim_job(id):
                continue
            b = self.store.get(id)
            if b.mode != self.mode:
                terminal_failure(b, "Provider mode changed after queueing. Commitments released.")
                self.store.save(b)
                continue
            adapter = FixtureAdapter() if self.mode == "fixture" else NebiusAdapter(id)
            task = asyncio.create_task(self._run(id, adapter))
            self.tasks[id] = task
            task.add_done_callback(lambda done, id=id: self.tasks.pop(id, None))
        await self.resume_settlements()
        if time.time() - getattr(self, "mail_at", 0) >= 5:
            self.mail_at = time.time()
            await self.housekeeping()
        for id in self.store.due_to_close(int(time.time())):
            if not hasattr(self, "close_attempts"):
                self.close_attempts = {}
            if time.time() - self.close_attempts.get(id, 0) < 60:
                continue
            self.close_attempts[id] = time.time()
            try:
                await self.start(id)
            except BudgetExceeded as exc:
                if budget.paused():
                    continue  # an operator pause is temporary: close once AI is resumed
                # Out of budget: a timed close cannot wait for tomorrow while buyers' money is
                # held, so it ends now, says why, and releases every hold. Nothing is charged.
                b = self.store.get(id)
                if b.status == "OPEN":
                    terminal_failure(b, str(exc) + " Commitments released.")
                    self.store.save(b)
            except (ProviderError, ValueError, Conflict):
                continue

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


_runtime: Runtime | None = None
_runtime_lock = Lock()


def peek_runtime():
    return _runtime


def get_runtime():
    global _runtime
    # functools.lru_cache allows duplicate concurrent factory executions on cold misses.
    with _runtime_lock:
        if _runtime is None:
            store = storage.get_store()
            value = Runtime(store, mode=settings.negotiation_mode)
            value.recover()
            value.seed()
            _runtime = value
        return _runtime


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
MatcherDep = Annotated[Any, Depends(get_matcher)]


def get_bloc(runtime, id):
    try:
        return runtime.store.get(id)
    except KeyError:
        raise HTTPException(404, "Bloc not found.") from None


list_cache: dict = {}
list_cache_lock = Lock()


class BlocSummary(Contract):
    id: str
    title: str
    product_key: str
    status: str
    scenario: str
    mode: str
    target_price: Decimal | None
    typical_price: Decimal
    committed_total: Decimal
    buyers: int
    closes_at: int
    viewer_is_owner: bool = False
    viewer_joined: bool = False


@router.get("/blocs", response_model=list[BlocSummary])
def list_blocs(runtime: RuntimeDep, user: OptionalUser):
    """Light list for browsing: no members, events or market rows. Cached for about a second,
    which is invisible to people and lets a crowd share one database read."""
    viewer = user.id if user else None
    key = (id(runtime.store), viewer)
    cached = list_cache.get(key)
    if cached and time.monotonic() - cached[0] < settings.list_cache_seconds:
        return cached[1]
    rows = runtime.store.summaries(viewer)
    for row in rows:
        row["committed_total"] = row.pop("committed")
    with list_cache_lock:
        if len(list_cache) > 512:
            list_cache.clear()
        list_cache[key] = (time.monotonic(), rows)
    return rows


@router.post("/blocs", response_model=BlocView, status_code=201)
async def create_bloc(
    body: CreateBloc, runtime: RuntimeDep, matcher: MatcherDep, user: CurrentUser
):
    ratelimit.hit(f"bloc:{user.id}", settings.bloc_actions_per_hour, 3600)
    # Matching and the comparable-price search are the creator's AI calls.
    with budget.payer_scope(budget.payer_for(user, ""), settings.ai_max_calls_per_scan):
        return await _create_bloc(body, runtime, matcher, user)


async def _create_bloc(body, runtime, matcher, user):
    title = body.title.strip()
    if len(title) < 3:
        raise HTTPException(422, "Enter an exact product title.")
    key = None
    if body.product_key:
        if body.item is None:
            raise HTTPException(409, "Match the product before choosing its identity.")
        try:
            result = await asyncio.wait_for(
                matcher.match(body.item), timeout=settings.provider_timeout
            )
        except (ProviderError, TimeoutError) as exc:
            raise HTTPException(503, str(exc) or "Matching timed out.") from None
        candidate = next((c for c in result.candidates if c.product_key == body.product_key), None)
        if (
            candidate is None
            or (candidate.confidence < 0.8 or result.requires_confirmation)
            and not body.confirmed_variant
        ):
            raise HTTPException(409, "Confirm an eligible exact model and variant.")
        key, title = candidate.product_key, candidate.title
        runtime.store.record_demand(key, candidate.confidence, body.confirmed_variant, result.mode)
        for existing in runtime.store.list():
            if (
                existing.product_key == key
                and existing.status == "OPEN"
                and (not existing.closes_at or existing.closes_at > int(time.time()))
            ):
                return existing.public(user.id)
    elif not body.confirmed_variant:
        raise HTTPException(409, "Confirm this custom product and variant.")
    id = str(uuid.uuid4())
    b = make_bloc(id, title, body.typical_price, mode=runtime.mode)
    b.owner_id = user.id
    if key:
        b.product_key = key
    try:
        await refresh_market(b, runtime.mode, b.calls)
    except ProviderError:
        b.market_mode = "unavailable"
        b.target_price = None
    runtime.store.create(b)
    return b.public(user.id)


class ViewCache:
    """Serialised Bloc views, keyed by revision, so a room that many people watch is built once.

    A Bloc only changes when its revision changes. Most visitors are not members, so they all get
    the same bytes; members get the same data with their own rows marked "me".
    """

    def __init__(self, size: int = 64):
        self.size, self.items, self.lock = size, {}, Lock()

    def get(self, store, id: str, meta: dict, viewer: str | None) -> bytes:
        key = (id, meta["generation"], meta["revision"])
        with self.lock:
            entry = self.items.get(key)
        if entry is None:
            bloc = store.get(id)
            base = bloc.public_base()
            entry = {
                "base": base,
                "json": json.dumps(base).encode(),
                "owner": bloc.owner_id,
                "positions": {
                    u: bloc.viewer_positions(u)
                    for u in {m.user_id for m in bloc.members}
                    if not u.startswith("seed-")
                },
            }
            with self.lock:
                self.items[key] = entry
                while len(self.items) > self.size:
                    self.items.pop(next(iter(self.items)))
        positions = entry["positions"].get(viewer, []) if viewer else []
        owner = bool(viewer and entry["owner"] == viewer)
        if not positions and not owner:
            return entry["json"]
        value = dict(entry["base"])
        members = list(value["members"])
        for i in positions:
            members[i] = {**members[i], "user_id": "me"}
        value["members"], value["viewer_is_owner"] = members, owner
        return json.dumps(value).encode()


view_cache = ViewCache()


@router.get("/blocs/{id}", response_model=BlocView)
def read_bloc(id: str, request: Request, runtime: RuntimeDep, user: OptionalUser):
    viewer = user.id if user else None
    meta = runtime.store.meta(id)
    if meta is None:
        raise HTTPException(404, "Bloc not found.")
    # The document only changes with its revision, so an unchanged revision is a cheap 304.
    # The tag includes the viewer because members are shown differently to each person.
    tag = hashlib.sha256(f"{meta['generation']}:{meta['revision']}:{viewer}".encode()).hexdigest()[
        :20
    ]
    etag = f'"{tag}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    try:
        body = view_cache.get(runtime.store, id, meta, viewer)
    except KeyError:
        raise HTTPException(404, "Bloc not found.") from None
    return Response(body, media_type="application/json", headers=headers)


@router.post("/blocs/{id}/join", response_model=BlocView)
def join_bloc(id: str, body: Join, runtime: RuntimeDep, user: CurrentUser):
    b = get_bloc(runtime, id)
    if settings.paypal_mode in {"simulator", "sandbox"}:
        # With payments on, joining means placing a PayPal hold first (see /money/blocs/{id}/hold).
        raise CodedError(402, "Place a PayPal hold to join this Bloc.", "payment_required")
    try:
        add_member(b, user.id, str(body.max_price))
        runtime.store.save(b)
    except (ValueError, Conflict) as exc:
        raise HTTPException(409, str(exc)) from None
    return b.public(user.id)


@router.post("/blocs/{id}/leave", response_model=BlocView)
async def leave_bloc(id: str, runtime: RuntimeDep, user: CurrentUser):
    b = get_bloc(runtime, id)
    try:
        if settings.paypal_mode in {"simulator", "sandbox"}:
            from maxx.money import service

            await service.leave(runtime.store, b, user.id)
        else:
            leave_member(b, user.id)
            runtime.store.save(b)
    except (ValueError, Conflict) as exc:
        raise HTTPException(409, str(exc)) from None
    return b.public(user.id)


@router.post("/blocs/{id}/start", response_model=BlocView, status_code=202)
async def start_bloc(id: str, runtime: RuntimeDep, user: CurrentUser):
    b = get_bloc(runtime, id)
    # Only the Bloc's creator or someone who has committed to it may close it.
    if b.owner_id != user.id and not any(
        m.user_id == user.id and m.status != "LEFT" for m in b.members
    ):
        raise HTTPException(403, "Join this Bloc before closing it.")
    ratelimit.hit(f"bloc:{user.id}", settings.bloc_actions_per_hour, 3600)
    try:
        await runtime.start(id)
        return get_bloc(runtime, id).public(user.id)
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from None
    except (ValueError, Conflict) as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/blocs/{id}/stream")
async def stream_bloc(
    id: str, request: Request, runtime: RuntimeDep, after: Annotated[int, Query(ge=0)] = 0
):
    b = get_bloc(runtime, id)
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(422, "Invalid event cursor.") from None
    if cursor < 0 or cursor > len(b.events):
        raise HTTPException(409, "Event cursor is stale. Reload the room.")
    # Each stream polls the database, so connections are capped per address and per Bloc.
    slot = hardening.streams.slot(client_ip(request), id)
    slot.__enter__()
    return _SlotStream(
        slot,
        event_frames(runtime.store, id, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


class _SlotStream(StreamingResponse):
    """Frees the connection slot however the response ends. A `finally` inside the generator is
    not enough: if the client leaves before the first frame, the generator never starts."""

    def __init__(self, slot, content, **kwargs):
        super().__init__(content, **kwargs)
        self.slot = slot

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.slot.__exit__(None, None, None)


@router.post("/demo/reset", response_model=list[BlocView])
async def reset_demo(runtime: RuntimeDep, user: CurrentUser):
    # Reset wipes everyone's seeded-demo participation. When admins are configured, only they may.
    if settings.admin_emails.strip() and not is_admin(user):
        raise HTTPException(403, "Only an administrator can reset the shared demo Blocs.")
    async with runtime.lock:
        if any(b.status == "NEGOTIATING" for b in runtime.store.list()):
            raise HTTPException(
                409, "Wait for active negotiations to finish before resetting demo Blocs."
            )
        runtime.seed(reset=True)
        return [b.public(user.id) for b in runtime.store.list() if b.id.startswith("demo-")]


@router.post("/catalog/match", response_model=MatchResult)
async def catalogue_match(body: Item, matcher: MatcherDep, request: Request, user: OptionalUser):
    address = client_ip(request)
    ratelimit.hit(f"match:{user.id if user else address}", settings.match_rate_per_hour, 3600)
    try:
        with budget.payer_scope(budget.payer_for(user, address), 1):
            return await asyncio.wait_for(matcher.match(body), timeout=settings.provider_timeout)
    except (ProviderError, TimeoutError) as exc:
        raise HTTPException(503, str(exc) or "Matching timed out.") from None
