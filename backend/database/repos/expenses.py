from sqlalchemy import select, func
from database.repos.base import BaseRepo
from database.tables import Expense, Category
from database.services.hashing import hash
from datetime import date as DateOnly


class ExpenseRepo(BaseRepo):
    def add(
        self,
        *,
        date: DateOnly,
        amount: float,
        description: str,
        category_id: int,
        raw: dict | None = None,
        dedupe_on_hash: bool = True,
    ) -> int:
        hash_val = self._key_for_raw(raw)
        if dedupe_on_hash and hash_val:
            existing_id = self._find_id_by_hash(hash_val)
            if existing_id:
                return existing_id
        exp = Expense(
            date=date,
            amount=amount,
            description=description or "",
            category_id=category_id,
            hash=hash_val,
        )
        self.s.add(exp)
        self.s.commit()
        self.s.refresh(exp)
        print(f"Added expense: {exp}")
        return exp.id

    def between(
        self,
        start: DateOnly,
        end: DateOnly,
        category_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str = "asc",
    ) -> list[dict]:
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
            .where(Expense.date.between(start, end))
        )
        if category_id is not None:
            stmt = stmt.where(Expense.category_id == category_id)
        stmt = (
            stmt.order_by(Expense.date.asc(), Expense.id.asc())
            if order != "desc"
            else stmt.order_by(Expense.date.desc(), Expense.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        rows = self.s.execute(stmt).all()
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

    def sum_for_category(
        self, category_id: int, start: DateOnly, end: DateOnly
    ) -> float:
        stmt = (
            select(func.coalesce(func.sum(Expense.amount), 0.0))
            .where(Expense.category_id == category_id)
            .where(Expense.date.between(start, end))
        )
        return float(self.s.execute(stmt).scalar_one() or 0.0)

    def _key_for_raw(self, raw: dict | None) -> str | None:
        return hash(raw) if raw else None

    def _find_id_by_hash(self, key: str) -> int | None:
        row = self.s.execute(select(Expense.id).where(Expense.hash == key)).first()
        return int(row[0]) if row else None
