# backend/server.py (only the relevant parts shown)
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os

# IMPORTANT: import the single-item classifier
from gpt_classifier import classify_transaction  # returns int/str/dict per transaction


class Transaction(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    description: str
    amount: float


class Classified(Transaction):
    # Either category (string label) or category_id (int) will be present depending on your classifier.
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


@app.post("/classify", response_model=ClassifyResponse)
async def classify_endpoint(req: Request, response: Response):
    # Ensure OpenAI key (prefer env; fallback reads backend/openai_api_key)
    key_path = os.path.join(os.path.dirname(__file__), "openai_api_key")
    if not os.getenv("OPENAI_API_KEY") and os.path.exists(key_path):
        with open(key_path, "r") as f:
            os.environ["OPENAI_API_KEY"] = f.read().strip()

    try:
        data: Dict[str, Any] = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    items = data.get("transactions") or data.get("expenses")
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

    # Classify EACH transaction (classify_transaction returns a single result per item)
    results: List[Dict[str, Any]] = []
    for tx in transactions:
        try:
            # First try passing the whole dict
            pred = classify_transaction(tx)
        except TypeError:
            # If your function expects positional args, try common variants
            try:
                pred = classify_transaction(tx["description"], tx["amount"], tx["date"])
            except TypeError:
                pred = classify_transaction(tx["description"], tx["amount"])

        # Normalize output to a consistent response
        out: Dict[str, Any] = {
            **tx,
            "category": None,
            "category_id": None,
            "confidence": None,
        }
        if isinstance(pred, dict):
            # e.g. {"category":"groceries","confidence":0.92} or {"category_id":3}
            if "category" in pred:
                out["category"] = pred.get("category")
            if "category_id" in pred:
                out["category_id"] = int(pred["category_id"])
            if "confidence" in pred:
                out["confidence"] = pred.get("confidence")
        elif isinstance(pred, (int,)) and not isinstance(pred, bool):
            out["category_id"] = int(pred)
        else:
            # treat as a label string
            out["category"] = str(pred)

        results.append(out)

    return {"results": results}
