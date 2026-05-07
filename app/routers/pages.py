from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.auth.deps import require_user
from app.models import User

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def home(
    request: Request,
    user: User = Depends(require_user),
):
    # Stub home page — F4 (daily log view) replaces this.
    return templates.TemplateResponse(
        request, "home.html", {"current_user": user}
    )
