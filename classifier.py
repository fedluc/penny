import os
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import (
    create_engine, Column, String, Text, Boolean, Integer, DateTime, ForeignKey
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

import openai

# ---------------- OpenAI ----------------
api_key = os.environ.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)
MODEL = "gpt-4.1-mini"

# ---------------- SQLAlchemy ----------------
Base = declarative_base()
engine = create_engine("sqlite:///expense.db", echo=False)
Session = sessionmaker(bind=engine)
session = Session()

# ---------------- Tables ----------------
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)  # canonical display name
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TransactionCache(Base):
    __tablename__ = "transaction_cache"
    hash = Column(String, primary_key=True)
    transaction = Column(Text)                              # normalized JSON
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
    # case-insensitive exact match
    return session.query(Category).filter(Category.name.ilike(name)).first()

def ensure_other_exists() -> Category:
    row = get_category_by_name("other")
    if row:
        return row
    row = Category(name="other", description="Fallback category")
    session.add(row)
    session.commit()
    return row

# ---------------- Classifier ----------------
def classify_transaction(tx: Dict) -> int:
    """
    Returns a category_id (int). Uses DB categories to constrain the model via function-calling.
    Caches by transaction hash.
    """
    key = _tx_key(tx)
    cached = get_cached_category_id(key)
    if cached is not None:
        return cached

    # Load categories from DB; ensure there's at least a fallback
    categories = get_active_category_names()
    if not categories:
        categories = [ensure_other_exists().name]

    # Optional: minimal hints from DB to help the model (free text, not authoritative)
    hints = "\n".join(f"- {name}" for name in categories[:50])  # keep short if many

    system_prompt = (
        "Classify the bank transaction into exactly ONE of the allowed categories. "
        "Choose ONLY from the provided list. If unsure, pick the closest match."
        "\n\nAllowed categories:\n" + (hints if hints else "- other")
    )

    # Constrain output with a function + enum built from DB
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Transaction: {json.dumps(tx)}"},
        ],
        functions=[{
            "name": "categorize_transaction",
            "description": "Assign the transaction to one of the predefined categories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": categories}
                },
                "required": ["category"]
            }
        }],
        function_call={"name": "categorize_transaction"},
        temperature=0
    )

    args = json.loads(resp.choices[0].message.function_call.arguments)
    chosen_name = args["category"]  # guaranteed to be one of `categories`
    row = get_category_by_name(chosen_name) or ensure_other_exists()

    put_cached_category_id(key, tx, row.id)
    return row.id

# ---------------- Seeding (optional) ----------------
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

# Example usage
if __name__ == "__main__":
    seed_categories_if_empty()  # run once if you want defaults

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
        print(f"{tx['description']} → {session.get(Category, cid).name} (id={cid})")
