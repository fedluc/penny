from __future__ import annotations
from datetime import date as DateOnly

from database.engine import make_engine, make_session_factory
from database.repos.categories import CategoryRepo
from database.repos.expenses import ExpenseRepo
from database.repos.cache import ClassificationCacheRepo
from database.services.seed import ensure_seed
from database.services.reporting import (
    ResultOrder,
    totals_by_category as totals_by_category_service,
)
from database.services.saving import save_expenses as save_expenses_service
from database.tables import Base

DEFAULT_DB_URL = "sqlite:///expense.db"


class Database:
    def __init__(self, db_url: str = DEFAULT_DB_URL, echo: bool = False):
        self.engine = make_engine(db_url, echo=echo)
        self.Session = make_session_factory(self.engine)
        Base.metadata.create_all(self.engine)
        with self.Session() as s:
            ensure_seed(s)

    # ---------------- Category helpers ----------------
    def get_or_create_other(self) -> int:
        with self.Session() as s:
            return CategoryRepo(s).get_or_create_other()

    def get_active_category_names_with_other(
        self, limit: int = 50
    ) -> tuple[list[str], int]:
        with self.Session() as s:
            return CategoryRepo(s).active_names_with_other(limit)

    def resolve_category_id(
        self, name: str, fallback_other_id: int | None = None
    ) -> int:
        with self.Session() as s:
            return CategoryRepo(s).resolve_id(name, fallback_other_id)

    # ---------------- Expenses ----------------
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
        Insert an expense. If raw and dedupe_on_hash=True, compute a stable hash
        of raw and avoid inserting duplicates (returns existing id instead).
        """
        with self.Session() as s:
            return ExpenseRepo(s).add_with_dedupe(
                date=date,
                amount=amount,
                description=description,
                category_id=category_id,
                raw=raw,
                dedupe_on_hash=dedupe_on_hash,
            )

    def save_expenses(
        self, items: list[dict], *, dedupe_on_hash: bool = True
    ) -> list[int]:
        """
        Saves a list of expense items to the database.
        """
        with self.Session() as s:
            return save_expenses_service(s, items, dedupe_on_hash=dedupe_on_hash)

    def list_expenses(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        since: DateOnly | None = None,
    ) -> list[dict]:
        """
        Return stored expenses, most recent first by date, amount desc, id desc.
        Dict keys: date (YYYY-MM-DD), description, amount, category, created_at (ISO or None).
        """
        with self.Session() as s:
            rows = ExpenseRepo(s).list_recent(limit=limit, offset=offset, since=since)
            return rows

    def get_expenses_between(
        self,
        start_date: DateOnly,
        end_date: DateOnly,
        *,
        category: int | str = None,
        limit: int | None = None,
        offset: int = 0,
        order: ResultOrder = ResultOrder.DESC,
    ) -> list[dict]:
        """
        Return expenses within [start_date, end_date], optionally filtered by category
        (id or name). Ordered by date then id. Returns JSON-friendly dicts.
        """
        with self.Session() as s:
            category_id: int | None = None
            if isinstance(category, int):
                category_id = category
            elif isinstance(category, str):
                category_id = CategoryRepo(s).resolve_id(category)

            return ExpenseRepo(s).between(
                start=start_date,
                end=end_date,
                category_id=category_id,
                limit=limit,
                offset=offset,
                order=order,
            )

    def sum_for_category_between(
        self,
        category: int | str,
        start_date: DateOnly,
        end_date: DateOnly,
    ) -> float:
        """
        Sum 'amount' for a single category (id or name) within [start_date, end_date].
        """
        with self.Session() as s:
            category_id = (
                category
                if isinstance(category, int)
                else CategoryRepo(s).resolve_id(category)
            )
            return ExpenseRepo(s).sum_for_category(category_id, start_date, end_date)

    # ---------------- Cache ----------------
    def cache_lookup(self, tx: dict) -> int | None:
        """Return cached category_id for a normalized tx payload, or None."""
        with self.Session() as s:
            return ClassificationCacheRepo(s).lookup(tx)

    def cache_write(self, tx: dict, category_id: int) -> None:
        """Write/overwrite cache entry for a tx payload -> category_id."""
        with self.Session() as s:
            ClassificationCacheRepo(s).write(tx, category_id)

    # ---------------- Reporting ----------------
    def totals_by_category(
        self,
        start_date: DateOnly,
        end_date: DateOnly,
        *,
        only_active: bool = True,
        include_zero: bool = False,
        order: ResultOrder = ResultOrder.DESC,  # "desc" | "asc"
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """
        Per-category totals within [start_date, end_date].
        - only_active: True (only active), False (only inactive), None (all)
        - include_zero: include categories with zero spend
        - order: by amount desc/asc or by name
        """
        with self.Session() as s:
            return totals_by_category_service(
                s,
                start_date,
                end_date,
                only_active=only_active,
                include_zero=include_zero,
                order=order,
                limit=limit,
                offset=offset,
            )
