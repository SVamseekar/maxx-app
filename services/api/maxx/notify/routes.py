"""A person's own notifications and email preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from maxx.auth import ratelimit
from maxx.auth.deps import CurrentUser, same_origin
from maxx.notify import service

router = APIRouter(prefix="/notifications", dependencies=[Depends(same_origin)])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Read(Strict):
    ids: list[str] | None = Field(default=None, max_length=200)


class Preferences(Strict):
    email: dict[str, bool] = Field(max_length=50)


@router.get("")
def my_notifications(
    user: CurrentUser,
    limit: int = Query(default=30, ge=1, le=100),
    before: int | None = Query(default=None, ge=0),
):
    return service.inbox(user.id, limit, before)


@router.get("/unread")
def unread(user: CurrentUser):
    return {"unread": service.unread_count(user.id)}


@router.post("/read")
def mark_read(body: Read, user: CurrentUser):
    ratelimit.hit(f"notify-read:{user.id}", 300, 3600)
    return {"marked": service.mark_read(user.id, body.ids)}


@router.get("/preferences")
def get_preferences(user: CurrentUser):
    return {"email": service.preferences(user.id), "always": _always()}


@router.post("/preferences")
def set_preferences(body: Preferences, user: CurrentUser):
    ratelimit.hit(f"notify-prefs:{user.id}", 60, 3600)
    return {"email": service.set_preferences(user.id, body.email), "always": _always()}


def _always() -> list[str]:
    return sorted(kind for kind, (_, optional) in service.KINDS.items() if not optional)
