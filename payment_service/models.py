# payment_service/models.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    String, Integer, Text, CheckConstraint, Enum, ForeignKey, Index,
    UniqueConstraint, text
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import TIMESTAMP
from .database import Base
import enum


class OrderStatus(str, enum.Enum):
    INIT = "INIT"
    HOLD = "HOLD"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    total_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    sold_qty: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        CheckConstraint("total_qty >= 0", name="ck_events_total_nonneg"),
        CheckConstraint("sold_qty >= 0", name="ck_events_sold_nonneg"),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id"), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="order_status"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_orders_qty_pos"),
        UniqueConstraint("event_id", "idempotency_key", name="uq_orders_event_idem"),
        Index("idx_orders_event_status", "event_id", "status"),
    )


class Hold(Base):
    __tablename__ = "holds"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_holds_qty_pos"),
        Index("idx_holds_event_expires", "event_id", "expires_at"),
    )
