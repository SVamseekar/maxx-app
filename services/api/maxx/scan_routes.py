import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from maxx.flow import run_scan
from maxx.providers import ProviderError
from maxx.scan import MAX_UPLOAD, Item, ScanError, ScanResult, validate_image

router = APIRouter()


@router.post(
    "/scan",
    response_model=ScanResult,
    responses={code: {"model": ScanError} for code in (413, 422, 503)},
)
async def scan(
    request: Request,
    owns_similar: bool = False,
    title: Annotated[str | None, Query(max_length=300)] = None,
    price: str | None = None,
    merchant: str | None = None,
):
    request_id = str(uuid.uuid4())
    try:
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_UPLOAD:
                return JSONResponse(
                    {
                        "code": "upload_too_large",
                        "message": "Choose an image up to 8 MB.",
                        "request_id": request_id,
                    },
                    status_code=413,
                )
        mime = request.headers.get("content-type", "").split(";")[0]
        validate_image(bytes(data), mime)
        corrections = {}
        if title is not None:
            if not title.strip():
                raise ValueError("Enter a product title.")
            corrections["title"] = title.strip()
        if price is not None:
            corrections["price"] = Item(price=price).price
            corrections["currency"] = "USD"
        if merchant is not None:
            corrections["merchant"] = merchant[:300]
        async with asyncio.timeout(100):
            return await run_scan(bytes(data), mime, owns_similar, request_id, corrections)
    except ValueError:
        return JSONResponse(
            {
                "code": "invalid_upload",
                "message": (
                    "Check the image type, size and product details. Use PNG, JPG or WebP"
                    " up to 8 MB and 16 megapixels."
                ),
                "request_id": request_id,
            },
            status_code=422,
        )
    except (ProviderError, TimeoutError) as exc:
        message = str(exc) if isinstance(exc, ProviderError) else "Scan timed out. Try again."
        return JSONResponse(
            {"code": "scan_unavailable", "message": message, "request_id": request_id},
            status_code=503,
        )
