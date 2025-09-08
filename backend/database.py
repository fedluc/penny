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

    # -------- Keys & hashing --------
    def tx_key(self, tx: Dict) -> str:
        norm = json.dumps(tx, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    # -------- Categories --------
    def get_active_category_names(self) -> List[str]:
        with self.Session() as s:
            rows = s.scalars(
                select(Category.name)
                .where(Category.is_active.is_(True))
                .order_by(Category.name)
            ).all()
            return list(rows)

    def get_category_by_name(self, name: str) -> Optional[Category]:
        # case-insensitive lookup
        with self.Session() as s:
            stmt = (
                select(Category)
                .where(func.lower(Category.name) == func.lower(name))
                .limit(1)
            )
            return s.scalars(stmt).first()

    def ensure_other_exists(self) -> Category:
        with self.Session() as s:
            stmt = select(Category).where(func.lower(Category.name) == "other").limit(1)
            cat = s.scalars(stmt).first()
            if cat:
                return cat
            cat = Category(name="other", description="Fallback category")
            s.add(cat)
            s.commit()
            s.refresh(cat)
            return cat

    # -------- Cache --------
    def get_cached_category_id(self, key: str) -> Optional[int]:
        with self.Session() as s:
            row = s.get(TransactionCache, key)
            return row.category_id if row else None

    def put_cached_category_id(self, key: str, tx: Dict, category_id: int) -> None:
        # Upsert via merge on PK
        with self.Session() as s:
            s.merge(TransactionCache(hash=key, transaction=tx, category_id=category_id))
            s.commit()

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