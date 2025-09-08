# backend/server.py (updated)
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os

# Use the new class-based classifier with batch support
from gpt_classifier import GPTClassifier  # expects .classify_batch(List[Dict]) -> List[int]

class Transaction(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    description: str
    amount: float

class Classified(Transaction):
    category: Optional[str] = None
    category_id: Optional[int] = None
    confidence: Optional[float] = None

class ClassifyResponse(BaseModel):
    results: List[Classified]

app = FastAPI(title="Expense Categorizer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

# Lazy singleton for the classifier (initialized after key is ensured)
_clf: Optional[GPTClassifier] = None

def get_classifier() -> GPTClassifier:
    global _clf
    if _clf is None:
        _clf = GPTClassifier()
    return _clf

@app.post("/classify", response_model=ClassifyResponse)
async def classify_endpoint(req: Request, response: Response):
    # Ensure OpenAI key (prefer env; fallback reads backend/openai_api_key)
    key_path = os.path.join(os.path.dirname(__file__), "openai_api_key")
    if not os.getenv("OPENAI_API_KEY") and os.path.exists(key_path):
        with open(key_path, "r") as f:
            os.environ["OPENAI_API_KEY"] = f.read().strip()

    try:
        payload: Dict[str, Any] = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    items = payload.get("transactions") or payload.get("expenses")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Expected 'transactions' array")

    # Validate & normalize to expected shape
    transactions: List[Dict[str, Any]] = []
    for i, raw in enumerate(items):
        try:
            tx = Transaction(
                date=str(raw.get("date", "")).strip(),
                description=str(raw.get("description", "")).strip(),
                amount=float(raw.get("amount")),
            )
            transactions.append(
                {"date": tx.date, "description": tx.description, "amount": tx.amount}
            )
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid transaction at index {i}: {e}"
            )

    if not transactions:
        return {"results": []}

    # Batch classify (GPTClassifier returns a list of category_ids)
    try:
        clf = get_classifier()
        category_ids: List[int] = clf.classify_batch(transactions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"classify_batch failed: {e}")

    # Build normalized response
    results: List[Dict[str, Any]] = []
    for tx, cat_id in zip(transactions, category_ids):
        results.append(
            {
                **tx,
                "category": None,           # reserved if you later return labels
                "category_id": int(cat_id),
                "confidence": None,         # reserved if you later emit confidences
            }
        )

    return {"results": results}
