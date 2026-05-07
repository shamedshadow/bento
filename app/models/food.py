from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

FOOD_SOURCES = ("openfoodfacts", "usda", "custom")


class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_foods_source_id"),
        CheckConstraint(
            "source IN ('openfoodfacts','usda','custom')",
            name="ck_foods_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    default_serving_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    default_serving_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    calories_per_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs_per_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fiber_per_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein_per_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_per_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sugar_per_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sodium_per_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    photo_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    @property
    def net_carbs_per_100g(self) -> Optional[float]:
        if self.carbs_per_100g is None:
            return None
        fiber = self.fiber_per_100g or 0.0
        return max(0.0, self.carbs_per_100g - fiber)
