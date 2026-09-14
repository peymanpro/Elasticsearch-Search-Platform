"""
Deterministic product dataset generator.

Produces N synthetic product documents matching the schema defined in
docs/09-product-document-model.md. The generator is seeded, so the
same seed always produces the same output. This is what lets Phase 21
tests and Phase 22 benchmarks rely on a stable dataset.

Usage:

    python scripts/generate_products.py --seed 42 --count 100
    python scripts/generate_products.py --seed 42 --count 1000 --out data/generated/products-1k.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Base templates
# ---------------------------------------------------------------------------
# A small set of hand-authored product seeds. The generator produces
# variants by combining a template with randomized numeric fields. This
# keeps the generated text coherent (a real product name, a real brand)
# while varying the fields that faceted search demonstrates on.

BASE_TEMPLATES = [
    {
        "name": "Wireless Noise-Cancelling Headphones",
        "brand": "Sony",
        "category": "Electronics",
        "description": "Over-ear wireless headphones with active noise cancellation and long battery life.",
        "tags": ["wireless", "bluetooth", "noise-cancelling", "over-ear"],
        "specifications": {
            "color": "black",
            "battery_hours": 30,
            "weight_grams": 254,
            "connectivity": "bluetooth 5.2",
        },
    },
    {
        "name": "4K Ultra HD Smart TV 55-inch",
        "brand": "Samsung",
        "category": "Electronics",
        "description": "55-inch 4K UHD smart television with HDR and built-in streaming apps.",
        "tags": ["tv", "4k", "smart", "hdr"],
        "specifications": {
            "screen_inches": 55,
            "resolution": "3840x2160",
            "hdr": "HDR10+",
            "smart_os": "tizen",
        },
    },
    {
        "name": "Mechanical Keyboard TKL RGB",
        "brand": "Keychron",
        "category": "Electronics",
        "description": "Tenkeyless mechanical keyboard with RGB backlighting and hot-swappable switches.",
        "tags": ["keyboard", "mechanical", "rgb", "tkl"],
        "specifications": {
            "layout": "tkl",
            "switch": "gateron brown",
            "backlight": "rgb",
            "connectivity": "usb-c",
        },
    },
    {
        "name": "Tablet 11-inch 128GB Wi-Fi",
        "brand": "Apple",
        "category": "Electronics",
        "description": "11-inch tablet with 128GB storage and Wi-Fi 6 connectivity.",
        "tags": ["tablet", "apple", "ipad", "wi-fi"],
        "specifications": {
            "screen_inches": 11,
            "storage_gb": 128,
            "connectivity": "wi-fi 6",
            "color": "space gray",
        },
    },
    {
        "name": "Stainless Steel Chef Knife 8-inch",
        "brand": "Wusthof",
        "category": "Home and Kitchen",
        "description": "Forged 8-inch chef knife with full tang and ergonomic handle.",
        "tags": ["kitchen", "knife", "cooking", "chef"],
        "specifications": {
            "blade_length_inches": 8,
            "steel": "high-carbon stainless",
            "weight_grams": 260,
        },
    },
    {
        "name": "Espresso Machine with Milk Frother",
        "brand": "Breville",
        "category": "Home and Kitchen",
        "description": "Semi-automatic espresso machine with integrated steam wand.",
        "tags": ["espresso", "coffee", "kitchen", "breville"],
        "specifications": {
            "pressure_bar": 15,
            "water_tank_liters": 2.0,
            "milk_frother": True,
            "color": "stainless steel",
        },
    },
    {
        "name": "Nonstick Frying Pan 12-inch",
        "brand": "T-fal",
        "category": "Home and Kitchen",
        "description": "12-inch nonstick frying pan with heat indicator.",
        "tags": ["pan", "nonstick", "cooking", "frying"],
        "specifications": {
            "diameter_inches": 12,
            "material": "aluminum",
            "coating": "ptfe",
            "dishwasher_safe": True,
        },
    },
    {
        "name": "Ergonomic Office Chair with Lumbar Support",
        "brand": "Herman Miller",
        "category": "Office",
        "description": "Ergonomic office chair with adjustable lumbar support and armrests.",
        "tags": ["chair", "ergonomic", "office", "lumbar"],
        "specifications": {
            "weight_capacity_kg": 136,
            "adjustable_armrests": True,
            "material": "mesh",
            "color": "graphite",
        },
    },
    {
        "name": "Standing Desk Electric Adjustable 60-inch",
        "brand": "Uplift",
        "category": "Office",
        "description": "Electric height-adjustable standing desk with memory presets.",
        "tags": ["desk", "standing", "adjustable", "office"],
        "specifications": {
            "width_inches": 60,
            "height_range_inches": "25-51",
            "memory_presets": 4,
            "motor": "dual",
        },
    },
    {
        "name": "Yoga Mat Non-Slip 6mm",
        "brand": "Manduka",
        "category": "Sports",
        "description": "6mm non-slip yoga mat with closed-cell surface.",
        "tags": ["yoga", "mat", "fitness", "non-slip"],
        "specifications": {
            "thickness_mm": 6,
            "length_inches": 71,
            "material": "pvc-free",
            "color": "deep sea blue",
        },
    },
    {
        "name": "Running Shoes Lightweight Trail",
        "brand": "Salomon",
        "category": "Sports",
        "description": "Lightweight trail running shoes with grippy outsole.",
        "tags": ["running", "shoes", "trail", "sports"],
        "specifications": {"size_us": 10, "weight_grams": 280, "drop_mm": 8, "color": "lava red"},
    },
    {
        "name": "Designing Data-Intensive Applications",
        "brand": "O Reilly",
        "category": "Books",
        "description": "Comprehensive guide to the principles of modern data systems.",
        "tags": ["book", "technology", "distributed-systems", "data"],
        "specifications": {
            "pages": 616,
            "publisher": "O Reilly",
            "language": "english",
            "isbn": "978-1449373320",
        },
    },
]


# ---------------------------------------------------------------------------
# Variation policy
# ---------------------------------------------------------------------------
# Each generated document is a copy of a template with these fields varied:
#
#   sku          -- a synthetic unique code derived from the index
#   id           -- equal to sku
#   price        -- the template has a base price (see BASE_PRICES) times a
#                   uniform multiplier in [0.85, 1.15], rounded to cents
#   currency     -- chosen from USD/EUR/GBP
#   rating       -- uniform in [3.5, 5.0], rounded to one decimal
#   popularity   -- integer in [10, 5000]
#   availability -- weighted choice across the four enum values
#   created_at   -- a random date within the last 3 years
#
# Text fields (name, brand, category, description, tags, specifications)
# come from the template unchanged. Randomizing text produces incoherent
# corpora that would corrupt the relevance experiments of Phases 9-16.

BASE_PRICES = {
    "Wireless Noise-Cancelling Headphones": 349.99,
    "4K Ultra HD Smart TV 55-inch": 699.00,
    "Mechanical Keyboard TKL RGB": 119.99,
    "Tablet 11-inch 128GB Wi-Fi": 449.00,
    "Stainless Steel Chef Knife 8-inch": 149.95,
    "Espresso Machine with Milk Frother": 499.00,
    "Nonstick Frying Pan 12-inch": 39.99,
    "Ergonomic Office Chair with Lumbar Support": 1295.00,
    "Standing Desk Electric Adjustable 60-inch": 749.00,
    "Yoga Mat Non-Slip 6mm": 88.00,
    "Running Shoes Lightweight Trail": 159.99,
    "Designing Data-Intensive Applications": 54.99,
}

AVAILABILITY_WEIGHTS = (
    ("in_stock", 0.70),
    ("out_of_stock", 0.10),
    ("preorder", 0.10),
    ("discontinued", 0.10),
)

CURRENCIES = ("USD", "EUR", "GBP")


def _pick_weighted(rng: random.Random, choices: tuple[tuple[str, float], ...]) -> str:
    """Return a value from a weighted-choice tuple."""
    names = [name for name, _ in choices]
    weights = [weight for _, weight in choices]
    return rng.choices(names, weights=weights, k=1)[0]


def _generate_one(rng: random.Random, index: int, sku_prefix: str) -> dict:
    """Return one generated product document as a plain dict."""
    template = rng.choice(BASE_TEMPLATES)
    base_price = BASE_PRICES[template["name"]]
    multiplier = rng.uniform(0.85, 1.15)
    price = round(base_price * multiplier, 2)

    days_ago = rng.randint(0, 365 * 3)
    created_at = datetime.now(UTC) - timedelta(days=days_ago)

    sku = f"{sku_prefix}-{index:06d}"

    return {
        "id": sku,
        "sku": sku,
        "name": template["name"],
        "brand": template["brand"],
        "category": template["category"],
        "description": template["description"],
        "tags": list(template["tags"]),
        "specifications": dict(template["specifications"]),
        "language": "en",
        "price": price,
        "currency": rng.choice(CURRENCIES),
        "rating": round(rng.uniform(3.5, 5.0), 1),
        "availability": _pick_weighted(rng, AVAILABILITY_WEIGHTS),
        "created_at": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "popularity": rng.randint(10, 5000),
    }


def generate(seed: int, count: int, sku_prefix: str = "GEN") -> list[dict]:
    """
    Generate ``count`` documents deterministically from ``seed``.

    The returned list is fully determined by (seed, count, sku_prefix).
    Two calls with the same arguments produce byte-identical JSONL when
    serialized by ``write_dataset``.
    """
    rng = random.Random(seed)
    return [_generate_one(rng, i + 1, sku_prefix) for i in range(count)]


def write_dataset(documents: list[dict], out_path: Path) -> None:
    """Write documents to ``out_path`` as JSONL, one per line."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as stream:
        for doc in documents:
            stream.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--out", type=Path, default=Path("data/generated/products.jsonl"))
    parser.add_argument("--sku-prefix", default="GEN")
    args = parser.parse_args()

    documents = generate(seed=args.seed, count=args.count, sku_prefix=args.sku_prefix)
    write_dataset(documents, args.out)
    print(f"wrote {len(documents)} documents to {args.out}")


if __name__ == "__main__":
    main()
