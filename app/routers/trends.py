from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_user
from app.db import get_session
from app.models import User
from app.services import trends as trends_svc

router = APIRouter()
templates = Jinja2Templates(directory="templates")

_ALLOWED_RANGES = (30, 90)


@router.get("/trends")
async def trends_page(
    request: Request,
    days: int = Query(30),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    if days not in _ALLOWED_RANGES:
        days = 30

    series = await trends_svc.daily_series(db, user, days)
    rolling = trends_svc.rolling_average(series, window=7)
    stats = trends_svc.summary_stats(series, user.daily_target_primary)

    show_scatter = user.primary_metric in ("net_carbs", "total_carbs")
    scatter = (
        await trends_svc.per_meal_scatter(db, user, days=14)
        if show_scatter
        else []
    )

    chart_data = {
        "labels": [d.isoformat() for d, _ in series],
        "daily": [round(v, 2) for _, v in series],
        "rolling": [round(v, 2) for _, v in rolling],
        "target": user.daily_target_primary,
        "metric_label": user.primary_metric.replace("_", " "),
    }

    return templates.TemplateResponse(
        request,
        "trends.html",
        {
            "current_user": user,
            "days": days,
            "ranges": _ALLOWED_RANGES,
            "chart_data": chart_data,
            "stats": stats,
            "show_scatter": show_scatter,
            "scatter_points": scatter,
            "primary_metric_label": user.primary_metric.replace("_", " "),
            "primary_target": user.daily_target_primary,
            "has_data": stats["days_logged"] > 0,
        },
    )
