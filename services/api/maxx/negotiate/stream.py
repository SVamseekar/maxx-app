"""SSE over durable events, with resume cursors and terminal completion.

Polling is a single tiny indexed query (latest event id and status), so thousands of open rooms do
not each re-read a whole Bloc. The full event list is fetched only when something actually changed.
"""

import asyncio

from maxx.negotiate.store import BlocStore


async def event_frames(store: BlocStore, id: str, after: int = 0, interval: float = 0.5):
    meta = await asyncio.to_thread(store.meta, id)
    if meta is None:
        return
    generation = meta["generation"]
    yield "retry: 1000\n\n"
    cursor = after
    idle = 0
    while True:
        meta = await asyncio.to_thread(store.meta, id)
        if meta is None or meta["generation"] != generation:
            yield 'event: reset\ndata: {"message":"Demo reset. Reload the room."}\n\n'
            return
        latest = await asyncio.to_thread(store.latest_event, id, generation)
        if cursor > latest:
            yield 'event: reset\ndata: {"message":"Demo reset. Reload the room."}\n\n'
            return
        if latest > cursor:
            for event in await asyncio.to_thread(store.replay, id, generation, cursor):
                if event.id > cursor:
                    yield f"id: {event.id}\ndata: {event.model_dump_json()}\n\n"
                    cursor = event.id
                    idle = 0
        elif meta["status"] in {"SETTLED", "FAILED"}:
            return
        idle += 1
        if idle % 30 == 0:
            yield ": keepalive\n\n"
        await asyncio.sleep(interval)
