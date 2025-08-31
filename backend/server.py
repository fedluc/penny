# backend/server.py
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os

from gpt_classifier import classify_transaction # your existing function

# ---- Pydantic models (exact transaction shape your backend expects) ----
class Transaction(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    description: str
    amount: float  # allow negatives for expenses

class Classified(Transaction):
    category: str
    confidence: Optional[float] = None

class ClassifyResponse(BaseModel):
    results: List[Classified]

app = FastAPI(title="Expense Categorizer API", version="0.1.0")

# CORS for Vite dev (adjust as needed)
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

@app.post("/classify", response_model=ClassifyResponse)
async def classify_endpoint(req: Request):
    # Ensure OpenAI key (prefer env; fallback reads backend/openai_api_key)
    key_path = os.path.join(os.path.dirname(__file__), "openai_api_key")
    if not os.getenv("OPENAI_API_KEY") and os.path.exists(key_path):
        with open(key_path, "r") as f:
            os.environ["OPENAI_API_KEY"] = f.read().strip()

    try:
        data: Dict[str, Any] = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Accept either `transactions` (preferred) or `expenses` (legacy)
    items = data.get("transactions")
    if not isinstance(items, list):
        raise HTTPException(400, detail="Payload must include 'transactions': [...]")

    # Normalize to the exact structure your backend expects
    transactions: List[Dict[str, Any]] = []
    for i, raw in enumerate(items):
        try:
            tx = Transaction(
                date=str(raw.get("date", "")).strip(),
                description=str(raw.get("description", "")).strip(),
                amount=float(raw.get("amount")),
            )
            transactions.append({"date": tx.date, "description": tx.description, "amount": tx.amount})
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid transaction at index {i}: {e}")

    top_k = int(data.get("top_k", 1))

    try:
        # Try with top_k first; fall back if your function doesn't support it.
        try:
            preds = classify_transaction(transactions, top_k=top_k)
        except TypeError:
            preds = classify_transaction(transactions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"classify() failed: {e}")

    results: List[Dict[str, Any]] = []
    for tx, pred in zip(transactions, preds):
        if isinstance(pred, dict):
            category = pred.get("category")
            confidence = pred.get("confidence")
        else:
            category, confidence = str(pred), None
        results.append({**tx, "category": category, "confidence": confidence})

    return {"results": results}
