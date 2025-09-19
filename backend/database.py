from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone, date as DateOnly

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    select,
    Index,
    Float,
    UniqueConstraint,
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


# ---------------- Database ----------------


class Database:
    def __init__(self, db_url: str = "sqlite:///expense.db", echo: bool = False):
        # For FastAPI + threads, you might need check_same_thread=False on SQLite
        self.engine = create_engine(
            db_url,
            echo=echo,
            future=True,
            connect_args=(
                {"check_same_thread": False} if db_url.startswith("sqlite") else {}
            ),
        )

        # Register PRAGMAs BEFORE any connections are used (i.e., before create_all)
        if db_url.startswith("sqlite"):
            self._apply_sqlite_pragmas()

        self.Session = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, future=True
        )
        Base.metadata.create_all(self.engine)
        self._seed_categories_if_empty()

    # ---- SQLite pragmas ----
    def _apply_sqlite_pragmas(self):
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=2000;")
            cursor.execute("PRAGMA temp_store=MEMORY;")
            cursor.close()

    # ---- Hash helpers (optional, for dedupe/idempotency) ----
    @staticmethod
    def _normalize_for_hash(payload: dict) -> str:
        # Stable, compact JSON
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _hash(norm: str) -> str:
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    # ---- Category helpers (unchanged) ----
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

    def get_active_category_names_with_other(
        self, limit: int = 50
    ) -> tuple[list[str], int]:
        """
        Returns (active_names[:limit], other_id). Ensures 'other' exists and is active list fallback.
        """
        other_id = self.get_or_create_other()
        with self.Session() as s:
            names = [
                r.name
                for r in s.query(Category)
                .filter(Category.is_active.is_(True))
                .order_by(Category.name)
                .all()
            ]
        if not names:
            names = ["other"]  # minimal safe set
        if "other" not in {n.lower() for n in names}:
            names = names + ["other"]
        return names[:limit], other_id

    def resolve_category_id(
        self, name: str, fallback_other_id: int | None = None
    ) -> int:
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

    # ---- Expense API (minimal; add more as you need) ----
    def add_expense(
        self,
        *,
        date: DateOnly,
        amount: float,
        description: str,
        category_id: int,
        raw: dict | None = None,
        dedupe_on_hash: bool = True,
    ) -> int:
        """
        Insert a new expense. If dedupe_on_hash=True and 'raw' is provided,
        compute a hash and avoid inserting duplicates.
        Returns the inserted row id.
        """
        with self.Session() as s:
            hash_val = None
            if dedupe_on_hash and raw is not None:
                norm = self._normalize_for_hash(raw)
                hash_val = self._hash(norm)
                existing = s.query(Expense.id).filter(Expense.hash == hash_val).first()
                if existing:
                    return existing[0]

            exp = Expense(
                date=date,
                amount=amount,
                description=description or "",
                category_id=category_id,
                hash=hash_val,
            )
            s.add(exp)
            s.commit()
            s.refresh(exp)
            return exp.id

    @staticmethod
    def _normalize_for_hash(payload: dict) -> str:
        import json

        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _hash(norm: str) -> str:
        import hashlib

        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def cache_lookup(self, tx: dict) -> int | None:
        norm = self._normalize_for_hash(tx)
        key = self._hash(norm)
        with self.Session() as s:
            row = s.get(ClassificationCache, key)
            return int(row.category_id) if row else None

    def cache_write(self, tx: dict, category_id: int) -> None:
        norm = self._normalize_for_hash(tx)
        key = self._hash(norm)
        with self.Session() as s:
            existing = s.get(ClassificationCache, key)
            if existing:
                existing.category_id = int(category_id)
            else:
                s.add(ClassificationCache(hash=key, category_id=int(category_id)))
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
