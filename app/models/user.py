from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

PRIMARY_METRICS = ("calories", "net_carbs", "total_carbs", "protein")
SECONDARY_TARGET_TYPES = ("min", "max")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "primary_metric IN ('calories','net_carbs','total_carbs','protein')",
            name="ck_users_primary_metric",
        ),
        CheckConstraint(
            "secondary_target_type IS NULL OR secondary_target_type IN ('min','max')",
            name="ck_users_secondary_target_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    primary_metric: Mapped[str] = mapped_column(String, nullable=False)
    daily_target_primary: Mapped[int] = mapped_column(Integer, nullable=False)
    secondary_metric: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    secondary_target: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    secondary_target_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    pin_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pin_set_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_pin_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pin_locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    timezone: Mapped[str] = mapped_column(
        String, nullable=False, default="America/New_York"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
