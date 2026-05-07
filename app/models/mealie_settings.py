from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MealieSettings(Base):
    """Singleton row (id=1) holding the homelab's Mealie integration config.
    App-level rather than per-user — Mealie is a shared homelab service and
    foods are shared across Bento users anyway.
    """

    __tablename__ = "mealie_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    api_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_sync_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
