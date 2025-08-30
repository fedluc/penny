import os
import json
import hashlib
import difflib
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import (
    create_engine, Column, String, Text, Boolean, Integer, ForeignKey, DateTime, UniqueConstraint
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

import openai

# ---------- OpenAI ----------
api_key = os.environ.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)
MODEL = "gpt-4.1-mini"

# ---------- SQLAlchemy ----------
Base = declarative_base()
engine = create_engine("sqlite:///expense.db", echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# ---------- Tables ----------
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    aliases = relationship("CategoryAlias", back_populates="category", cascade="all, delete-orphan")

class CategoryAlias(Base):
    __tablename__ = "category_aliases"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    alias = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint("alias", name="uq_alias_unique"),)

    category = relationship("Category", back_populates="aliases")

class TransactionCache(Base):
    __tablename__ = "transaction_cache"
    hash = Column(String, primary_key=True)
    transaction = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category")

Base.metadata.create_all(engine)

# ---------- Utility: category admin ----------
def ensure_category(name: str, description: Optional[str] = None) -> Category:
    row = session.query(Category).filter(Category.name.ilike(name)).first()
    if row:
        return row
    row = Category(name=name.strip(), description=description or "")
    session.add(row)
    session.commit()
    return row

def add_alias(category_name: str, alias: str):
    cat = session.query(Category).filter(Category.name.ilike(category_name)).first()
    if not cat:
        raise ValueError(f"Category '{category_name}' not found")
    alias = alias.strip()
    if session.query(CategoryAlias).filter(CategoryAlias.alias.ilike(alias)).first():
        return
    session.add(CategoryAlias(category_id=cat.id, alias=alias))
    session.commit()

# ---------- Seed (run once if you want) ----------
def seed_categories_if_empty():
    if session.query(Category).count() == 0:
        for name, desc, alias_list in [
            ("groceries", "Supermarkets & food stores", ["supermarket", "food shop", "ICA", "Coop", "Willys"]),
            ("restaurants", "Dining & take-away", ["restaurant", "dining", "cafe"]),
            ("transportation", "Taxis, rideshare, public transit", ["uber", "taxi", "ride", "bus", "train"]),
            ("utilities", "Electricity, water, internet, phone", ["electricity", "internet", "telia"]),
            ("entertainment", "Movies, events, streaming", ["cinema", "movie", "tickets", "concert"]),
            ("pets", "Pet stores, vet, dog food", ["dog", "cat", "petstore", "zoo"]),
            ("health", "Pharmacy, clinics, sports", ["pharmacy", "doctor", "gym"]),
            ("shopping", "Retail & online shopping", ["retail", "online", "store"]),
            ("subscriptions", "Recurring services/memberships", ["subscription", "membership"]),
            ("other", "Everything else", ["misc", "uncategorized"]),
        ]:
            cat = ensure_category(name, desc)
            for a in alias_list:
                add_alias(name, a)

# ---------- Hashing & Cache ----------
def _tx_key(tx: Dict) -> str:
    norm = json.dumps(tx, sort_keys=True)
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

# ---------- Category lookup & matching ----------
def _load_category_index() -> Tuple[List[Category], dict]:
    """
    Returns:
      - active categories
      - a dict of lowercase name/alias -> Category
    """
    cats = session.query(Category).filter(Category.is_active == True).all()
    index = {}
    for c in cats:
        index[c.name.lower()] = c
        for a in c.aliases:
            index[a.alias.lower()] = c
    return cats, index

def resolve_category_name_to_row(name_from_model: str) -> Category:
    """
    Map free-text category name into a Category row via:
      1) exact case-insensitive match on name
      2) alias match
      3) fuzzy best match on existing names (not aliases) if very close
      4) fallback to 'other' (create if missing)
    """
    cats, index = _load_category_index()
    if not cats:
        # Create a minimal 'other' if DB is empty
        return ensure_category("other", "Fallback category")

    candidate = (name_from_model or "").strip().lower()
    if candidate in index:
        return index[candidate]

    # fuzzy on canonical names
    names = [c.name.lower() for c in cats]
    close = difflib.get_close_matches(candidate, names, n=1, cutoff=0.75)
    if close:
        for c in cats:
            if c.name.lower() == close[0]:
                return c

    # final fallback
    return ensure_category("other", "Fallback category")

# ---------- GPT classifier (no hard-coded enums) ----------
def classify_transaction(tx: Dict) -> int:
    """
    Returns a category_id. Uses DB-backed categories and caches results by tx hash.
    """
    key = _tx_key(tx)
    cached_id = get_cached_category_id(key)
    if cached_id is not None:
        return cached_id

    # Build a compact hint list from DB to guide the model (purely informational).
    active_cats = session.query(Category).filter(Category.is_active == True).all()
    if not active_cats:
        ensure_category("other", "Fallback category")
        active_cats = session.query(Category).filter(Category.is_active == True).all()

    # Short, readable hint list
    lines = []
    for c in active_cats:
        kws = [a.alias for a in c.aliases][:6]  # keep prompt short
        hint = f"- {c.name}" + (f" (e.g., {', '.join(kws)})" if kws else "")
        lines.append(hint)
    hints = "\n".join(lines)

    system_prompt = (
        "You classify bank transactions into exactly ONE category from the list below.\n"
        "Return the category NAME only (no extra text).\n\n"
        "Available categories:\n"
        f"{hints if hints else '- other'}"
    )

    # Let the model return a plain string; we’ll map it to a DB row.
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Transaction: {json.dumps(tx)}"}
        ],
        # No function/enum constraint; free text keeps DB truly authoritative.
        temperature=0  # be deterministic
    )

    name = (resp.choices[0].message.content or "").strip()
    cat_row = resolve_category_name_to_row(name)
    put_cached_category_id(key, tx, cat_row.id)
    return cat_row.id

# ---------- Example usage ----------
if __name__ == "__main__":
    # Uncomment once to seed some starter categories/aliases
    seed_categories_if_empty()
    
    transactions = [
        {"date": "2025-06-01", "description": "ICA 45.67", "amount": -45.67},
        {"date": "2025-06-05", "description": "DINNER 30.00", "amount": -30.00},
        {"date": "2025-06-07", "description": "UBER RIDE 15.50", "amount": -15.50},
        {"date": "2025-06-08", "description": "ELECTRICITY BILL 75.00", "amount": -75.00},
        {"date": "2025-06-09", "description": "MOVIE TICKETS 20.00", "amount": -20.00},
        {"date": "2025-06-10", "description": "PETSMART DOG FOOD 23.99", "amount": -23.99},
    ]

    for tx in transactions:
        cid = classify_transaction(tx)
        cname = session.get(Category, cid).name
        print(f"{tx['description']} → {cname} (id={cid})")
