"""SSE over durable events, with resume cursors and terminal completion."""

import asyncio

from maxx.negotiate.store import BlocStore


async def event_frames(store: BlocStore, id: str, after: int = 0, interval: float = 0.2):
    generation = store.get(id).generation
    yield "retry: 1000\n\n"
    cursor = after
    idle = 0
    while True:
        bloc = store.get(id)
        if bloc.generation != generation or cursor > len(bloc.events):
            yield 'event: reset\ndata: {"message":"Demo reset. Reload the room."}\n\n'
            return
        for event in store.replay(id, bloc.generation, cursor):
            if event.id > cursor:
                yield f"id: {event.id}\ndata: {event.model_dump_json()}\n\n"
                cursor = event.id
                idle = 0
        if bloc.status in {"SETTLED", "FAILED"}:
            return
        idle += 1
        if idle % 50 == 0:
            yield ": keepalive\n\n"
        await asyncio.sleep(interval)
