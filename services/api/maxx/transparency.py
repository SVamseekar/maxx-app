"""Public metadata only. No prompts, images, credentials or seller state."""

from urllib.parse import urlparse

from fastapi import APIRouter

from maxx import providers, storage
from maxx.config import settings
from maxx.scan import CallRecord, Contract

router = APIRouter()


class Transparency(Contract):
    modes: dict[str, str]
    configured_models: dict[str, str]
    # Where every model call goes (host only), e.g. api.tokenfactory.nebius.com.
    inference_host: str = ""
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
            "payments": settings.paypal_mode,
        },
        configured_models={
            role: getattr(settings, "model_" + role)
            for role in ("vision", "fast", "reason", "seller", "negotiator", "embed")
        },
        inference_host=urlparse(settings.nebius_base_url).hostname or "",
        calls=calls,
        cost_status="configured estimates"
        if any(c.cost_status == "estimated" for c in calls)
        else "unmeasured",
    )
