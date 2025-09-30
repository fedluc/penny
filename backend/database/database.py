from __future__ import annotations

from database.engine import make_engine, make_session_factory
from database.repos.categories import CategoryRepo
from database.repos.expenses import ExpenseRepo
from database.repos.cache import ClassificationCacheRepo
from database.services.seed import ensure_seed
from database.services.reporting import totals_by_category_between
from database.tables import Base

DEFAULT_DB_URL = "sqlite:///expense.db"


class Database:
    def __init__(self, db_url: str = DEFAULT_DB_URL, echo: bool = False):
        self.engine = make_engine(db_url, echo=echo)
        self.Session = make_session_factory(self.engine)
        Base.metadata.create_all(self.engine)
        with self.Session() as s:
            ensure_seed(s)

    def get_or_create_other(self) -> int:
        with self.Session() as s:
            return CategoryRepo(s).get_or_create_other()

    def get_active_category_names_with_other(self, limit: int = 50):
        with self.Session() as s:
            return CategoryRepo(s).active_names_with_other(limit)

    def resolve_category_id(
        self, name: str, fallback_other_id: int | None = None
    ) -> int:
        with self.Session() as s:
            repo = CategoryRepo(s)
            return repo.resolve_id(name, fallback_other_id)

    def add_expense(self, **kwargs) -> int:
        with self.Session() as s:
            exp_repo = ExpenseRepo(s)
            return exp_repo.add(**kwargs)

    def get_expenses_between(self, *args, **kwargs) -> list[dict]:
        with self.Session() as s:
            exp_repo = ExpenseRepo(s)
            # Resolve category name here if you want the same API as before
            cat = kwargs.pop("category", None)
            if isinstance(cat, str):
                category_id = CategoryRepo(s).resolve_id(cat)
            elif isinstance(cat, int):
                category_id = cat
            else:
                category_id = None
            return exp_repo.between(*args, category_id=category_id, **kwargs)

    def cache_lookup(self, tx: dict) -> int | None:
        with self.Session() as s:
            return ClassificationCacheRepo(s).lookup(tx)

    def cache_write(self, tx: dict, category_id: int) -> None:
        with self.Session() as s:
            ClassificationCacheRepo(s).write(tx, category_id)

    def sum_for_category_between(self, category, start_date, end_date) -> float:
        with self.Session() as s:
            if isinstance(category, str):
                category_id = CategoryRepo(s).resolve_id(category)
            else:
                category_id = int(category)
            return ExpenseRepo(s).sum_for_category(category_id, start_date, end_date)

    def totals_by_category_between(self, *args, **kwargs) -> list[dict]:
        with self.Session() as s:
            return totals_by_category_between(s, *args, **kwargs)
