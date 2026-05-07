from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_user
from app.db import get_session
from app.models import User
from app.services import export as export_svc

router = APIRouter()


def _parse_day(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"Invalid date: {value!r} (expected YYYY-MM-DD)")


@router.get("/export")
async def export_csv(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    start_day = _parse_day(start)
    end_day = _parse_day(end)
    if start_day and end_day and start_day > end_day:
        raise HTTPException(400, "start must be on or before end")

    filename = export_svc.filename_for(user)
    return StreamingResponse(
        export_svc.stream_entries_csv(
            db, user, start_day=start_day, end_day=end_day
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
