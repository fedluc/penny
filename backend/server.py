# backend/server.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Depends, APIRouter, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from datetime import datetime, date as DateOnly


from gpt_classifier import GPTClassifier
from database.database import Database, Expense, Category

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


class SaveExpensesRequest(BaseModel):
    expenses: list[Classified] = Field(..., description="Expenses to persist")


class SaveExpensesResponse(BaseModel):
    inserted_ids: list[int]


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
        # Expose DB (assumes classifier has .db)
        if not hasattr(app.state.classifier, "db"):
            raise RuntimeError(
                "GPTClassifier must expose a `.db` attribute (Database)."
            )
        app.state.db: Database = app.state.classifier.db
        try:
            yield
        finally:
            # Teardown hooks for future resources (DB pools, HTTP sessions), if any.
            pass

    # --- DI: fetch classifier/db for handlers ---
    def dep_classifier(self, request: Request) -> GPTClassifier:
        return request.app.state.classifier

    def dep_db(self, request: Request) -> Database:
        return request.app.state.db

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
                    status_code=400,
                    detail="Expected 'expenses' array",
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

    def _save_expenses_handler(self):
        async def save_expenses(
            payload: SaveExpensesRequest,
            db: Database = Depends(self.dep_db),
        ) -> SaveExpensesResponse:
            """
            Persist expenses (classified or not). If category is a name, it will be resolved.
            If neither category nor category_id provided, they fall back to 'other'.
            """
            inserted: list[int] = []

            # Ensure 'other' exists once (avoid doing this per-row)
            other_id = db.get_or_create_other()

            for i, item in enumerate(payload.expenses):
                # Validate/parse date (YYYY-MM-DD)
                try:
                    d: DateOnly = datetime.strptime(item.date, "%Y-%m-%d").date()
                except Exception:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid date at index {i}: {item.date!r}",
                    )

                # Amount
                try:
                    amt = float(item.amount)
                except Exception:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid amount at index {i}: {item.amount!r}",
                    )

                # Resolve category id
                cat_id: int
                if item.category_id is not None:
                    cat_id = int(item.category_id)
                elif item.category:
                    cat_id = db.resolve_category_id(
                        item.category, fallback_other_id=other_id
                    )
                else:
                    cat_id = other_id

                # Save; include raw copy for provenance
                raw = {
                    "date": item.date,
                    "description": item.description,
                    "amount": amt,
                    "category": item.category,
                    "category_id": cat_id,
                }
                new_id = db.add_expense(
                    date=d,
                    amount=amt,
                    description=item.description,
                    category_id=cat_id,
                    raw=raw,
                    dedupe_on_hash=True,  # idempotent on identical raw payloads
                )
                inserted.append(new_id)

            return SaveExpensesResponse(inserted_ids=inserted)

        return save_expenses

    def _list_expenses_handler(self):
        async def list_expenses(
            db: Database = Depends(self.dep_db),
            limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
            offset: int = Query(0, ge=0, description="Rows to skip"),
            since: str | None = Query(
                None, description="YYYY-MM-DD lower bound on date"
            ),
        ):
            """
            Return stored expenses (new Expense model), most recent first by date then amount desc.
            """
            with db.Session() as s:
                # Join to get the category name; keep LEFT JOIN (isouter=True) in case of missing categories
                q = s.query(Expense, Category.name.label("category_name"))
                if since:
                    try:
                        since_dt = datetime.strptime(since, "%Y-%m-%d").date()
                        q = q.filter(Expense.date >= since_dt)
                    except Exception:
                        raise HTTPException(status_code=400, detail=f"Invalid 'since' date: {since!r}")

                rows = (
                    q.join(Category, Expense.category_id == Category.id, isouter=True)
                    .order_by(Expense.date.desc(), Expense.amount.desc(), Expense.id.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )

                results: list[dict] = []
                for exp, cat_name in rows:
                    results.append(
                        {
                            "date": exp.date.isoformat(),
                            "description": exp.description,
                            "amount": float(exp.amount),
                            "category": cat_name,  # ← human-readable name
                            "created_at": exp.created_at.isoformat() if exp.created_at else None,
                        }
                    )

                return {"results": results}

        return list_expenses

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

        # Classify (no persistence)
        router.add_api_route(
            "/classify",
            self._classify_handler(),
            methods=["POST"],
            response_model=ClassifyResponse,
        )

        # Persist & list expenses (new model)
        router.add_api_route(
            "/expenses",
            self._save_expenses_handler(),
            methods=["POST"],
            response_model=SaveExpensesResponse,
            summary="Persist expenses",
        )
        router.add_api_route(
            "/expenses",
            self._list_expenses_handler(),
            methods=["GET"],
            summary="List stored expenses",
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
