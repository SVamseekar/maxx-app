"""Create synthetic shopping screenshots and explicit replay data; no model accuracy implied."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
font = (
    ImageFont.truetype(font_path, 28)
    if Path(font_path).exists()
    else ImageFont.load_default(size=28)
)
cases = [
    (
        "headphones",
        "Sony WH-1000XM5 Black",
        "Sony",
        "WH-1000XM5",
        "Black",
        "349.99",
        "Audio store",
        "USD",
        "299.99",
    ),
    (
        "phone",
        "Apple iPhone 16 128GB Black",
        "Apple",
        "iPhone 16",
        "128GB Black",
        "799.00",
        "Phone store",
        "USD",
        "749.00",
    ),
    (
        "vacuum",
        "Dyson V8 Cordless Vacuum",
        "Dyson",
        "V8",
        "Cordless",
        "399.99",
        "Home store",
        "USD",
        "379.99",
    ),
    (
        "unreadable",
        "Sony WH-1000XM5 Black",
        "Sony",
        "WH-1000XM5",
        "Black",
        None,
        "Audio store",
        "USD",
        None,
    ),
    (
        "non-usd",
        "Sony WH-1000XM5 Black",
        "Sony",
        "WH-1000XM5",
        "Black",
        "299.00",
        "Audio store",
        "EUR",
        None,
    ),
]
manifest = []
for name, title, brand, model, variant, price, merchant, currency, best in cases:
    image = Image.new("RGB", (760, 1000), "#f5f5f5")
    draw = ImageDraw.Draw(image)
    lines = [
        merchant,
        "Your cart",
        title,
        "Quantity: 1",
        ("$" if currency == "USD" else "EUR ") + (price or "???"),
        "Shipping calculated at checkout",
        "Synthetic evaluation screenshot",
    ]
    for index, line in enumerate(lines):
        draw.text((35, 60 + index * 100), line, font=font, fill="#171717")
    path = ROOT / "screenshots" / (name + ".png")
    image.save(path)
    public = ROOT.parent / "apps/web/public/samples"
    public.mkdir(parents=True, exist_ok=True)
    (public / path.name).write_bytes(path.read_bytes())
    rows = []
    if best:
        for index, cost in enumerate([best, str(float(best) + 10)]):
            rows.append(
                {
                    "title": title,
                    "url": f"https://store{index}.example/{name}",
                    "price": cost,
                    "shipping": "0",
                    "same_item": True,
                    "in_stock": True,
                    "evidence": f"${cost} In stock. Free shipping. Synthetic fixture.",
                }
            )
    manifest.append(
        {
            "name": name,
            "file": f"screenshots/{name}.png",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "item": {
                "title": title,
                "brand": brand,
                "model": model,
                "variant": variant,
                "price": price,
                "currency": currency,
                "merchant": merchant,
                "qty": 1,
                "confidence": 0.99 if price else 0.4,
                "visible_text": "\n".join(lines),
            },
            "rows": rows,
        }
    )
(ROOT / "fixtures.json").write_text(json.dumps(manifest, indent=2) + "\n")
