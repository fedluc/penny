# backend/server.py
from fastapi import FastAPI, HTTPException, Request, Depends, APIRouter, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
import json

from gpt_classifier import GPTClassifier  # classify_batch(list[dict]) -> list[int]
from database import TransactionCache  # ORM model to read cached transactions

# ---------- App name and version ----------
APP_NAME = "Expense Categorizer API"
APP_VERSION = "0.1.0"


# ---------- Pydantic models ----------
class Transaction(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    description: str
    amount: float


class Classified(Transaction):
    category: str | None = None
    category_id: int | None = None
    confidence: float | None = None


class ClassifyResponse(BaseModel):
    results: list[Classified]


# ---------- App Builder ----------
class AppBuilder:

    def __init__(
        self,
        title: str,
        version: str,
        *,
        cors_origins: list[str] | None = None,
        classifier: GPTClassifier | None = None,
    ):
        self.title = title
        self.version = version
        self.cors_origins = cors_origins or [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
        self._provided_classifier = classifier

    # --- lifespan: startup/teardown of long-lived resources ---
    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        # Create (or use injected) classifier
        app.state.classifier = self._provided_classifier or GPTClassifier()
        try:
            yield
        finally:
            # Teardown hooks for future resources (DB pools, HTTP sessions), if any.
            pass

    # --- DI: fetch classifier for handlers ---
    def dep_classifier(self, request: Request) -> GPTClassifier:
        return request.app.state.classifier

    # ---------- Handlers ----------
    def _health_handler(self):
        async def health():
            return {"ok": True}

        return health

    def _classify_handler(self):
        async def classify_endpoint(
            req: Request,
            clf: GPTClassifier = Depends(self.dep_classifier),
        ):
            payload = await self._read_json(req)
            items = payload.get("transactions") or payload.get("expenses")
            if not isinstance(items, list):
                raise HTTPException(
                    status_code=400, detail="Expected 'transactions' array"
                )

            transactions = self._normalize_transactions(items)
            if not transactions:
                return {"results": []}

            try:
                category_ids: list[int] = clf.classify_batch(transactions)
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"classify_batch failed: {e}"
                )

            results: list[dict] = []
            for tx, cat_id in zip(transactions, category_ids):
                results.append(
                    {
                        **tx,
                        "category": None,
                        "category_id": int(cat_id),
                        "confidence": None,
                    }
                )
            return {"results": results}

        return classify_endpoint

    def _list_transactions_handler(self):
        async def list_transactions(
            clf: GPTClassifier = Depends(self.dep_classifier),
            limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
            offset: int = Query(0, ge=0, description="Rows to skip"),
        ):
            """
            Return cached transactions already stored in the database.
            Useful for debugging/inspecting classification results.
            """
            # Reuse the DB managed by the classifier (no new globals/singletons)
            db = clf.db  # GPTClassifier holds your Database instance
            with db.Session() as s:
                rows = (
                    s.query(TransactionCache)
                    .order_by(TransactionCache.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )

                # Keep shape consistent with POST /classify response
                results: list[dict] = []
                for r in rows:
                    # If you later switch to JSON type, remove the json.loads below
                    try:
                        tx_obj = (
                            r.transaction
                            if isinstance(r.transaction, dict)
                            else json.loads(r.transaction)
                        )
                    except Exception:
                        # Fallback: return raw text if parsing fails
                        tx_obj = {"raw": r.transaction}

                    results.append(
                        {
                            **{
                                "date": tx_obj.get("date"),
                                "description": tx_obj.get("description"),
                                "amount": tx_obj.get("amount"),
                            },
                            "category": None,  # reserved for future label support
                            "category_id": (
                                int(r.category_id)
                                if r.category_id is not None
                                else None
                            ),
                            "confidence": None,
                            "hash": r.hash,
                            "created_at": (
                                r.created_at.isoformat() if r.created_at else None
                            ),
                        }
                    )
                return {"results": results}

        return list_transactions

    # ---------- Private helpers ----------
    async def _read_json(self, req: Request) -> dict:
        try:
            obj = await req.json()
            if not isinstance(obj, dict):
                raise ValueError("Root JSON must be an object")
            return obj
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

    def _normalize_transactions(self, items: list[dict]) -> list[dict]:
        txs: list[dict] = []
        for i, raw in enumerate(items):
            try:
                tx = Transaction(
                    date=str(raw.get("date", "")).strip(),
                    description=str(raw.get("description", "")).strip(),
                    amount=float(raw.get("amount")),
                )
                txs.append(
                    {
                        "date": tx.date,
                        "description": tx.description,
                        "amount": tx.amount,
                    }
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid transaction at index {i}: {e}"
                )
        return txs

    # --- Router assembly ---
    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/health", self._health_handler(), methods=["GET"])
        router.add_api_route(
            "/classify",
            self._classify_handler(),
            methods=["POST"],
            response_model=ClassifyResponse,
        )
        router.add_api_route(
            "/transactions",
            self._list_transactions_handler(),
            methods=["GET"],
            summary="List cached transactions",
        )
        return router

    # --- public factory ---
    def create_app(self) -> FastAPI:
        app = FastAPI(title=self.title, version=self.version, lifespan=self._lifespan)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.include_router(self._build_router())
        return app


# Factory entrypoint for uvicorn
def create_app() -> FastAPI:
    return AppBuilder(APP_NAME, APP_VERSION).create_app()
