from __future__ import annotations

from datetime import datetime, timezone, date as DateOnly

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
    Float,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
    declarative_base,
)

# ---------------- Base & helpers ----------------

def utcnow() -> datetime:
    # Always timezone-aware UTC
    return datetime.now(timezone.utc)


Base = declarative_base()

# ---------------- Tables ----------------


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # reverse side of relationship (renamed from cached_transactions)
    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="category", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"Category(id={self.id}, name={self.name!r}, active={self.is_active})"


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Common analytics fields promoted out of JSON
    date: Mapped[DateOnly] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(
        Float, nullable=False, index=True
    )  # use cents(int) if you prefer exactness
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Category link
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # For dedupe (based on normalized raw/fields). Keep unique if you like idempotency.
    hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    category: Mapped["Category"] = relationship(back_populates="expenses")

    def __repr__(self) -> str:
        return f"Expense(id={self.id}, date={self.date}, amount={self.amount}, category_id={self.category_id})"


# Helpful indexes for exploration/analytics
Index("ix_expenses_category_date", Expense.category_id, Expense.date.desc())
Index("ix_expenses_category_amount", Expense.category_id, Expense.amount.desc())


class ClassificationCache(Base):
    __tablename__ = "classification_cache"
    # hash of the normalized tx payload
    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("hash", name="uq_classification_cache_hash"),)