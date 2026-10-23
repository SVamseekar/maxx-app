"""Demo-only endpoints for judges. Refused unless the demo setup is on (see tour.enabled)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from maxx.auth import ratelimit
from maxx.auth.deps import CurrentUser, same_origin
from maxx.demo import tour
from maxx.negotiate.routes import RuntimeDep
from maxx.providers import ProviderError

router = APIRouter(prefix="/demo", dependencies=[Depends(same_origin)])


@router.get("/seller-tour")
def tour_status():
    return {"available": tour.enabled()}


@router.post("/seller-tour", status_code=201)
async def start_tour(runtime: RuntimeDep, user: CurrentUser):
    if not tour.enabled():
        raise HTTPException(404, "Not found.")
    if not user.email_verified:
        raise HTTPException(403, "Confirm your email before starting the seller tour.")
    ratelimit.hit(f"seller-tour:{user.id}", 3, 3600)
    ratelimit.hit("seller-tour:all", 60, 3600)
    try:
        return await tour.start(runtime, user)
    except tour.TourError as exc:
        raise HTTPException(409, str(exc)) from None
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
