"Run with python -m maxx.verify_providers; never prints keys or provider error bodies."

import asyncio
import base64
import io
import json
import uuid

import httpx2 as httpx
from PIL import Image, ImageDraw

from maxx import budget
from maxx.config import settings
from maxx.providers import ProviderError, chat, request
from maxx.scan import Item


async def main():
    if not settings.nebius_api_key:
        print(
            json.dumps(
                {
                    "status": "unverified",
                    "reason": "NEBIUS_API_KEY missing",
                    "model_ids": "account availability unverified",
                    "image_input": "base64 image support unverified",
                }
            )
        )
        raise SystemExit(2)
    calls = []
    request_id = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=settings.provider_timeout) as client:
        try:
            catalog = await request(
                client,
                request_id,
                calls,
                "nebius",
                "models",
                settings.nebius_base_url.rstrip("/") + "/models",
            )
            ids = [m["id"] for m in catalog["data"]]
            selected = {
                role: {
                    "id": getattr(settings, "model_" + role),
                    "available": getattr(settings, "model_" + role) in ids,
                }
                for role in ["vision", "fast", "reason"]
            }
            print(json.dumps({"available_ids": ids, "configured_models": selected}, indent=2))
            if not all(m["available"] for m in selected.values()):
                print("Update MODEL_* in .env and rerun. No unavailable model will be called.")
                raise SystemExit(2)
            image = Image.new("RGB", (600, 200), "white")
            ImageDraw.Draw(image).text(
                (20, 40), "Test product USD $12.34", fill="black", font_size=38
            )
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            item = await chat(
                client,
                request_id,
                calls,
                "vision",
                {"screenshot": "the attached test image"},
                Item,
                "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode(),
            )
            print(
                json.dumps(
                    {
                        "image_input": "verified" if str(item.price) == "12.34" else "inconclusive",
                        "transport": "base64 data URL",
                        "price_read": str(item.price),
                        "calls": calls,
                    },
                    indent=2,
                )
            )
            if str(item.price) != "12.34":
                raise SystemExit(2)
        except ProviderError as exc:
            print(json.dumps({"status": "failed", "message": str(exc), "calls": calls}, indent=2))
            raise SystemExit(2) from None


if __name__ == "__main__":
    # A verification run is the operator's own spend, capped like any request.
    with budget.payer_scope(budget.Payer("system", "verify"), 20):
        asyncio.run(main())
