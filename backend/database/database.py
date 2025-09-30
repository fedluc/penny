from __future__ import annotations

from datetime import date as DateOnly

from sqlalchemy import and_, event, func, select
from database.engine import make_engine, make_session_factory
from database.tables import Base, Category, Expense, ClassificationCache
from database.services.hashing import normalize_for_hash, hash

DEFAULT_DB_URL = "sqlite:///expense.db"

class Database:
    def __init__(self, db_url: str = DEFAULT_DB_URL, echo: bool = False):
        self.engine = make_engine(db_url, echo=echo)
        self.Session = make_session_factory(self.engine)
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
                norm = normalize_for_hash(raw)
                hash_val = hash(norm)
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

    def cache_lookup(self, tx: dict) -> int | None:
        norm = normalize_for_hash(tx)
        key = hash(norm)
        with self.Session() as s:
            row = s.get(ClassificationCache, key)
            return int(row.category_id) if row else None

    def cache_write(self, tx: dict, category_id: int) -> None:
        norm = normalize_for_hash(tx)
        key = hash(norm)
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

    def get_expenses_between(
        self,
        start_date: DateOnly,
        end_date: DateOnly,
        *,
        category: int | str | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str = "asc",  # "asc" or "desc" by date
    ) -> list[dict]:
        """
        Return expenses within [start_date, end_date], optionally filtered by category.
        'category' can be a category_id (int) or a case-insensitive category name (str).
        Results are ordered by date then id (stable), and returned as JSON-friendly dicts.
        """
        if order not in {"asc", "desc"}:
            order = "asc"
        with self.Session() as s:
            # Resolve category (if provided)
            category_id: int | None = None
            if isinstance(category, int):
                category_id = category
            elif isinstance(category, str):
                category_id = self.resolve_category_id(category)
            stmt = (
                select(
                    Expense.id,
                    Expense.date,
                    Expense.amount,
                    Expense.description,
                    Expense.category_id,
                    Category.name.label("category_name"),
                )
                .join(Category, Category.id == Expense.category_id)
                .where(Expense.date.between(start_date, end_date))
            )
            if category_id is not None:
                stmt = stmt.where(Expense.category_id == category_id)
            if order == "asc":
                stmt = stmt.order_by(Expense.date.asc(), Expense.id.asc())
            else:
                stmt = stmt.order_by(Expense.date.desc(), Expense.id.desc())
            if limit is not None:
                stmt = stmt.limit(limit).offset(offset)
            rows = s.execute(stmt).all()
            return [
                {
                    "id": r.id,
                    "date": r.date,
                    "amount": float(r.amount),
                    "description": r.description,
                    "category_id": r.category_id,
                    "category_name": r.category_name,
                }
                for r in rows
            ]

    def sum_for_category_between(
        self,
        category: int | str,
        start_date: DateOnly,
        end_date: DateOnly,
    ) -> float:
        """
        Sum 'amount' for a single category within [start_date, end_date].
        'category' can be an id (int) or a case-insensitive name (str).
        Returns 0.0 if there are no matching rows.
        """
        with self.Session() as s:
            # Resolve category id
            if isinstance(category, int):
                category_id = category
            else:
                category_id = self.resolve_category_id(category)
            stmt = (
                select(func.coalesce(func.sum(Expense.amount), 0.0))
                .where(Expense.category_id == category_id)
                .where(Expense.date.between(start_date, end_date))
            )
            total = s.execute(stmt).scalar_one()
            # Ensure a float is returned
            return float(total or 0.0)

    def get_expenses_between(
        self,
        start_date: DateOnly,
        end_date: DateOnly,
        *,
        category: int | str | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str = "asc",  # "asc" or "desc" by date
    ) -> list[dict]:
        """
        Return expenses within [start_date, end_date], optionally filtered by category.
        'category' can be a category_id (int) or a case-insensitive category name (str).
        Results are ordered by date then id (stable), and returned as JSON-friendly dicts.
        """
        if order not in {"asc", "desc"}:
            order = "asc"
        with self.Session() as s:
            category_id: int | None = None
            if isinstance(category, int):
                category_id = category
            elif isinstance(category, str):
                category_id = self.resolve_category_id(category)
            stmt = (
                select(
                    Expense.id,
                    Expense.date,
                    Expense.amount,
                    Expense.description,
                    Expense.category_id,
                    Category.name.label("category_name"),
                )
                .join(Category, Category.id == Expense.category_id)
                .where(Expense.date.between(start_date, end_date))
            )
            if category_id is not None:
                stmt = stmt.where(Expense.category_id == category_id)
            if order == "asc":
                stmt = stmt.order_by(Expense.date.asc(), Expense.id.asc())
            else:
                stmt = stmt.order_by(Expense.date.desc(), Expense.id.desc())
            if limit is not None:
                stmt = stmt.limit(limit).offset(offset)
            rows = s.execute(stmt).all()
            return [
                {
                    "id": r.id,
                    "date": r.date,  # a datetime.date object; stringify in your API if needed
                    "amount": float(r.amount),
                    "description": r.description,
                    "category_id": r.category_id,
                    "category_name": r.category_name,
                }
                for r in rows
            ]

    def totals_by_category_between(
        self,
        start_date: DateOnly,
        end_date: DateOnly,
        *,
        only_active: bool | None = True,
        include_zero: bool = False,
        order: str = "desc",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """
        Return per-category totals within [start_date, end_date].

        - only_active=True  -> include only active categories
          only_active=False -> include only inactive categories
          only_active=None  -> include all categories
        - include_zero=True -> include categories with zero spend in the range (LEFT JOIN)
        - order: 'desc' | 'asc' | 'name_asc'
        """
        with self.Session() as s:
            total_expr = func.coalesce(func.sum(Expense.amount), 0.0).label("total")
            if include_zero:
                # LEFT JOIN Category -> Expense with date filter in the ON clause
                j = Category.__table__.outerjoin(
                    Expense.__table__,
                    and_(
                        Expense.category_id == Category.id,
                        Expense.date.between(start_date, end_date),
                    ),
                )
                stmt = select(
                    Category.id.label("category_id"),
                    Category.name.label("category_name"),
                    Category.is_active.label("is_active"),
                    total_expr,
                ).select_from(j)
            else:
                # INNER JOIN + WHERE on date
                stmt = (
                    select(
                        Category.id.label("category_id"),
                        Category.name.label("category_name"),
                        Category.is_active.label("is_active"),
                        total_expr,
                    )
                    .join(Expense, Expense.category_id == Category.id)
                    .where(Expense.date.between(start_date, end_date))
                )
            # Filter by active/inactive if requested
            if only_active is True:
                stmt = stmt.where(Category.is_active.is_(True))
            elif only_active is False:
                stmt = stmt.where(Category.is_active.is_(False))
            # Group and order
            stmt = stmt.group_by(Category.id, Category.name, Category.is_active)
            if order == "asc":
                stmt = stmt.order_by(total_expr.asc(), Category.name.asc())
            else:
                stmt = stmt.order_by(total_expr.desc(), Category.name.asc())
            if limit is not None:
                stmt = stmt.limit(limit).offset(offset)
            rows = s.execute(stmt).all()
            return [
                {
                    "category_id": r.category_id,
                    "category_name": r.category_name,
                    "is_active": bool(r.is_active),
                    "total": float(r.total or 0.0),
                }
                for r in rows
            ]
