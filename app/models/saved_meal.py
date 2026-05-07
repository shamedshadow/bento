from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SavedMeal(Base):
    __tablename__ = "saved_meals"
    __table_args__ = (
        CheckConstraint(
            "default_meal_type IS NULL OR default_meal_type IN "
            "('breakfast','lunch','dinner','snack')",
            name="ck_saved_meals_default_meal_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    default_meal_type: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    items: Mapped[list["SavedMealItem"]] = relationship(
        "SavedMealItem",
        back_populates="saved_meal",
        cascade="all, delete-orphan",
        order_by="SavedMealItem.display_order",
    )


class SavedMealItem(Base):
    __tablename__ = "saved_meal_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    saved_meal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("saved_meals.id", ondelete="CASCADE"),
        nullable=False,
    )
    food_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("foods.id"), nullable=False
    )
    amount_g: Mapped[float] = mapped_column(Float, nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    saved_meal: Mapped["SavedMeal"] = relationship(
        "SavedMeal", back_populates="items"
    )
