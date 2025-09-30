from sqlalchemy import and_, select, func
from sqlalchemy.orm import Session
from database.tables import Expense, Category


def totals_by_category_between(
    s: Session,
    start_date,
    end_date,
    *,
    only_active: bool | None = True,
    include_zero: bool = False,
    order: str = "desc",
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    total_expr = func.coalesce(func.sum(Expense.amount), 0.0).label("total")
    if include_zero:
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

    if only_active is True:
        stmt = stmt.where(Category.is_active.is_(True))
    elif only_active is False:
        stmt = stmt.where(Category.is_active.is_(False))

    stmt = stmt.group_by(Category.id, Category.name, Category.is_active)
    stmt = (
        stmt.order_by(total_expr.asc(), Category.name.asc())
        if order == "asc"
        else stmt.order_by(total_expr.desc(), Category.name.asc())
    )
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
