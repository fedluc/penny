from sqlalchemy import select
from sqlalchemy.orm import Session
from database.tables import Category

DEFAULT_SEED = [
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


def ensure_seed(s: Session, seed=DEFAULT_SEED):
    existing = set(n.lower() for n in s.scalars(select(Category.name)).all())
    to_add = [
        Category(name=n, description=d) for n, d in seed if n.lower() not in existing
    ]
    if to_add:
        s.add_all(to_add)
        s.commit()
