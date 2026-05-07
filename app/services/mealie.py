"""Mealie integration: pull recipes as Bento foods (1 serving = 100g virtual unit).

Mealie stores nutrition per serving. We map per-serving values directly to
Bento's per-100g fields and set default_serving_g=100 — so a Bento amount of
100g represents one Mealie serving and the macros scale linearly from there.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Food, MealieSettings

logger = logging.getLogger(__name__)

USER_AGENT = "Bento/1.0 (https://github.com/shamedshadow/bento)"
DEFAULT_SERVING_LABEL = "1 serving"
PAGE_SIZE = 100


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _coerce_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


async def get_or_create_settings(session: AsyncSession) -> MealieSettings:
    row = (
        await session.execute(
            select(MealieSettings).where(MealieSettings.id == 1)
        )
    ).scalar_one_or_none()
    if row is None:
        row = MealieSettings(id=1)
        session.add(row)
        await session.flush()
    return row


async def test_connection(url: str, token: str) -> tuple[bool, str]:
    """Quick auth check against /api/users/self. Returns (ok, message)."""
    if not url or not token:
        return False, "URL and API token are both required."
    base = _normalize_url(url)
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            resp = await client.get(f"{base}/api/users/self")
            if resp.status_code == 200:
                data = resp.json()
                who = data.get("username") or data.get("email") or "Mealie user"
                return True, f"Connected as {who}."
            if resp.status_code == 401:
                return False, "API token rejected (401)."
            if resp.status_code == 404:
                return False, "URL doesn't look like a Mealie API root."
            return False, f"Mealie returned HTTP {resp.status_code}."
    except httpx.HTTPError as e:
        logger.warning("Mealie connection test failed: %s", e)
        return False, f"Network error: {e}"


def map_recipe_to_food_fields(recipe: dict) -> Optional[dict]:
    """Transform a Mealie recipe payload into Food columns. Returns None when
    nutrition is entirely absent (we'd be importing a row with no logging value).
    """
    nutrition = recipe.get("nutrition") or {}
    fields = {
        "calories_per_100g": _coerce_float(nutrition.get("calories")),
        "carbs_per_100g": _coerce_float(nutrition.get("carbohydrateContent")),
        "fiber_per_100g": _coerce_float(nutrition.get("fiberContent")),
        "protein_per_100g": _coerce_float(nutrition.get("proteinContent")),
        "fat_per_100g": _coerce_float(nutrition.get("fatContent")),
        "sugar_per_100g": _coerce_float(nutrition.get("sugarContent")),
    }
    # Mealie reports sodium in mg per serving; we store grams per-100g.
    sodium_mg = _coerce_float(nutrition.get("sodiumContent"))
    fields["sodium_per_100g"] = sodium_mg / 1000.0 if sodium_mg is not None else None

    if all(v is None for v in fields.values()):
        return None

    name = (recipe.get("name") or "").strip()
    if not name:
        return None
    slug = recipe.get("slug")
    if not slug:
        return None

    return {
        "source": "mealie",
        "source_id": slug,
        "barcode": None,
        "name": name,
        "brand": "Mealie",
        "default_serving_g": 100.0,
        "default_serving_label": DEFAULT_SERVING_LABEL,
        **fields,
    }


async def _fetch_all_slugs(client: httpx.AsyncClient, base: str) -> list[str]:
    """Iterate paginated /api/recipes, return slugs only (full data fetched per-slug)."""
    slugs: list[str] = []
    page = 1
    while True:
        resp = await client.get(
            f"{base}/api/recipes",
            params={"page": page, "perPage": PAGE_SIZE},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items") or []
        slugs.extend(it["slug"] for it in items if "slug" in it)
        if len(items) < PAGE_SIZE:
            break
        page += 1
    return slugs


async def _fetch_recipe(client: httpx.AsyncClient, base: str, slug: str) -> Optional[dict]:
    resp = await client.get(f"{base}/api/recipes/{slug}")
    if resp.status_code != 200:
        logger.warning("Mealie recipe fetch failed for %s: %s", slug, resp.status_code)
        return None
    return resp.json()


async def sync(
    session: AsyncSession, settings: MealieSettings
) -> dict:
    """Upsert all Mealie recipes as Foods. Returns counts."""
    if not settings.url or not settings.api_token:
        return {"error": "Mealie not configured."}
    base = _normalize_url(settings.url)
    headers = {
        "Authorization": f"Bearer {settings.api_token}",
        "User-Agent": USER_AGENT,
    }
    imported = updated = skipped = 0
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            slugs = await _fetch_all_slugs(client, base)
            for slug in slugs:
                recipe = await _fetch_recipe(client, base, slug)
                if recipe is None:
                    skipped += 1
                    continue
                fields = map_recipe_to_food_fields(recipe)
                if fields is None:
                    skipped += 1
                    continue
                existing = (
                    await session.execute(
                        select(Food).where(
                            Food.source == "mealie",
                            Food.source_id == slug,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    existing.last_synced_at = _now_utc_naive()
                    updated += 1
                else:
                    food = Food(**fields, last_synced_at=_now_utc_naive())
                    session.add(food)
                    imported += 1
    except httpx.HTTPError as e:
        logger.warning("Mealie sync HTTP error: %s", e)
        return {"error": f"Network error: {e}"}

    settings.last_synced_at = _now_utc_naive()
    settings.last_sync_summary = (
        f"{imported} new, {updated} updated, {skipped} skipped (no nutrition or fetch failed)"
    )
    await session.flush()
    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "total": len(slugs),
    }
