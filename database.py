import json
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import (
    create_engine, Column, String, Text, Boolean, Integer, DateTime, ForeignKey
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# ---------------- SQLAlchemy ----------------
Base = declarative_base()
engine = create_engine("sqlite:///expense.db", echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# ---------------- Tables ----------------
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TransactionCache(Base):
    __tablename__ = "transaction_cache"
    hash = Column(String, primary_key=True)
    transaction = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category")

Base.metadata.create_all(engine)

# ---------------- Helpers ----------------
def _tx_key(tx: Dict) -> str:
    norm = json.dumps(tx, sort_keys=True)
    import hashlib
    return hashlib.sha256(norm.encode()).hexdigest()

def get_cached_category_id(key: str) -> Optional[int]:
    row = session.get(TransactionCache, key)
    return row.category_id if row else None

def put_cached_category_id(key: str, tx: Dict, category_id: int) -> None:
    session.add(TransactionCache(
        hash=key,
        transaction=json.dumps(tx, sort_keys=True),
        category_id=category_id
    ))
    session.commit()

def get_active_category_names() -> List[str]:
    rows = session.query(Category).filter(Category.is_active == True).all()
    return [r.name for r in rows]

def get_category_by_name(name: str) -> Optional[Category]:
    return session.query(Category).filter(Category.name.ilike(name)).first()

def ensure_other_exists() -> Category:
    row = get_category_by_name("other")
    if row:
        return row
    row = Category(name="other", description="Fallback category")
    session.add(row)
    session.commit()
    return row

def seed_categories_if_empty():
    if session.query(Category).count() == 0:
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
        for name, desc in seed:
            if not get_category_by_name(name):
                session.add(Category(name=name, description=desc))
        session.commit()