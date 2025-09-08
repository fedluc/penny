from database import session, seed_categories_if_empty, Category
from gpt_classifier import classify_transaction

if __name__ == "__main__":
    seed_categories_if_empty()
    transactions = [
        {"date": "2025-06-01", "description": "ICA 45.67", "amount": -45.67},
        {"date": "2025-06-05", "description": "DINNER 30.00", "amount": -30.00},
        {"date": "2025-06-07", "description": "UBER RIDE 15.50", "amount": -15.50},
        {
            "date": "2025-06-08",
            "description": "ELECTRICITY BILL 75.00",
            "amount": -75.00,
        },
        {"date": "2025-06-09", "description": "MOVIE TICKETS 20.00", "amount": -20.00},
        {
            "date": "2025-06-10",
            "description": "PETSMART DOG FOOD 23.99",
            "amount": -23.99,
        },
    ]
    for tx in transactions:
        cid = classify_transaction(tx)
        print(f"{tx['description']} → {session.get(Category, cid).name} (id={cid})")
