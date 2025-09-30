from database.repos.base import BaseRepo
from database.tables import ClassificationCache
from database.services.hashing import hash


class ClassificationCacheRepo(BaseRepo):
    def lookup(self, tx: dict) -> int | None:
        key = hash(tx)
        row = self.s.get(ClassificationCache, key)
        return int(row.category_id) if row else None

    def write(self, tx: str, category_id: int) -> None:
        key = hash(tx)
        existing = self.s.get(ClassificationCache, key)
        if existing:
            existing.category_id = int(category_id)
        else:
            self.s.add(ClassificationCache(hash=key, category_id=int(category_id)))
        self.s.commit()
