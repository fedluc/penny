from database.repos.base import BaseRepo
from database.tables import Category


class CategoryRepo(BaseRepo):
    def get_or_create_other(self) -> int:
        row = self.s.query(Category).filter(Category.name.ilike("other")).first()
        if row:
            return row.id
        row = Category(name="other", description="Fallback category")
        self.s.add(row)
        self.s.commit()
        self.s.refresh(row)
        return row.id

    def resolve_id(self, name: str, fallback_other_id: int | None = None) -> int:
        row = self.s.query(Category).filter(Category.name.ilike(name)).first()
        if row:
            return row.id
        return (
            fallback_other_id
            if fallback_other_id is not None
            else self.get_or_create_other()
        )

    def active_names_with_other(self, limit: int = 50) -> tuple[list[str], int]:
        other_id = self.get_or_create_other()
        names = [
            r.name
            for r in self.s.query(Category)
            .filter(Category.is_active.is_(True))
            .order_by(Category.name)
            .all()
        ] or ["other"]
        if "other" not in {n.lower() for n in names}:
            names.append("other")
        return names[:limit], other_id
