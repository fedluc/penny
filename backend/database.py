from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    func,
    select,
    Index,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
    declarative_base,
    sessionmaker,
)

# ---------------- Base & helpers ----------------


def utcnow() -> datetime:
    # Always timezone-aware UTC
    return datetime.now(timezone.utc)


# ---------------- Tables ----------------
Base = declarative_base()
class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # reverse side of relationship
    cached_transactions: Mapped[List[TransactionCache]] = relationship(
        back_populates="category", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"Category(id={self.id}, name={self.name!r}, active={self.is_active})"


class TransactionCache(Base):
    __tablename__ = "transaction_cache"

    # SHA-256 hex -> 64 chars
    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    transaction: Mapped[Dict] = mapped_column(JSON, nullable=False)
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    category: Mapped[Category] = relationship(back_populates="cached_transactions")


# helpful composite index for exploration
Index(
    "ix_txcache_category_created",
    TransactionCache.category_id,
    TransactionCache.created_at.desc(),
)

# ---------------- Database ----------------
class Database:
    def __init__(self, db_url: str = "sqlite:///expense.db", echo: bool = False):
        # For FastAPI + threads, you might need check_same_thread=False on SQLite
        self.engine = create_engine(db_url, echo=echo, future=True)
        self.Session = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, future=True
        )
        Base.metadata.create_all(self.engine)
        self._seed_categories_if_empty()

        # ---- internal normalization & hashing ----
    @staticmethod
    def _normalize_tx(tx: Dict) -> str:
        # Stable, compact JSON
        return json.dumps(tx, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _hash(norm: str) -> str:
        import hashlib
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    # ---- cache API (no external key needed) ----
    def cache_lookup(self, tx: Dict) -> Optional[int]:
        norm = self._normalize_tx(tx)
        key = self._hash(norm)
        with self.Session() as s:
            row = s.get(TransactionCache, key)
            return row.category_id if row else None

    def cache_write(self, tx: Dict, category_id: int) -> None:
        norm = self._normalize_tx(tx)
        key = self._hash(norm)
        with self.Session() as s:
            row = s.get(TransactionCache, key)
            if row:
                row.transaction = norm
                row.category_id = category_id
            else:
                s.add(TransactionCache(hash=key, transaction=norm, category_id=category_id))
            s.commit()

    # ---- categories API ----
    def get_or_create_other(self) -> int:
        with self.Session() as s:
            row = s.query(Category).filter(Category.name.ilike("other")).first()
            if row:
                return row.id
            row = Category(name="other", description="Fallback category")
            s.add(row)
            s.commit()
            s.refresh(row)
            return row.id

    def get_active_category_names_with_other(self, limit: int = 50) -> tuple[list[str], int]:
        """
        Returns (active_names[:limit], other_id). Ensures 'other' exists and is active list fallback.
        """
        other_id = self.get_or_create_other()
        with self.Session() as s:
            names = [r.name for r in s.query(Category).filter(Category.is_active == True).order_by(Category.name).all()]
        if not names:
            names = ["other"]  # minimal safe set
        # Ensure 'other' is present in the presented list for the model (nice for clarity)
        if "other" not in {n.lower() for n in names}:
            names = names + ["other"]
        return names[:limit], other_id

    def resolve_category_id(self, name: str, fallback_other_id: Optional[int] = None) -> int:
        """
        Case-insensitive lookup. If not found, returns fallback_other_id or creates/returns 'other'.
        """
        with self.Session() as s:
            row = s.query(Category).filter(Category.name.ilike(name)).first()
            if row:
                return row.id
        if fallback_other_id is not None:
            return fallback_other_id
        return self.get_or_create_other()

    # -------- Seeding --------
    def _seed_categories_if_empty(self) -> None:
        seed = [
            ("groceries", "Supermarkets & food stores"),
            ("restaurants", "Dining & take-away"),
            ("transportation", "Taxis, rideshare, public transit"),
            ("utilities", "Electricity, water, internet, phone"),
            ("entertainment", "Movies, events, streaming"),
            ("pets", "Pet stores, vet, dog food"),
            ("health", "Pharmacy, clinics, sports"),
            ("shopping", "Retail & online shopping"),
            ("subscriptions", "Recurring services and memberships"),
            ("other", "Everything else / fallback"),
        ]
        with self.Session() as s:
            existing = set(n.lower() for n in s.scalars(select(Category.name)).all())
            to_add = [
                Category(name=n, description=d)
                for n, d in seed
                if n.lower() not in existing
            ]
            if to_add:
                s.add_all(to_add)
                s.commit()