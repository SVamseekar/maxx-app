"""What a person may still spend on live AI today, so the interface can say so before a scan."""

from fastapi import APIRouter, Request

from maxx import budget
from maxx.auth.deps import OptionalUser, client_ip
from maxx.config import settings

router = APIRouter()


@router.get("/ai/usage")
def usage(request: Request, user: OptionalUser):
    payer = budget.payer_for(user, client_ip(request))
    return {
        "payer": payer.kind,
        "premium": payer.premium,
        "remaining_usd": str(budget.remaining_for(payer)),
        "paused": budget.status()["paused"],
        "anonymous_live": settings.ai_anonymous_live,
        "resets": "00:00 UTC",
    }
