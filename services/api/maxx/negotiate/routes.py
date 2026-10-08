import asyncio
import time
import uuid
from decimal import Decimal
from threading import Lock
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from maxx import storage
from maxx.config import settings
from maxx.market import refresh_market
from maxx.matching import MatchResult, get_matcher
from maxx.negotiate.adapters import FixtureAdapter, NebiusAdapter
from maxx.negotiate.blocs import add_member, leave_member, make_bloc, transition
from maxx.negotiate.contracts import BlocView, Contract, Money
from maxx.negotiate.runner import run_negotiation, terminal_failure
from maxx.negotiate.store import BlocStore, Conflict
from maxx.negotiate.stream import event_frames
from maxx.providers import ProviderError
from maxx.scan import Item

router = APIRouter()


class CreateBloc(Contract):
    title: str = Field(min_length=3, max_length=300)
    typical_price: Money
    confirmed_variant: bool = False
    product_key: str | None = Field(default=None, max_length=100)
    item: Item | None = None


class User(Contract):
    user_id: str = Field(default="demo-you", min_length=1, max_length=50)


class Join(User):
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
        for b in self.store.list():
            if b.status == "NEGOTIATING" and self.store.job_status(b.id) != "QUEUED":
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
                adapter = self.adapter_factory() if self.adapter_factory else NebiusAdapter(id)
                if not self.adapter_factory:
                    await adapter.verify()
            else:
                raise ProviderError("NEGOTIATION_MODE must be fixture or live.")
            await refresh_market(b, self.mode, adapter.calls)
            b.mode = self.mode
            transition(b, "NEGOTIATING")
            self.store.save(b, queue=True)
            self.store.claim_job(id)
            task = asyncio.create_task(
                run_negotiation(self.store, id, adapter, round_delay=self.delay)
            )
            self.tasks[id] = task
            task.add_done_callback(lambda done, id=id: self.tasks.pop(id, None))
            return b.public()

    async def tick(self):
        import time

        # A task can die while the database is unavailable. Release safely once it returns.
        for b in self.store.list():
            if (
                b.status == "NEGOTIATING"
                and b.id not in self.tasks
                and self.store.job_status(b.id) == "RUNNING"
            ):
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
            task = asyncio.create_task(
                run_negotiation(self.store, id, adapter, round_delay=self.delay)
            )
            self.tasks[id] = task
            task.add_done_callback(lambda done, id=id: self.tasks.pop(id, None))
        for b in self.store.list():
            if b.status == "OPEN" and b.closes_at and b.closes_at <= int(time.time()):
                if not hasattr(self, "close_attempts"):
                    self.close_attempts = {}
                if time.time() - self.close_attempts.get(b.id, 0) < 60:
                    continue
                self.close_attempts[b.id] = time.time()
                try:
                    await self.start(b.id)
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


@router.get("/blocs", response_model=list[BlocView])
def list_blocs(runtime: RuntimeDep):
    return [b.public() for b in runtime.store.list()]


@router.post("/blocs", response_model=BlocView, status_code=201)
async def create_bloc(body: CreateBloc, runtime: RuntimeDep, matcher: MatcherDep):
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
                return existing.public()
    elif not body.confirmed_variant:
        raise HTTPException(409, "Confirm this custom product and variant.")
    id = str(uuid.uuid4())
    b = make_bloc(id, title, body.typical_price, mode=runtime.mode)
    if key:
        b.product_key = key
    try:
        await refresh_market(b, runtime.mode, b.calls)
    except ProviderError:
        b.market_mode = "unavailable"
        b.target_price = None
    runtime.store.create(b)
    return b.public()


@router.get("/blocs/{id}", response_model=BlocView)
def read_bloc(id: str, runtime: RuntimeDep):
    return get_bloc(runtime, id).public()


@router.post("/blocs/{id}/join", response_model=BlocView)
def join_bloc(id: str, body: Join, runtime: RuntimeDep):
    b = get_bloc(runtime, id)
    try:
        add_member(b, body.user_id, str(body.max_price))
        runtime.store.save(b)
    except (ValueError, Conflict) as exc:
        raise HTTPException(409, str(exc)) from None
    return b.public()


@router.post("/blocs/{id}/leave", response_model=BlocView)
def leave_bloc(id: str, body: User, runtime: RuntimeDep):
    b = get_bloc(runtime, id)
    try:
        leave_member(b, body.user_id)
        runtime.store.save(b)
    except (ValueError, Conflict) as exc:
        raise HTTPException(409, str(exc)) from None
    return b.public()


@router.post("/blocs/{id}/start", response_model=BlocView, status_code=202)
async def start_bloc(id: str, runtime: RuntimeDep):
    get_bloc(runtime, id)
    try:
        return await runtime.start(id)
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
    return StreamingResponse(
        event_frames(runtime.store, id, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/demo/reset", response_model=list[BlocView])
async def reset_demo(runtime: RuntimeDep):
    async with runtime.lock:
        if any(b.status == "NEGOTIATING" for b in runtime.store.list()):
            raise HTTPException(
                409, "Wait for active negotiations to finish before resetting demo Blocs."
            )
        runtime.seed(reset=True)
        return [b.public() for b in runtime.store.list() if b.id.startswith("demo-")]


@router.post("/catalog/match", response_model=MatchResult)
async def catalogue_match(body: Item, matcher: MatcherDep):
    try:
        return await asyncio.wait_for(matcher.match(body), timeout=settings.provider_timeout)
    except (ProviderError, TimeoutError) as exc:
        raise HTTPException(503, str(exc) or "Matching timed out.") from None
