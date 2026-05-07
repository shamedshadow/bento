from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        CheckConstraint(
            "meal_type IS NULL OR meal_type IN ('breakfast','lunch','dinner','snack')",
            name="ck_entries_meal_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    food_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("foods.id"), nullable=False
    )
    amount_g: Mapped[float] = mapped_column(Float, nullable=False)
    meal_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
