from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth.context import AuthContextMiddleware
from app.auth.setup_gate import SetupGateMiddleware
from app.config import settings
from app.db import engine
from app.routers import admin, auth_pages, entries, foods, pages, saved_meals, trends


@asynccontextmanager
async def lifespan(app: FastAPI):
    photos_dir = Path(settings.photos_dir)
    photos_dir.mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()


app = FastAPI(title="Bento", lifespan=lifespan)

app.add_middleware(AuthContextMiddleware)
app.add_middleware(SetupGateMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_pages.router)
app.include_router(admin.router)
app.include_router(foods.router)
app.include_router(entries.router)
app.include_router(saved_meals.router)
app.include_router(trends.router)
app.include_router(pages.router)

photos_dir = Path(settings.photos_dir)
photos_dir.mkdir(parents=True, exist_ok=True)
app.mount("/photos", StaticFiles(directory=str(photos_dir)), name="photos")

static_dir = Path("static")
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
