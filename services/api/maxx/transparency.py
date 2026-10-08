"""Public metadata only. No prompts, images, credentials or seller state."""

from fastapi import APIRouter

from maxx import providers, storage
from maxx.config import settings
from maxx.scan import CallRecord, Contract

router = APIRouter()


class Transparency(Contract):
    modes: dict[str, str]
    configured_models: dict[str, str]
    calls: list[CallRecord]
    cost_status: str = "unmeasured"


@router.get("/transparency", response_model=Transparency)
def transparency():
    calls = []
    for record in storage.get_store().recent_calls():
        try:
            record["tokens"] = providers.token_counts(record.get("tokens"))
            fields = CallRecord.model_fields
            calls.append(
                CallRecord.model_validate({k: v for k, v in record.items() if k in fields})
            )
        except (ValueError, AttributeError, TypeError):
            continue
    return Transparency(
        modes={
            "scan": settings.scan_mode,
            "negotiation": settings.negotiation_mode,
            "matching": settings.match_mode,
        },
        configured_models={
            role: getattr(settings, "model_" + role)
            for role in ("vision", "fast", "reason", "seller", "negotiator", "embed")
        },
        calls=calls,
        cost_status="configured estimates"
        if any(c.cost_status == "estimated" for c in calls)
        else "unmeasured",
    )
