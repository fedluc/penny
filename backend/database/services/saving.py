# database/services/expenses.py
from __future__ import annotations

from sqlalchemy.orm import Session
from database.repos.categories import CategoryRepo
from database.repos.expenses import ExpenseRepo


def save_expenses(
    s: Session,
    items: list[dict],
    *,
    dedupe_on_hash: bool = True,
) -> list[int]:
    """
    Persist multiple expenses within a single session/transaction.

    Each item must have:
      - date: datetime.date
      - description: str
      - amount: float
      - category_id: Optional[int]
      - category: Optional[str]  (used if category_id missing)

    Returns inserted (or deduped) row ids in order.
    """
    cat_repo = CategoryRepo(s)
    exp_repo = ExpenseRepo(s)
    other_id = cat_repo.get_or_create_other()
    inserted: list[int] = []
    for item in items:
        if item.get("category_id") is not None:
            cat_id = int(item["category_id"])
        elif item.get("category"):
            cat_id = cat_repo.resolve_id(item["category"], fallback_other_id=other_id)
        else:
            cat_id = other_id
        raw = {
            "date": item["date"].isoformat(),
            "description": item["description"],
            "amount": float(item["amount"]),
            "category": item.get("category"),
            "category_id": cat_id,
        }
        new_id = exp_repo.add(
            date=item["date"],
            amount=float(item["amount"]),
            description=item["description"],
            category_id=cat_id,
            raw=raw,
            dedupe_on_hash=dedupe_on_hash,
        )
        inserted.append(new_id)

    return inserted
