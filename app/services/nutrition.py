"""Food lookup, search, and creation.

Open Food Facts is the primary nutrition source. USDA fallback for unbranded
text searches lands in F2 pass 2.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Food

logger = logging.getLogger(__name__)

OFF_BASE = "https://world.openfoodfacts.org/api/v2"
USDA_BASE = "https://api.nal.usda.gov/fdc/v1"
USER_AGENT = "Bento/1.0 (https://github.com/shamedshadow/bento)"
CACHE_TTL = timedelta(days=30)
# Be polite — cap concurrent external requests across the process at 2.
_OFF_SEMAPHORE = asyncio.Semaphore(2)
_USDA_SEMAPHORE = asyncio.Semaphore(2)
# Local-search hit count below which we top up with USDA (per scope F2).
USDA_TOPUP_THRESHOLD = 5
# USDA nutrient IDs (FDC standard). Energy has multiple — Foundation entries
# tend to use 2047/2048 (Atwater factors); SR Legacy uses 1008. Try them in
# fallback order. Sugar similarly varies between 2000 and 1063.
_USDA_NUTRIENT_FALLBACKS = {
    "calories_per_100g": (1008, 2047, 2048),
    "carbs_per_100g": (1005,),
    "fiber_per_100g": (1079,),
    "protein_per_100g": (1003,),
    "fat_per_100g": (1004,),
    "sugar_per_100g": (2000, 1063),
    "sodium_per_100g": (1093,),  # mg per 100g — convert to g below
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _fetch_off(barcode: str) -> dict | None:
    async with _OFF_SEMAPHORE:
        try:
            async with httpx.AsyncClient(
                timeout=10.0, headers={"User-Agent": USER_AGENT}
            ) as client:
                resp = await client.get(f"{OFF_BASE}/product/{barcode}.json")
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("OFF lookup failed for %s: %s", barcode, e)
            return None

    if data.get("status") != 1 or "product" not in data:
        return None
    return data["product"]


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _map_off_product(barcode: str, product: dict) -> dict:
    nutr = product.get("nutriments") or {}
    name = (
        product.get("product_name")
        or product.get("product_name_en")
        or product.get("generic_name")
        or "Unknown product"
    )
    brand = (product.get("brands") or "").split(",")[0].strip() or None
    return {
        "source": "openfoodfacts",
        "source_id": product.get("code") or barcode,
        "barcode": barcode,
        "name": name.strip(),
        "brand": brand,
        "default_serving_g": _coerce_float(product.get("serving_quantity")),
        "default_serving_label": (product.get("serving_size") or None),
        "calories_per_100g": _coerce_float(
            nutr.get("energy-kcal_100g") or nutr.get("energy_kcal_100g")
        ),
        "carbs_per_100g": _coerce_float(nutr.get("carbohydrates_100g")),
        "fiber_per_100g": _coerce_float(nutr.get("fiber_100g")),
        "protein_per_100g": _coerce_float(nutr.get("proteins_100g")),
        "fat_per_100g": _coerce_float(nutr.get("fat_100g")),
        "sugar_per_100g": _coerce_float(nutr.get("sugars_100g")),
        "sodium_per_100g": _coerce_float(nutr.get("sodium_100g")),
    }


async def lookup_by_barcode(
    session: AsyncSession, barcode: str
) -> Optional[Food]:
    """Local cache first; OFF fallback. Caches new rows; refreshes stale ones."""
    barcode = barcode.strip()
    if not barcode:
        return None

    existing = (
        await session.execute(
            select(Food).where(
                Food.barcode == barcode,
                Food.source == "openfoodfacts",
            )
        )
    ).scalar_one_or_none()

    fresh = _now() - CACHE_TTL
    if existing and existing.last_synced_at and existing.last_synced_at >= fresh:
        return existing

    product = await _fetch_off(barcode)
    if product is None:
        # OFF didn't know it. If we have a stale cached hit, surface it; else None.
        return existing

    fields = _map_off_product(barcode, product)
    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        existing.last_synced_at = _now()
        return existing

    food = Food(**fields, last_synced_at=_now())
    session.add(food)
    await session.flush()
    return food


async def search_local(
    session: AsyncSession, q: str, limit: int = 30
) -> list[Food]:
    q = q.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    rows = (
        await session.execute(
            select(Food)
            .where(Food.name.ilike(pattern) | Food.brand.ilike(pattern))
            .order_by(Food.name)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def _fetch_usda(query: str, limit: int = 10) -> list[dict]:
    """Hit USDA FDC search. Filters to Foundation + SR Legacy (per-100g values)."""
    if not settings.usda_api_key:
        return []
    params = {
        "api_key": settings.usda_api_key,
        "query": query,
        "pageSize": str(limit),
        "dataType": "Foundation,SR Legacy",
    }
    async with _USDA_SEMAPHORE:
        try:
            async with httpx.AsyncClient(
                timeout=10.0, headers={"User-Agent": USER_AGENT}
            ) as client:
                resp = await client.get(f"{USDA_BASE}/foods/search", params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("USDA search failed for %r: %s", query, e)
            return []
    return data.get("foods", []) or []


def _map_usda_food(hit: dict) -> dict:
    nutrients = {
        n.get("nutrientId"): n.get("value")
        for n in hit.get("foodNutrients") or []
        if n.get("nutrientId") is not None
    }
    fields: dict[str, Optional[float]] = {}
    for key, ids in _USDA_NUTRIENT_FALLBACKS.items():
        value = None
        for nid in ids:
            v = _coerce_float(nutrients.get(nid))
            if v is not None:
                value = v
                break
        fields[key] = value
    # USDA reports sodium in mg per 100g; we store grams per 100g.
    if fields.get("sodium_per_100g") is not None:
        fields["sodium_per_100g"] = fields["sodium_per_100g"] / 1000.0
    return {
        "source": "usda",
        "source_id": str(hit["fdcId"]),
        "barcode": None,
        "name": (hit.get("description") or "Unknown").strip(),
        "brand": (hit.get("brandOwner") or "").strip() or None,
        "default_serving_g": None,
        "default_serving_label": None,
        **fields,
    }


async def search_foods(
    session: AsyncSession, q: str, limit: int = 30
) -> list[Food]:
    """Local cache first; if fewer than USDA_TOPUP_THRESHOLD hits and a USDA key
    is configured, top up from USDA and cache the new rows.
    """
    local = await search_local(session, q, limit)
    if len(local) >= USDA_TOPUP_THRESHOLD or not settings.usda_api_key or not q.strip():
        return local

    hits = await _fetch_usda(q.strip(), limit=limit - len(local))
    if not hits:
        return local

    seen_usda_ids = {f.source_id for f in local if f.source == "usda"}
    appended: list[Food] = []
    for hit in hits:
        fdc_id = str(hit.get("fdcId") or "")
        if not fdc_id or fdc_id in seen_usda_ids:
            continue
        # Another concurrent request might have already cached this row.
        existing = (
            await session.execute(
                select(Food).where(
                    Food.source == "usda", Food.source_id == fdc_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            seen_usda_ids.add(fdc_id)
            appended.append(existing)
            continue
        food = Food(**_map_usda_food(hit), last_synced_at=_now())
        session.add(food)
        await session.flush()
        seen_usda_ids.add(fdc_id)
        appended.append(food)
    return local + appended


async def create_custom_food(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    calories_per_100g: float,
    carbs_per_100g: float,
    brand: Optional[str] = None,
    default_serving_g: Optional[float] = None,
    default_serving_label: Optional[str] = None,
    fiber_per_100g: Optional[float] = None,
    protein_per_100g: Optional[float] = None,
    fat_per_100g: Optional[float] = None,
    sugar_per_100g: Optional[float] = None,
    sodium_per_100g: Optional[float] = None,
) -> Food:
    food = Food(
        source="custom",
        source_id=None,
        name=name.strip(),
        brand=(brand or "").strip() or None,
        default_serving_g=default_serving_g,
        default_serving_label=(default_serving_label or "").strip() or None,
        calories_per_100g=calories_per_100g,
        carbs_per_100g=carbs_per_100g,
        fiber_per_100g=fiber_per_100g,
        protein_per_100g=protein_per_100g,
        fat_per_100g=fat_per_100g,
        sugar_per_100g=sugar_per_100g,
        sodium_per_100g=sodium_per_100g,
        created_by_user_id=user_id,
    )
    session.add(food)
    await session.flush()
    return food
