from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DiscordSettings(Base):
    __tablename__ = "discord_settings"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    webhook_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    meal_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # JSON-encoded list of "HH:MM" strings.
    meal_reminders_times: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )

    eod_summary_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    eod_summary_time: Mapped[str] = mapped_column(
        String, nullable=False, default="21:00"
    )

    weekly_summary_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Sunday=0 ... Saturday=6
    weekly_summary_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    log_nudge_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    log_nudge_after_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=6
    )

    # Auto-disable after 3 consecutive failed sends (set by F8 scheduler).
    auto_disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
